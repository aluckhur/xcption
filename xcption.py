#!/usr/bin/python
import csv
import argparse
import re
import logging
import sys
import os
import json
import pprint
import nomad
import subprocess

from jinja2 import Environment, FileSystemLoader

pp = pprint.PrettyPrinter(indent=1)

#general settings
dcname = 'DC1'
xcppath = '/usr/sbin/xcp'
nomadpath = '/usr/local/bin/nomad'
jobsdir = 'jobs' #relative to the script directory 
ginga2templatedir = 'template' #relative to the script directory 
defaultjobcron = "*/5 * * * *"
defaultcpu = 100
defaultmemory = 200

parser = argparse.ArgumentParser()
parser.add_argument('-a','--action', choices=['init', 'baseline', 'sync', 'status'], help="action to take during invokation",required=True,type=str)
parser.add_argument('-c','--csvfile', help="input CSV file with the following columns: Job Name,SRC Path,DST Path",required=True,type=str)
parser.add_argument('-d','--debug', help="log debug messages to console", action='store_true')

args = parser.parse_args()

#initialize logging 
log = logging.getLogger()
log.setLevel(logging.DEBUG)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# create file handler which logs even debug messages
fh = logging.FileHandler('xcption.log')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
log.addHandler(fh)

# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
if args.debug: ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
log.addHandler(ch)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)

logging.info("starting " + os.path.basename(sys.argv[0])) 

#initialize dict objects
jobsdict = {}
dstdict = {}
nomadout = {}

def parse_csv(csv_path):
	with open(csv_path) as csv_file:
		csv_reader = csv.reader(csv_file, delimiter=',')
		line_count = 0
		for row in csv_reader:
			if line_count == 0 or re.search("^\s*\#",row[0]):
				line_count += 1
			else:
				jobname = row[0]
				src     = row[1]
				dst     = row[2]
				
				cron    = ''
				if 3 < len(row): cron    = row[3] 
				if cron == '':   cron    = defaultjobcron 


				cpu     = '' 
				if 4 < len(row): cpu     = row[4] 
				if cpu == '':    cpu     = defaultcpu 
				
				memory  = ''
				if 5 < len(row): memory  = row[5] 
				if memory == '': memory  = defaultmemory 
				
				logging.info("parsing entry for job:" + jobname	 + " src:" + src + " dst:" + dst) 
				if not re.search("\S+\:\/\S+", src):
					logging.error("src path format is incorrect: " + src) 
					exit(1)	
				if not re.search("\S+\:\/\S+", dst):
					logging.error("dst path format is incorrect: " + dst)
					exit(1)	
				
				if args.action == 'init':
					#check if src/dst can be mounted
					subprocess.call( [ 'mkdir', '-p','/tmp/temp_mount' ] )
					if subprocess.call( [ 'mount', '-t', 'nfs', '-o','vers=3', src, '/tmp/temp_mount' ],stderr=subprocess.STDOUT):
						logging.error("cannot mount src using nfs: " + src)
						exit(1)					
					subprocess.call( [ 'umount', '/tmp/temp_mount' ],stderr=subprocess.STDOUT)
					
					if subprocess.call( [ 'mount', '-t', 'nfs', '-o','vers=3', dst, '/tmp/temp_mount' ],stderr=subprocess.STDOUT):
						logging.error("cannot mount dst using nfs: " + dst)
						exit(1)					
					subprocess.call( [ 'umount', '/tmp/temp_mount' ],stderr=subprocess.STDOUT)	
					
				srchost,srcpath = src.split(":")
				dsthost,dstpath = dst.split(":")		
				
				#validate no duplicate src and destination 
				if not jobname in jobsdict:
					jobsdict[jobname]={}
				if src in jobsdict[jobname]:
					logging.error("duplicate src path: " + src)
					exit(1)
				if dst in dstdict:
					logging.error("duplicate dst path: " + dst)
					exit(1)
						
				srcbase = src.replace(':/','-_')
				srcbase = srcbase.replace('/','_')
				
				dstbase = dst.replace(':/','-_')
				dstbase = dstbase.replace('/','_')
				
				baseline_job_name = 'baseline_'+jobname+'_'+srcbase
				sync_job_name = 'sync_'+jobname+'_'+srcbase
				
				xcpindexname = srcbase +'-'+dstbase	
				
				#fill dict with info
				jobsdict[jobname][src] = {}
				jobsdict[jobname][src]["dst"] = dst
				jobsdict[jobname][src]["srchost"] = srchost
				jobsdict[jobname][src]["srcpath"] = srcpath
				jobsdict[jobname][src]["dsthost"] = dsthost
				jobsdict[jobname][src]["dstpath"] = dstpath
				jobsdict[jobname][src]["srcbase"] = srcbase
				jobsdict[jobname][src]["dstbase"] = dstbase
				jobsdict[jobname][src]["baseline_job_name"] = baseline_job_name
				jobsdict[jobname][src]["sync_job_name"] = sync_job_name
				jobsdict[jobname][src]["xcpindexname"] = xcpindexname
				jobsdict[jobname][src]["cron"] = cron
				jobsdict[jobname][src]["cpu"] = cpu
				jobsdict[jobname][src]["memory"] = memory

				
				dstdict[dst] = 1
				line_count += 1

