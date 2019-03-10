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
import requests
import subprocess
from prettytable import PrettyTable
from jinja2 import Environment, FileSystemLoader

pp = pprint.PrettyPrinter(indent=1)

#general settings
dcname = 'DC1'
xcppath = '/usr/sbin/xcp'
xcprepopath = '/xcption/xcprepo'
nomadpath = '/usr/local/bin/nomad'
jobsdir = 'jobs' #relative to the script directory 
ginga2templatedir = 'template' #relative to the script directory 
defaultjobcron = "*/1 * * * *"
defaultcpu = 100
defaultmemory = 800

parser = argparse.ArgumentParser()
#parser.add_argument('-a','--action', choices=['init', 'baseline', 'sync', 'status'], help="action to take during invokation",required=True,type=str)

parser.add_argument('-c','--csvfile', help="input CSV file with the following columns: Job Name,SRC Path,DST Path,Schedule,CPU,Memory",required=True,type=str)
parser.add_argument('-d','--debug',   help="log debug messages to console", action='store_true')


subparser = parser.add_subparsers(dest='subparser_name', help='sub commands that can be used')

# create the sub commands 
parser_status   = subparser.add_parser('status',   help='display status')
parser_init     = subparser.add_parser('init',     help='intialize/update configuration')
parser_baseline = subparser.add_parser('baseline', help='start baseline')
parser_sync     = subparser.add_parser('sync',     help='start scheule')
parser_syncnow  = subparser.add_parser('syncnow',  help='initiate sync now')
parser_pause    = subparser.add_parser('pause',    help='disabe next scheuled sync')
parser_resume   = subparser.add_parser('resume',   help='resume scheduled sync')
parser_scan     = subparser.add_parser('scan',     help='scan fielsystem')
parser_rescan   = subparser.add_parser('rescan',   help='rescan fielsystem')
parser_delete   = subparser.add_parser('delete',   help='delete existing config')

parser_logs = subparser.add_parser('logs',     help='display xcp logs')