def create_nomad_jobs():
	root = os.path.dirname(os.path.abspath(__file__))
	#loading job ginga2 templates 
	templates_dir = os.path.join(root, ginga2templatedir)
	env = Environment( loader = FileSystemLoader(templates_dir) )
	
	try:
		baseline_template = env.get_template('nomad_baseline.txt')
	except:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_baseline.txt'))
		exit(1)
	
	try:	
		sync_template = env.get_template('nomad_sync.txt')
	except:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_sync.txt'))
		exit(1)
	
	for jobname in jobsdict:
		jobdir = os.path.join(root, jobsdir,jobname)
		
		#check if job dir exists
		if os.path.exists(jobdir):
			logging.warning("job directory:" + jobdir + " - already exists") 
		else:	
			if os.makedirs(jobdir):
				logging.error("could not create output directory: " + jobdir)				
				exit(1)
				
		for src in jobsdict[jobname]:
			jobdetails = jobsdict[jobname][src]
			
			dst	              = jobdetails['dst']
			srcbase           = jobdetails['srcbase']
			dstbase           = jobdetails['dstbase']
			baseline_job_name = jobdetails['baseline_job_name']
			sync_job_name     = jobdetails['sync_job_name']
			xcpindexname      = jobdetails['xcpindexname']	
			jobcron           = jobdetails['cron']
			cpu    			  = jobdetails['cpu']
			memory            = jobdetails['memory']
			
			#creating baseline job 
			baseline_job_file = os.path.join(jobdir,baseline_job_name+'.hcl')	
			
			logging.info("creating baseline job file: " + baseline_job_file)				
			with open(baseline_job_file, 'w') as fh:
				fh.write(baseline_template.render(
					dcname=dcname,
					baseline_job_name=baseline_job_name,
					xcppath=xcppath,
					xcpindexname=xcpindexname,
					memory=memory,
					cpu=cpu,	
					src=src,
					dst=dst
				))
			#call( [ 'nomad', 'run', baseline_job_file] )
			
			#creating sync job 
			sync_job_file = os.path.join(jobdir,sync_job_name+'.hcl')		
			logging.info("creating sync job file: " + sync_job_file)				
			with open(sync_job_file, 'w') as fh:
				fh.write(sync_template.render(
					dcname=dcname,
					sync_job_name=sync_job_name,
					jobcron=jobcron,
					xcppath=xcppath,
					xcpindexname=xcpindexname,
					memory=memory,
					cpu=cpu					
				))

def start_nomad_jobs(action):

	root = os.path.dirname(os.path.abspath(__file__))			
	
	n = nomad.Nomad(host="localhost", timeout=5)
	
	for jobname in jobsdict:
		jobdir = os.path.join(root, jobsdir,jobname)

		#check if job dir exists
		if not os.path.exists(jobdir):
			logging.error("job directory:" + jobdir + " not exists. please init first") 
			exit (1)
				
		for src in jobsdict[jobname]:
			jobdetails = jobsdict[jobname][src]
			
			dst	          = jobdetails['dst']
			srcbase       = jobdetails['srcbase']
			dstbase       = jobdetails['dstbase']
			nomadjobname  = jobdetails[action+'_job_name']
			xcpindexname  = jobdetails['xcpindexname']	
		
			try:	
				job = n.job.get_job(nomadjobname)
			except:
				job = ''
			
			if job:
				logging.warning("job name:"+nomadjobname+" already exists") 
			
			if (action != 'baseline' and job) or not job:
				jobfile = os.path.join(jobdir,nomadjobname+'.hcl')		
				logging.info("starting job:" + nomadjobname) 
				nomadjobjson = subprocess.check_output([ nomadpath, 'run','-output',jobfile])
				nomadjobdict = json.loads(nomadjobjson)
				
				
				nomadjobdict['Job']['Stop'] = False


				try:
					nomadout = n.job.plan_job(nomadjobname, nomadjobdict)
				except:
					logging.error("job planning failed for job:"+nomadjobname+" please run: nomad job plan "+jobfile+ " for more details") 
					exit(1)

				nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
				try:
					job = n.job.get_job(nomadjobname)
				except:
					logging.error("job:"+nomadjobname+" creation failed") 

			elif action == 'baseline' and job:
				logging.warning("baseline job cannot be updated") 


			

parse_csv(args.csvfile)
if args.action == 'init':
	create_nomad_jobs()

if args.action == 'baseline':
	start_nomad_jobs('baseline')

if args.action == 'sync':
	start_nomad_jobs('sync')
	
if args.action == 'status':
	create_nomad_status()