parser_status.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_status.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_init.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_init.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_baseline.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_baseline.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_sync.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_sync.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_syncnow.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_syncnow.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_pause.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_pause.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_resume.add_argument('-j','--job',     help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_resume.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

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

logging.debug("starting " + os.path.basename(sys.argv[0])) 

#initialize dict objects
jobsdict = {}
dstdict = {}
nomadout = {}

#creation of the nomad instance 
n = nomad.Nomad(host="localhost", timeout=5)
#baseutl for nomad rest api requests 
nomadapiurl = 'http://localhost:4646/v1/'

#return nomad job details has dict, assert if not exists 
def getnomadjobdetails (nomadjobname):
	job = {}
	try:
		job = n.job.get_job(nomadjobname)
	except:
		assert not job 
	return job

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

				if (jobfilter == '' or jobfilter == jobname) and (srcfilter == '' or srcfilter == src):

					
					cron    = ''
					if 3 < len(row): cron    = row[3] 
					if cron == '':   cron    = defaultjobcron 


					cpu     = '' 
					if 4 < len(row): cpu     = row[4] 
					if cpu == '':    cpu     = defaultcpu 
					
					memory  = ''
					if 5 < len(row): memory  = row[5] 
					if memory == '': memory  = defaultmemory 
					
					logging.debug("parsing entry for job:" + jobname	 + " src:" + src + " dst:" + dst) 
					if not re.search("\S+\:\/\S+", src):
						logging.error("src path format is incorrect: " + src) 
						exit(1)	
					if not re.search("\S+\:\/\S+", dst):
						logging.error("dst path format is incorrect: " + dst)
						exit(1)	
					
					if args.subparser_name == 'init':
						#check if src/dst can be mounted
						subprocess.call( [ 'mkdir', '-p','/tmp/temp_mount' ] )
						logging.info("validating src:" + src + " and dst:" + dst+ " are mountable") 
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
					srcbase = srcbase.replace(' ','-')
					
					dstbase = dst.replace(':/','-_')
					dstbase = dstbase.replace('/','_')
					dstbase = dstbase.replace(' ','-')
					
					baseline_job_name = 'baseline_'+jobname+'_'+srcbase
					sync_job_name     = 'sync_'+jobname+'_'+srcbase
					scan_job_name     = 'scan_'+jobname+'_'+srcbase
					rescan_job_name   = 'rescan_'+jobname+'_'+srcbase					
					
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
					jobsdict[jobname][src]["sync_job_name"]     = sync_job_name
					jobsdict[jobname][src]["scan_job_name"]     = scan_job_name
					jobsdict[jobname][src]["rescan_job_name"]   = rescan_job_name					
					jobsdict[jobname][src]["xcpindexname"]      = xcpindexname
					jobsdict[jobname][src]["xcpscanindexname"]  = 'scan-'+xcpindexname
					jobsdict[jobname][src]["cron"]   = cron
					jobsdict[jobname][src]["cpu"]    = cpu
					jobsdict[jobname][src]["memory"] = memory

					
					dstdict[dst] = 1
					line_count += 1

def create_nomad_jobs():
	root = os.path.dirname(os.path.abspath(__file__))
	#loading job ginga2 templates 
	templates_dir = os.path.join(root, ginga2templatedir)
	env = Environment(loader=FileSystemLoader(templates_dir) )
	
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
	
	try:
		scan_template = env.get_template('nomad_scan.txt')
	except:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_scan.txt'))
		exit(1)
	
	try:	
		rescan_template = env.get_template('nomad_rescan.txt')
	except:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_rescan.txt'))
		exit(1)		
	
	for jobname in jobsdict:
		
		if jobfilter == '' or jobfilter == jobname:

			jobdir = os.path.join(root, jobsdir,jobname)
			
			#check if job dir exists
			if os.path.exists(jobdir):
				logging.warning("job directory:" + jobdir + " - already exists") 
			else:	
				if os.makedirs(jobdir):
					logging.error("could not create output directory: " + jobdir)				
					exit(1)
					
			for src in jobsdict[jobname]:
				if srcfilter == '' or srcfilter == src:
					jobdetails = jobsdict[jobname][src]
					
					dst	              = jobdetails['dst']
					srcbase           = jobdetails['srcbase']
					dstbase           = jobdetails['dstbase']
					baseline_job_name = jobdetails['baseline_job_name']
					sync_job_name     = jobdetails['sync_job_name']
					scan_job_name     = jobdetails['scan_job_name']
					rescan_job_name   = jobdetails['rescan_job_name']					
					xcpindexname      = jobdetails['xcpindexname']	
					xcpscanindexname  = jobdetails['xcpscanindexname']
					jobcron           = jobdetails['cron']
					cpu    			  = jobdetails['cpu']
					memory            = jobdetails['memory']
					
					#creating baseline job 
					baseline_job_file = os.path.join(jobdir,baseline_job_name+'.hcl')	
					logging.info("creating/updating relationship configs for src:"+src)
					logging.debug("creating baseline job file: " + baseline_job_file)				
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
					
					#creating sync job 
					sync_job_file = os.path.join(jobdir,sync_job_name+'.hcl')		
					logging.debug("creating sync job file: " + sync_job_file)				
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

					#creating scan job
					scan_job_file = os.path.join(jobdir,scan_job_name+'.hcl')	
					logging.debug("creating scan job file: " + scan_job_file)				
					with open(scan_job_file, 'w') as fh:
						fh.write(baseline_template.render(
							dcname=dcname,
							baseline_job_name=scan_job_name,
							xcppath=xcppath,
							xcpindexname=xcpscanindexname,
							memory=memory,
							cpu=cpu,	
							src=src,
							dst=dst
						))					

					#creating rescan job 
					rescan_job_file = os.path.join(jobdir,rescan_job_name+'.hcl')		
					logging.debug("creating rescan job file: " + rescan_job_file)				
					with open(rescan_job_file, 'w') as fh:
						fh.write(sync_template.render(
							dcname=dcname,
							sync_job_name=rescan_job_name,
							jobcron=jobcron,
							xcppath=xcppath,
							xcpindexname=xcpscanindexname,
							memory=memory,
							cpu=cpu					
						))

def start_nomad_jobs(action):

	root = os.path.dirname(os.path.abspath(__file__))			
	
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(root, jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.error("job config directory:" + jobdir + " not exists. please init first") 
				exit (1)
					
			for src in jobsdict[jobname]:
				if srcfilter == '' or srcfilter == src:
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
						logging.debug("job name:"+nomadjobname+" already exists") 
					
					if (action != 'baseline' and job) or not job:
						jobfile = os.path.join(jobdir,nomadjobname+'.hcl')		
						if not os.path.exists(jobfile): 
							logging.warning("log file"+jobfile+" for job:"+nomadjobname+" could not be found, please run init again") 
						else:
							logging.info("starting/updating job:" + nomadjobname) 
							nomadjobjson = subprocess.check_output([ nomadpath, 'run','-output',jobfile])
							nomadjobdict = json.loads(nomadjobjson)

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
								exit(1)



							#force immediate baseline than disable the cron 
							if action == 'baseline':
								response = requests.post(nomadapiurl+'job/'+nomadjobname+'/periodic/force')	
								if not response.ok:
									logging.error("job:"+nomadjobname+" force start failed") 
									exit(1)

								#nomadjobdict['Job']['Stop'] = True
								#nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
								#try:
								#	job = n.job.get_job(nomadjobname)
								#except:
								#	logging.error("job:"+nomadjobname+" disable cron failed failed") 
								#	exit(1)

					elif action == 'baseline' and job:
						logging.warning("baseline job already exists and cannot be updated") 

#parse stats from xcp logs, logs can be retrived from api or file in the repo
def parse_stats_from_log (allocid,type):

	#output dict
	results = {}
	#logs file are periodicaly copied to the xcprepo folder using periodic nomad xcption_gc job using system/xcption_gc.sh script 
	logfileinxcprepo = os.path.join(xcprepopath,'tmpreports','alloc',allocid,'alloc','logs',type+'.stderr.0')
	logging.debug("log file name path:"+logfileinxcprepo)								

	#try to get the log file using api
	response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+type+'&type=stderr&plain=true')

	lastline = ''

	if response.ok and response.content:
		logging.debug("log for job:"+allocid+" is avaialble using api")								
		lastline = response.content.splitlines()[-1]
	elif os.path.isfile(logfileinxcprepo):
		logging.debug("log for job:"+allocid+" is avaialble in file")								
		with open(logfileinxcprepo, 'r') as f:
		    lines = f.read().splitlines()
		    lastline = lines[-1]
	else: 
		logging.warning("could not find log file for job:"+allocid)																	

	if lastline:
		matchObj = re.search("\s+(\S*\d+s)(\.)?$", lastline, re.M|re.I)
		if matchObj: results['time'] = matchObj.group(1)
	return results


#create general status table 
def create_general_status ():

	root = os.path.dirname(os.path.abspath(__file__))			

	#get nomad allocations 
	jobs  = n.jobs.get_jobs()
	allocs = n.allocations.get_allocations()
	
	#build the table object
	table = PrettyTable()
	table.field_names = ["Job","Source Path", "Dest Path", "Baseline Status", "Baseline Time", "Sync Status", "Last Sync Time"]
	rowcount = 0
	
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(root, jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.error("job config directory:" + jobdir + " not exists. please init first") 
				exit (1)
					
			for src in jobsdict[jobname]:
				jobdetails = jobsdict[jobname][src]
				
				dst	          = jobdetails['dst']
				srcbase       = jobdetails['srcbase']
				dstbase       = jobdetails['dstbase']
				xcpindexname  = jobdetails['xcpindexname']	

				baseline_job_name = jobdetails['baseline_job_name']
				sync_job_name     = jobdetails['sync_job_name']
				scan_job_name     = jobdetails['scan_job_name']
				rescan_job_name   = jobdetails['rescan_job_name']					
				xcpindexname      = jobdetails['xcpindexname']			
				jobcron           = jobdetails['cron']

				baselinestatus = 'unknown'
				baselinetime   = '-'

				updatestatus   = 'unknow'
				synctime     = '-'
				syncsched     = jobcron

				for job in jobs:
					synccounter = 0				
					if job['ID'].startswith(baseline_job_name+'/periodic-'):
						baselinestatus = job['Status']
						for alloc in allocs:
							if alloc['JobID'].startswith(baseline_job_name+'/periodic-'):
								if baselinestatus == 'dead': baselinestatus =  alloc['ClientStatus'] 
								statsresults = parse_stats_from_log(alloc['ID'],'baseline')
								if 'time' in statsresults.keys(): baselinetime = statsresults['time']
				
				#take care of sync job status 
				joblastid = ''
				joblastallocid = ''
				for job in jobs:
					
					if job['ID'] == sync_job_name:
						
						if job['Stop']: syncsched = 'Disabled'
					
					if job['ID'].startswith(sync_job_name+'/periodic-'):
						updatestatus = job['Status']
						joblastid = job['ID']
						
						for alloc in allocs:
							if alloc['JobID'].startswith(sync_job_name+'/periodic-'):
								joblastallocid = alloc['ID'] 
			
				if joblastallocid: 
					n.job.get_job(joblastid) 
					lastalloc = n.allocation.get_allocation(joblastallocid)

					statsresults = parse_stats_from_log(joblastallocid,'sync')
					if statsresults['time']: synctime = statsresults['time']
					
					updatestatus =  lastalloc['ClientStatus']
					if updatestatus == 'complete': updatestatus = 'idle'
									
				table.add_row([jobname,src,dst,baselinestatus,baselinetime,updatestatus+'('+syncsched+')',synctime])
				rowcount += 1
					
	
	if rowcount > 0:
		table.border = False
		table.align = 'l'
		print table
	else:
		print "no data found"

#####################################################################################################
###################                        MAIN                                        ##############
#####################################################################################################


#filter by job or relationship
jobfilter = args.job
if not jobfilter: jobfilter = ''

srcfilter = args.source
if not srcfilter: srcfilter = ''

parse_csv(args.csvfile)
if args.subparser_name == 'init':
	create_nomad_jobs()

if args.subparser_name == 'baseline':
	start_nomad_jobs('baseline')

if args.subparser_name == 'sync':
	start_nomad_jobs('sync')
	
if args.subparser_name == 'status' and not srcfilter:
	create_general_status()





