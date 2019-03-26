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
import shutil
import croniter
import datetime
import time
import copy

from hurry.filesize import size
from prettytable import PrettyTable
from jinja2 import Environment, FileSystemLoader

pp = pprint.PrettyPrinter(indent=1)

#general settings
dcname = 'DC1'
#xcp path location
xcppath = '/usr/local/bin/xcp'
#location of the script 
root = os.path.dirname(os.path.abspath(__file__))
#xcp repo and cache dir loaction 
xcprepopath = os.path.join(root,'system','xcp_repo')
#xcp indexes path 
xcpindexespath = os.path.join(xcprepopath,'catalog','indexes')
#cache dir for current state 
cachedir = os.path.join(xcprepopath,'nomadcache')
#file containing loaded jobs 
jobdictjson = os.path.join(cachedir,'jobs.json')
#path to nomad bin 
nomadpath = '/usr/local/bin/nomad'
#location for the jobs dir
jobsdir = os.path.join(xcprepopath,'jobs') 
#job template dirs
ginga2templatedir = os.path.join(root,'template') 
#log file location
logfilepath = os.path.join(root,'log','xcption.log')

#default nomad job properties 
defaultjobcron = "0 0 * * * *" #nightly @ midnight
defaultcpu = 3000
defaultmemory = 800


parser = argparse.ArgumentParser()

#parser.add_argument('-c','--csvfile', help="input CSV file with the following columns: Job Name,SRC Path,DST Path,Schedule,CPU,Memory",required=True,type=str)
parser.add_argument('-d','--debug',   help="log debug messages to console", action='store_true')


subparser = parser.add_subparsers(dest='subparser_name', help='sub commands that can be used')

# create the sub commands 
parser_status   = subparser.add_parser('status',   help='display status')
parser_load     = subparser.add_parser('load',     help='load/update configuration from csv file')
parser_baseline = subparser.add_parser('baseline', help='start baseline (xcp copy)')
parser_sync     = subparser.add_parser('sync',     help='start schedule updates (xcp sync)')
parser_syncnow  = subparser.add_parser('syncnow',  help='initiate sync now')
parser_pause    = subparser.add_parser('pause',    help='disable sync schedule')
parser_resume   = subparser.add_parser('resume',   help='resume sync schedule')
#parser_scan     = subparser.add_parser('scan',     help='scan fielsystem')
#parser_rescan   = subparser.add_parser('rescan',   help='rescan fielsystem')
parser_delete   = subparser.add_parser('delete',   help='delete existing config')
parser_nomad    = subparser.add_parser('nomad',    description='hidden command, usded to backup nomad jobs into files')

parser_status.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_status.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_status.add_argument('-v','--verbose',help="provide detailed information", required=False,action='store_true')
parser_status.add_argument('-p','--phase',help="change the scope of the command to specific phase (basline,sync#)", required=False,type=str,metavar='phase')
parser_status.add_argument('-l','--logs',help="display xcp logs", required=False,action='store_true')

parser_load.add_argument('-c','--csvfile',help="input CSV file with the following columns: Job Name,SRC Path,DST Path,Schedule,CPU,Memory",required=True,type=str)
parser_load.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_load.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_baseline.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_baseline.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_sync.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_sync.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_syncnow.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_syncnow.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_pause.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_pause.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_resume.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_resume.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_delete.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_delete.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_delete.add_argument('-f','--force',help="force delete", required=False,action='store_true')

args = parser.parse_args()


#initialize logging 
log = logging.getLogger()
log.setLevel(logging.DEBUG)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
formatterdebug = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')

# create file handler which logs even debug messages
fh = logging.FileHandler(logfilepath)
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatterdebug)
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


#load jobsdict from json 
def load_jobs_from_json (jobdictjson):
	global jobsdict
	if os.path.exists(jobdictjson):
		try:
			logging.debug("loading existing json file:"+jobdictjson)
			with open(jobdictjson, 'r') as f:
				jobsdict = json.load(f)
		except:
			logging.debug("could not load existing json file:"+jobdictjson)

#parse input csv file
def parse_csv(csv_path):

	global jobsdict
	global dstdict
	
	if not os.path.exists(csv_path):
		logging.error("cannot find csv file:"+csv_path)
		exit(1)

	#checking existing job json file and try to load it 
	load_jobs_from_json(jobdictjson)

	with open(csv_path) as csv_file:
		csv_reader = csv.reader(csv_file, delimiter=',')
		line_count = 0
		for row in csv_reader:
			line = ' '.join(row)
			if line_count == 0 or re.search("^\s*\#",line) or re.search("^\s*$",line):
				line_count += 1
			else:
				logging.debug("parsing csv line:"+line)
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
					
					if args.subparser_name == 'load':
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
					if src in jobsdict[jobname] and dst != jobsdict[jobname][src]['dst']:
						logging.error("cannot load diffrent dst to existing src:" + src+"->"+dst)
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

					logging.debug("parsed the following relation:"+src+":"+dst)

					dstdict[dst] = 1
					line_count += 1
	#dumping jobsdict to json file 
	try:
		with open(jobdictjson, 'w') as fp:
			json.dump(jobsdict, fp)
		fp.close()
	except:
		logging.error("cannot write job json file:"+jobdictjson)
		exit(1)

# start nomad job from hcl file
def start_nomad_job_from_hcl(hclpath, nomadjobname):
	if not os.path.exists(hclpath):
		logging.error("cannot find hcl file:"+hclpath)
		exit(1)

	logging.debug("reading hcl file:"+hclpath)
	with open(hclpath, 'r') as f:
		hclcontent = f.read()

		hclcontent = hclcontent.replace('\n', '').replace('\r', '').replace('\t','')
		hcljson = {}
		hcljson['JobHCL'] = hclcontent
		hcljson['Canonicalize'] = True

		response = requests.post(nomadapiurl+'jobs/parse',json=hcljson)
		if response.ok:
			nomadjobdict={}
			nomadjobdict['Job'] = json.loads(response.content)
			try:
			 	nomadout = n.job.plan_job(nomadjobname, nomadjobdict)
			except:
			 	logging.error("job planning failed for job:"+nomadjobname+" please run: nomad job plan "+hclpath+ " for more details") 
			 	exit(1)
			logging.debug("starting job:"+nomadjobname)
			try:
				nomadout = n.job.register_job(nomadjobname, nomadjobdict)
			except:
				logging.error("job:"+nomadjobname+" creation failed") 
				exit(1)

#create nomad hcl files
def create_nomad_jobs():
	#loading job ginga2 templates 
	templates_dir = ginga2templatedir
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

			jobdir = os.path.join(jobsdir,jobname)
			
			#check if job dir exists
			if os.path.exists(jobdir):
				logging.debug("job directory:" + jobdir + " - already exists") 
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

def check_baseline_job_status (baselinejobname):
	baselinejob = {}
	try:	
		baselinejob = n.job.get_job(baselinejobname)
	except:
		baselinejob = None

	if not baselinejob:
		logging.debug("baseline job:"+baselinejobname+" does not exist")
		return('Baseline Not Exists')

	#if job exists validated it been completed
	if baselinejob:
		response = requests.get(nomadapiurl+'jobs?prefix='+baselinejobname+'/periodic')	
		if not response.ok:
			logging.debug("could not get job:"+baselinejobname+" periodic details") 
			baselinejob = None
		else:
			baselinejob = json.loads(response.content)
			baselinejobcompleted = 0
			try:
				baselinejobcompleted = baselinejob[0]['JobSummary']['Summary'][baselinejobname]['Complete']
			except:
				baselinejobcompleted = 0
				logging.debug("could not get periodic baseline job, trying on files")

				baselinecachedir = os.path.join(cachedir,'job_'+baselinejobname)
				if not os.path.exists(baselinecachedir): 
					logging.debug('cannot find job cache dir:'+baselinecachedir)
				else:			
					for file in os.listdir(baselinecachedir):
						if file.startswith("periodic-"):
							baselinecachefile = os.path.join(baselinecachedir,file)
							with open(baselinecachefile) as f:
								logging.debug('loading cached info periodic file:'+baselinecachefile)
								jobdata = json.load(f)
								baselinejobcompleted = 0
								baselinejobcompleted = jobdata['JobSummary']['Summary'][baselinejobname]['Complete']				
			if baselinejobcompleted != 1: 
				logging.debug("baseline job:"+baselinejobname+" exists but did not completed") 
				baselinejob = None
				return('Baseline Is Not Complete')
	return('Baseline Is Complete')

#start nomand job
def start_nomad_jobs(action):
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

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

							#if sync job and baseline was not started disable schedule 
							if action == 'sync':
								baselinejon = {}
								baselinejobname = jobdetails['baseline_job_name']
								baselinestatus = check_baseline_job_status(baselinejobname)
								if baselinestatus != 'Baseline Is Complete':
									logging.warning("sync will be paused:"+baselinestatus)
									nomadjobdict["Job"]["Stop"] = True
								else:
									logging.debug("baseline is completed:")

							nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
							try:
								job = n.job.get_job(nomadjobname)
							except:
								logging.error("job:"+nomadjobname+" creation failed") 
								exit(1)

							#force immediate baseline 
							if action == 'baseline':
								response = requests.post(nomadapiurl+'job/'+nomadjobname+'/periodic/force')	
								if not response.ok:
									logging.error("job:"+nomadjobname+" force start failed") 
									exit(1)
					elif action == 'baseline' and job:
						logging.warning("baseline job already exists and cannot be updated") 


#parse stats from xcp logs, logs can be retrived from api or file in the repo
def parse_stats_from_log (type,name,task='none'):
	#output dict
	results = {}
	results['content'] = ''
	lastline = ''

	if type == 'file':
		logfilepath = name 								
		try:
			with open(logfilepath, 'r') as f:
				content = f.read()
				lines = content.splitlines()
				if lines: 
					lastline = lines[-1]
					results['content'] = content
		except:
			logging.error("cannot read log file:"+logfilepath)	
	elif type == 'alloc':						
		#try to get the log file using api
		allocid = name
		response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+task+'&type=stderr&plain=true')
		if response.ok and re.search("\d", response.content, re.M|re.I):
			logging.debug("log for job:"+allocid+" is avaialble using api")								
			lines = response.content.splitlines()
			if lines:
				lastline = lines[-1]
			results['content'] = response.content
		else:
			logging.debug("log for job:"+allocid+" is not avaialble using api")																								

	if lastline:
		#print lastline
		matchObj = re.search("\s+(\S*\d+s)(\.)?$", lastline, re.M|re.I)
		if matchObj: 
			results['time'] = matchObj.group(1)

		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) scanned", lastline, re.M|re.I)
		if matchObj: 
			results['scanned'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) copied", lastline, re.M|re.I)
		if matchObj: 
			results['copied'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) indexed", lastline, re.M|re.I)
		if matchObj: 
			results['indexed'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) gone", lastline, re.M|re.I)
		if matchObj: 
			results['gone'] = matchObj.group(1)	
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) modification", lastline, re.M|re.I)
		if matchObj: 
			results['modification'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) errors", lastline, re.M|re.I)
		if matchObj: 
			results['errors'] = matchObj.group(1)

		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) file.gone", lastline, re.M|re.I)
		if matchObj: 
			results['filegone'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) dir.gone", lastline, re.M|re.I)
		if matchObj: 
			results['dirgone'] = matchObj.group(1)			
		matchObj = re.search("out \(([-+]?[0-9]*\.?[0-9]+ MiB\/s)", lastline, re.M|re.I)
		if matchObj: 
			results['bw'] = matchObj.group(1)			
	return results

#get the next cron run in human readable 
def get_next_cron_time (cron):
	now = datetime.datetime.now()
	cront = croniter.croniter(cron, now)
	nextdate = cront.get_next(datetime.datetime)
	delta = nextdate-now

	s = delta.seconds

	hours, remainder = divmod(s, 3600)
	minutes, seconds = divmod(remainder, 60)	
	return '{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds))

def sec_to_time(sec):
	sec = int(round(sec,0))
	days = int(round(sec // 86400,0))
	sec -= 86400*days

	hrs = int(round(sec // 3600,0))
	sec -= 3600*hrs

	mins = int(round(sec // 60,0))
	sec -= 60*mins

	return str(days)+'d:'+str(hrs)+'h:'+str(mins)+'m:'+str(int(round(sec,0)))+'s'

#create general status
def create_status (reporttype,displaylogs=False):

	#get nomad allocations 
	jobs = {}
	allocs = {}
	nodes = {}
	
	try:
		jobs  = n.jobs.get_jobs()
	except:
		logging.error('cannot get nomad job list')
		exit(1)
	try:
		allocs = n.allocations.get_allocations()
	except:
		logging.error('cannot get alloc list')
		exit(1)
	try:
		nodes = n.nodes.get_nodes()
	except:
		logging.error('cannot get node list')
		exit(1)

	nodename = '-'
	
	#build the table object
	table = PrettyTable()
	table.field_names = ["Job","Source Path", "Dest Path", "Baseline Status", "Baseline Time", "Sync Status", "Next Sync","Sync Time","Node","Sync #"]
	rowcount = 0
	
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.error("job config directory:" + jobdir + " not exists. please load first") 
				exit (1)
					
			for src in jobsdict[jobname]:
				if srcfilter == '' or srcfilter == src:
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

					baselinejobstatus = '-'
					baselinestatus = '-'

					baselinetime   = '-'

					syncstatus   = '- '
					synctime     = '- '
					nodename     = '- '
					syncsched    = get_next_cron_time(jobcron)

					baselinefound = False
					#location for the cache dir for baseline  
					baselinecachedir = os.path.join(cachedir,'job_'+baseline_job_name)

					statsresults ={}
					
					#baseline objects 
					baselinejob={}
					baselinealloc={}
					basleinelog={}

					if not os.path.exists(baselinecachedir): 
						logging.debug('cannot find job cache dir:'+baselinecachedir)
					else:			
						#for file in sorted(os.listdir(baselinecachedir),key=os.path.getctime):
						for file in os.listdir(baselinecachedir):
							if file.startswith("periodic-"):
								baselinecachefile = os.path.join(baselinecachedir,file)
								with open(baselinecachefile) as f:
									logging.debug('loading cached info periodic file:'+baselinecachefile)
									jobdata = json.load(f)
									baselinejobstatus = jobdata['Status']
									baselinejob = jobdata
							if file.startswith("alloc_"):
								baselinealloccachefile = os.path.join(baselinecachedir,file)
								with open(baselinealloccachefile) as f:
									logging.debug('loading cached info alloc file:'+baselinealloccachefile)
									allocdata = json.load(f)
									baselinestatus =  allocdata['ClientStatus']
									baselinefound  = True
									baselinealloc = allocdata
							if file.startswith("log_"):
								baselinelogcachefile = os.path.join(baselinecachedir,file)
								logging.debug('loading cached info log file:'+baselinelogcachefile)
								statsresults = parse_stats_from_log('file',baselinelogcachefile)
								if 'time' in statsresults.keys(): 
									baselinetime = statsresults['time']
									baselinelog = statsresults

					#set baseline job status based on the analysis 
					if baselinejobstatus == 'pending': baselinestatus='pending'


					#gather sync related info
					joblastdetails = {}
					alloclastdetails = {}

					syncjobsstructure = {}

					syncperiodiccounter = 0
					allocperiodiccounter = 0

					synccounter = 0
					syncjobfound = False

					#location for the cache dir for sync 
					synccachedir     = os.path.join(cachedir,'job_'+sync_job_name)					

					if not os.path.exists(synccachedir): 
						logging.debug('cannot find job cache dir:'+synccachedir)
					else:			
						for file in os.listdir(synccachedir):
							if file == 'job_'+sync_job_name+'.json':
								syncjobfound = True
								synccachefile = os.path.join(synccachedir,file)
								with open(synccachefile) as f:
									logging.debug('loading cached info job file:'+synccachefile)
									jobdata = json.load(f)
									if jobdata['Stop']: syncsched = 'paused'
									if not syncjobsstructure.has_key('job'):
										syncjobsstructure['job'] = {}
									syncjobsstructure['job'] = jobdata

							if file.startswith("periodic-"):
								synccachefile = os.path.join(synccachedir,file)
								with open(synccachefile) as f:
									logging.debug('loading cached info periodic file:'+synccachefile)
									jobdata = json.load(f)
									if file.split('-')[1] > syncperiodiccounter:										
										syncstatus = jobdata['Status']
										joblastdetails = jobdata
										syncperiodiccounter = file.split('-')[1]
									if not syncjobsstructure.has_key('periodics'):
										syncjobsstructure['periodics'] = {}
									syncjobsstructure['periodics'][jobdata['ID']] = {}											
									syncjobsstructure['periodics'][jobdata['ID']] = jobdata
									synccounter+=1

							if file.startswith("alloc_"):
								syncalloccachefile = os.path.join(synccachedir,file)
								with open(syncalloccachefile) as f:
									logging.debug('loading cached info alloc file:'+syncalloccachefile)
									allocdata = json.load(f)
									if allocdata['CreateTime'] > allocperiodiccounter:
										allocperiodiccounter = allocdata['CreateTime'] 
										alloclastdetails = allocdata
									if not syncjobsstructure.has_key('allocs'):
										syncjobsstructure['allocs'] = {}										
									syncjobsstructure['allocs'][allocdata['ID']] = {}
									syncjobsstructure['allocs'][allocdata['ID']] = allocdata

							if file.startswith("log_"):
								synclogcachefile = os.path.join(synccachedir,file)
								logallocid = file.replace('log_','').replace('.log','')
								logging.debug('loading cached info log file:'+synclogcachefile)
								statsresults = parse_stats_from_log('file',synclogcachefile)
								if 'time' in statsresults.keys(): 
									synctime = statsresults['time']
								if not syncjobsstructure.has_key('logs'):
									syncjobsstructure['logs'] = {}
								syncjobsstructure['logs'][logallocid] = {}										
								syncjobsstructure['logs'][logallocid] = statsresults

					if not syncjobfound: syncsched = '-'
			
					if alloclastdetails: 
						logging.debug("sync job name:"+sync_job_name+" lastjobid:"+joblastdetails['ID']+' allocjobid:'+alloclastdetails['ID'])

						synclogcachefile = os.path.join(synccachedir,'log_'+alloclastdetails['ID']+'.log')
						statsresults = parse_stats_from_log('file',synclogcachefile)
						if 'time' in statsresults.keys(): synctime = statsresults['time']
						if 'lastline' in statsresults.keys(): synclastline = statsresults['lastline']
						
						syncstatus =  alloclastdetails['ClientStatus']
						if joblastdetails['Status'] in ['pending','running']: syncstatus =  joblastdetails['Status']
						if syncstatus == 'complete': syncstatus = 'idle'

						nodeid = ''
						if 'NodeID' in alloclastdetails: nodeid = alloclastdetails['NodeID']
						if nodeid:
							for node in nodes:
								if node['ID'] == nodeid: nodename = node['Name']

					table.add_row([jobname,src,dst,baselinestatus,baselinetime,syncstatus,syncsched,synctime,nodename,synccounter])
					rowcount += 1


					#printing verbose information
					if reporttype == 'verbose':
						#building verbose details table for the job
						verbosetable = PrettyTable()
						verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Copied','Modified','Deleted','Errors','Node','Status',]

						#print general information 
					 	print "JOB:"+jobname
						print "SRC:"+src
						print "DST:"+dst
						print "SYNC CRON:"+jobcron
					 	print "NEXT SYNC:"+syncsched

					 	#for baseline 
					 	if baselinejob and baselinealloc:
			 				task = 'baseline'
				 			try:
				 				starttime = baselinealloc['TaskStates']['baseline']['StartedAt']
				 				starttime = starttime.split('T')[0]+' '+starttime.split('T')[1].split('.')[0]
				 			except:
				 				starttime = '-'

				 			try:
				 				endtime = baselinealloc['TaskStates']['baseline']['FinishedAt']
				 				endtime = endtime.split('T')[0]+' '+endtime.split('T')[1].split('.')[0]
				 			except:
				 				endtime = '-'

				 			try:
				 				duration = baselinelog['time']
				 			except:
				 				duration = '-'

				 			try:
				 				scanned = baselinelog['scanned']
				 			except:
				 				scanned = '0'
				 				
				 			try:
				 				copied = baselinelog['copied']
				 			except:
				 				copied = '0'

				 			try:
				 				deleted = baselinelog['gone']
				 			except:
				 				deleted = '0'

				 			try:
				 				modified = baselinelog['modified']
				 			except:
				 				modified = '0'						 										 				

				 			try:
				 				errors = baselinelog['errors']
				 			except:
				 				errors = '0'

							try:
								nodeid = baselinealloc['NodeID']
								if nodeid:
									for node in nodes:
										if node['ID'] == nodeid: nodename = node['Name']
							except:
								nodeid = ''

				 			try:
					 			baselinestatus =  baselinealloc['ClientStatus']
								if baselinejob['Status'] in ['pending','running']: baselinestatus =  baselinejob['Status']
							except:
								baselinestatus = '-'

							if not phasefilter or phasefilter == task:
				 				verbosetable.add_row([task,starttime,endtime,duration,scanned,copied,modified,deleted,errors,nodename,baselinestatus])
				 				if displaylogs:
									verbosetable.border = False
									verbosetable.align = 'l'
									print verbosetable
									print ""
									if 'content' in baselinelog:
										print baselinelog['content']
									else:
										print "log is not avaialble"
									print ""
									print ""
									verbosetable = PrettyTable()
									verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Copied','Modified','Deleted','Errors','Node','Status',]

					 	#for each periodic 
					 	counter = 1
					 	if 'periodics' in syncjobsstructure.keys():
						 	for periodic in sorted(syncjobsstructure['periodics'].keys()):
						 		currentperiodic = syncjobsstructure['periodics'][periodic]
						 		for allocid in syncjobsstructure['allocs']:
						 			if syncjobsstructure['allocs'][allocid]['JobID'] == periodic:
						 				currentalloc = syncjobsstructure['allocs'][allocid]
						 				currentlog = {}
						 				if allocid in syncjobsstructure['logs'].keys():
						 					currentlog = syncjobsstructure['logs'][allocid]

						 				task = 'sync' + str(counter)
						 				counter+=1

							 			try:
							 				starttime = currentalloc['TaskStates']['sync']['StartedAt']
							 				starttime = starttime.split('T')[0]+' '+starttime.split('T')[1].split('.')[0]
							 			except:
							 				starttime = '-'

							 			try:
							 				endtime = currentalloc['TaskStates']['sync']['FinishedAt']
							 				endtime = endtime.split('T')[0]+' '+endtime.split('T')[1].split('.')[0]
							 			except:
							 				endtime = '-'

							 			try:
							 				duration = currentlog['time']
							 			except:
							 				duration = '-'

							 			try:
							 				scanned = currentlog['scanned']
							 			except:
							 				scanned = '0'
							 				
							 			try:
							 				copied = currentlog['copied']
							 			except:
							 				copied = '0'

							 			try:
							 				deleted = currentlog['gone']
							 			except:
							 				deleted = '0'

							 			try:
							 				modified = currentlog['modified']
							 			except:
							 				modified = '0'						 										 				

							 			try:
							 				errors = currentlog['errors']
							 			except:
							 				errors = '0'	

										try:
											nodeid = baselinealloc['NodeID']
											if nodeid:
												for node in nodes:
													if node['ID'] == nodeid: nodename = node['Name']
										except:
											nodeid = ''

							 			try:
								 			syncstatus =  currentalloc['ClientStatus']
											if currentperiodic['Status'] in ['pending','running']: syncstatus =  currentperiodic['Status']
										except:
											syncstatus = '-'
										
										if not phasefilter or phasefilter == task:
						 					verbosetable.add_row([task,starttime,endtime,duration,scanned,copied,modified,deleted,errors,nodename,syncstatus])
							 				if displaylogs:
												verbosetable.border = False
												verbosetable.align = 'l'
												print verbosetable
												print ""
												if 'content' in currentlog:
													print currentlog['content']
												else:
													print "log is not avaialble"
												print ""
												print ""
												verbosetable = PrettyTable()
												verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Copied','Modified','Deleted','Errors','Node','Status',]

						#print the table 
						verbosetable.border = False
						verbosetable.align = 'l'
						print verbosetable
						print ""
						print ""	


					# verbosedetails = []

					# #printing verbose information 
					# if reporttype == 'verbose':
					#  	print "JOB Name:"+jobname
					# 	print "SRC:"+src
					# 	print "DST:"+dst
					# 	print "SYNC CRON:"+jobcron
					#  	print "NEXT SYNC:"+syncsched
						
					# 	baselinestatsdir = os.path.join(xcpindexespath,xcpindexname,'reports')
					# 	baselinestatsjsonfile = ''
					# 	try:			
					# 		for file in os.listdir(baselinestatsdir):
					# 			if file.endswith('.stats.json'):
					# 				baselinestatsjsonfile = os.path.join(baselinestatsdir,file)
					# 				with open(baselinestatsjsonfile, 'r') as f:
					# 					baselinestats = json.load(f)
					# 					verbosedetails.append(baselinestats)
					# 	except:
					# 		logging.debug('cannot find baseline job stats file:'+baselinestatsdir)

					# 	syncstatsdir = os.path.join(xcpindexespath,xcpindexname,'sync','reports')
					# 	#try:
					# 	os.chdir(syncstatsdir)
					# 	syncfiles = filter(os.path.isfile, os.listdir(syncstatsdir))
					# 	syncfiles = [os.path.join(syncstatsdir, f) for f in syncfiles] # add path to each file
					# 	syncfiles.sort(key=lambda x: os.path.getmtime(x))						
					# 	for file in syncfiles:
					# 		if file.endswith('.stats.json'):
					# 			syncstatsjsonfile = os.path.join(syncstatsdir,file)
					# 			if os.path.getsize(file) > 0:
					# 				with open(syncstatsjsonfile, 'r') as f:
					# 					syncstats = json.load(f)
					# 					verbosedetails.append(syncstats)
					# 	#except:
					# 	#	logging.debug('cannot find sync job stats files in dir:'+syncstatsdir)


					# 	counter = 0
					# 	for phase in verbosedetails:
					# 		try:
					# 			count   = phase['stats']['count']
					# 		except:
					# 			count = '-'
					# 		try:
					# 			sizehuman = size(phase['stats']['dataCopied'])+'B'
					# 		except:
					# 			sizehuman = '-'
							
					# 		try:
					# 			started = phase['date']
					# 		except:
					# 			started = '-'

					# 		try:
					# 			duration = sec_to_time(phase['stats']['duration'])
					# 		except:
					# 			duration = '-'

					# 		#pp.pprint(phase)
					# 		#print(phase['summary'])
					# 		task = 'sync'
					# 		if counter == 0: task = 'baseline'
					# 		counter += 1

					# 		if syncstatus == 'failed':
					# 			try:
					# 				syncstatus = syncstatus+'('+syncjobsstructure['logs'][alloclastdetails['ID']]['lastline']+')'
					# 			except:
					# 				syncstatus = syncstatus							
						
					# 		verbosetable.add_row([task,count,sizehuman,started,duration,baselinestatus,error])						

						

					
	#dispaly general report
	if rowcount > 0 and reporttype == 'general':
		table.border = False
		table.align = 'l'
		print table
	elif reporttype == 'general':
		print "no data found"

#update nomad job status (pause,resume)
def update_nomad_job_status(action):

	if action == 'pause': newstate = True
	if action == 'resume': newstate = False
	
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

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
					nomadjobname  = jobdetails['sync_job_name']
					baselinejobname  = jobdetails['baseline_job_name']
				
					job = {}
					try:	
						job = n.job.get_job(nomadjobname)
					except:
						job = ''
					
					if not job:
						logging.warning("job name:"+nomadjobname+" doesn't exists") 
					
					else:
						baselinestatus = check_baseline_job_status(baselinejobname)
						
						syncjobdetails = {}
						try:
							syncjobdetails = n.job.get_job(nomadjobname)
						except:
							logging.error("cannot get job:"+nomadjobname+" details")

						jobfile = os.path.join(jobdir,nomadjobname+'.hcl')		
						if not os.path.exists(jobfile): 
							logging.warning("log file"+jobfile+" for job:"+nomadjobname+" could not be found, please run init again") 
							exit (1)

						nomadjobjson = subprocess.check_output([ nomadpath, 'run','-output',jobfile])
						nomadjobdict = json.loads(nomadjobjson)

						currentstopstatus = 'pause'
						if syncjobdetails["Stop"] != True : currentstopstatus = 'resume' 
							
						if action == 'resume' and baselinestatus != 'Baseline Is Complete' and currentstopstatus == 'pause':
							logging.warning("cannot resume job:"+nomadjobname+" status changed to:"+action+"since baseline is not complete") 
						elif action in ['pause','resume'] and currentstopstatus != action:
							nomadjobdict["Job"]["Stop"] = newstate

							logging.info("job name:"+nomadjobname+" status changed to:"+action) 
							nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
							try:
								job = n.job.get_job(nomadjobname)
							except:
								logging.error("job:"+nomadjobname+" update failed") 
								exit(1)
						elif action in ['pause','resume'] and currentstopstatus == action:
							logging.info("job name:"+nomadjobname+" is already:"+action) 
						elif action == 'syncnow':
							if baselinestatus != 'Baseline Is Complete':
								logging.warning("cannot syncnow since baseline status for:"+nomadjobname+' is:'+baselinestatus)
							else:
								logging.info("starting syncnow job:"+nomadjobname) 
								if currentstopstatus == 'pause':									
									logging.debug("temporary resuming job:"+nomadjobname+" to allow syncnow") 
									nomadjobdict["Job"]["Stop"] = False
									nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
									try:
										job = n.job.get_job(nomadjobname)
									except:
										logging.error("job:"+nomadjobname+" update failed") 
										exit(1)

								logging.debug("issuing periodic force update on job:"+nomadjobname)
								response = requests.post(nomadapiurl+'job/'+nomadjobname+'/periodic/force')	
								if not response.ok:
									logging.error("job:"+nomadjobname+" syncnow failed") 
									exit(1)		

								if currentstopstatus == 'pause':									
									logging.debug("returning job:"+nomadjobname+" to pause state") 
									nomadjobdict["Job"]["Stop"] = True
									nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
									try:
										job = n.job.get_job(nomadjobname)
									except:
										logging.error("job:"+nomadjobname+" update failed") 
										exit(1)

#query user for yes no question
def query_yes_no(question, default="no"):
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")

#delete nomad job by prefix
def delete_job_by_prefix(prefix):
	response = requests.get(nomadapiurl+'jobs?prefix='+prefix)	
	if not response.ok:
		logging.warning("could not get jobs prefixed by:"+prefix) 
	else:
		nomadjobs = json.loads(response.content)
		for nomadjob in nomadjobs:
			response = requests.get(nomadapiurl+'job/'+nomadjob['ID']+'/allocations')

			if not response.ok:
				logging.warning("could not get allocations for:"+nomadjob['ID']) 		
			else:
				nomadjoballocation = json.loads(response.content)
				for nomadjoballocation in nomadjoballocation:
					allocationlogs = os.path.join(xcprepopath,'tmpreports','alloc',nomadjoballocation['ID'])
					if os.path.exists(allocationlogs):
						try:
							logging.debug('trying to delete temp alloc log directory:'+allocationlogs)
							rmout = shutil.rmtree(allocationlogs) 
						except:
							logging.debug('could not delete temp alloc directory'+allocationlogs)
							exit(1)

			logging.debug("delete job:"+nomadjob['ID'])
			response = requests.delete(nomadapiurl+'job/'+nomadjob['ID']+'?purge=true')				
			if not response.ok:
				logging.error("can't delete job:"+nomadjob['ID']) 
				exit(1)

#delete jobs 
def delete_jobs(forceparam):

	jobsdictcopy = copy.deepcopy(jobsdict)
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.warning("job config directory:" + jobdir + " not exists. please init first") 
			
			for src in jobsdict[jobname]:
				if srcfilter == '' or srcfilter == src:
					jobdetails = jobsdict[jobname][src]
					
					dst	          = jobdetails['dst']
					srcbase       = jobdetails['srcbase']
					dstbase       = jobdetails['dstbase']
					syncnomadjobname  = jobdetails['sync_job_name']
					baselinejobname  = jobdetails['baseline_job_name']

					force = forceparam
					if not force: force = query_yes_no("delete job for source:"+src,'no')
					if force:
						logging.info("delete job for source:"+src) 
						#delete baseline jobs 
						delete_job_by_prefix(baselinejobname)
						
						#delete sync jobs 
						delete_job_by_prefix(syncnomadjobname)

						#delete xcp repo
						indexpath = os.path.join(xcprepopath,'catalog','indexes',jobsdict[jobname][src]["xcpindexname"])
						if os.path.exists(indexpath):
							logging.debug("delete xcp repo from:"+indexpath)
							try:
								rmout = shutil.rmtree(indexpath) 
							except:
								logging.error("could not delete xcp repo from:"+indexpath) 

						baselinecachedir = os.path.join(cachedir,'job_'+baselinejobname)
						if os.path.exists(baselinecachedir):
							logging.debug("delete baseline cache dir:"+baselinecachedir)
							try:
								rmout = shutil.rmtree(baselinecachedir) 
							except:
								logging.error("could not delete baseline cache dir:"+baselinecachedir)

						synccachedir = os.path.join(cachedir,'job_'+syncnomadjobname)
						if os.path.exists(synccachedir):
							logging.debug("delete sync cache dir:"+synccachedir)
							try:
								rmout = shutil.rmtree(synccachedir) 
							except:
								logging.error("could not delete sync cache dir:"+synccachedir)

						#delete entry from jobdict
						del jobsdictcopy[jobname][src]
						#dumping jobsdict to json file 
						try:
							with open(jobdictjson, 'w') as fp:
								json.dump(jobsdictcopy, fp)
							fp.close()
						except:
							logging.error("cannot write job json file:"+jobdictjson)
							exit(1)						

#check if nomad is available + run the xcption_gc_system job if not avaialble 
def check_nomad():
	response = requests.get(nomadapiurl+'nodes')	
	if not response.ok:
		logging.error("could not contact nomad cluster, please make sure this node is part of the cluster")
		exit(1)
	else:
		nodes = json.loads(response.content)
		for node in nodes:
			if node['Status'] != 'ready':
				logging.warning("node:"+node['Name']+' status is:'+node['Status'])
			else:
				logging.debug("nomad node status:"+node['Name']+' status:'+node['Status'])
		response = requests.get(nomadapiurl+'job/xcption_gc_system')
		if not response.ok:
			if response.content == "job not found":
				logging.debug("xcption_gc_system job is not running, starting it now")

				#loading job ginga2 templates 
				templates_dir = ginga2templatedir
				env = Environment(loader=FileSystemLoader(templates_dir) )
				

				try:
					gc_template = env.get_template('xcption_gc_system.txt')
				except:
					logging.error("could not find template file: " + os.path.join(templates_dir,'xcption_gc_system.txt'))
					exit(1)
				
				#creating the jobs directory
				xcptiongcsystemhcldir = jobsdir
				if not os.path.isdir(xcptiongcsystemhcldir):
					try:
						os.mkdir(xcptiongcsystemhcldir)
					except:
						logging.error("could not create directoy:" + xcptiongcsystemhcldir)
						exit (1)
				xcptiongcsystemhcl = os.path.join(jobsdir,'xcption_gc_system.hcl')
				xcptiongcsystemsh = os.path.join(root,'system','xcption_gc_system.sh')

				#creating gc job 
				logging.debug("creating gc job file: " + xcptiongcsystemhcl)				
				with open(xcptiongcsystemhcl, 'w') as fh:
					fh.write(gc_template.render(
						xcption_gc_system_sh_path=xcptiongcsystemsh
					))				

				start_nomad_job_from_hcl(xcptiongcsystemhcl,'xcption_gc_system')
			else:
				logging.debug("could not contact nomad cluster, please make sure this node is part of the cluster")
				exit(1)
		else:
			logging.debug("xcption_gc_system job is running")

#used to parse nomad jobs to files, will be used as a cache in case of nomad GC removed ended jobs 
def parse_nomad_jobs_to_files ():
	#get nomad allocations 
	jobs = {}
	allocs = {}
	nodes = {}
	
	try:
		jobs  = n.jobs.get_jobs()
	except:
		logging.error('cannot get nomad job list')
		exit(1)
	try:
		allocs = n.allocations.get_allocations()
	except:
		logging.error('cannot get alloc list')
		exit(1)
	try:
		nodes = n.nodes.get_nodes()
	except:
		logging.error('cannot get node list')
		exit(1)

	if not os.path.isdir(cachedir):
		os.mkdir(cachedir)

	lockcounter = 0
	lockfile = os.path.join(cachedir,'nomadlock')
	while os.path.exists(lockfile) and lockcounter <= 3:
		logging.debug("delaying cache update since another update is running (lock file:"+lockfile+" exists)")
		time.sleep(1)
		lockcounter+=1

	#creating the lock file 
	try:
		open(lockfile, 'w').close()
	except:
		logging.debug("cannot create lock file:"+lockfile)

	for job in jobs:
		jobdir = os.path.join(cachedir,'job_'+job['ID'])	

		if len(job['ID'].split('/')) == 1:
			if not os.path.isdir(jobdir):
				logging.debug("creating dir:"+jobdir)
				try:
					logging.debug("creating directory:"+jobdir)
					os.mkdir(jobdir)
				except:
					logging.error("cannot create dir:"+jobdir)
					exit(1)
		else:
			#because the sub jobs contains the job name
			jobdir = os.path.join(cachedir,'job_'+job['ID'].split('/')[0])

		jobjsonfile = os.path.join(jobdir,'job_'+job['ID']+'.json')		
		
		if len(job['ID'].split('/')) > 1:
			jobjsonfile = os.path.join(jobdir,job['ID'].split('/')[1])

		try:
			with open(jobjsonfile, 'w') as fp:
			    json.dump(job, fp)
			    logging.debug("dumping job   to json file:"+jobjsonfile)		
		except:
			logging.error("cannot create file:"+jobjsonfile)
			exit(1)

		logging.debug("caching job:"+job['ID'])

		for alloc in allocs:		
			if alloc['JobID'] == job['ID']:
				allocjsonfile = os.path.join(jobdir,'alloc_'+alloc['ID']+'.json')				
				try:
					with open(allocjsonfile, 'w') as fp:
					    json.dump(alloc, fp)
					    logging.debug("dumping alloc to json file:"+allocjsonfile)		
				except:
					logging.error("cannot create file:"+allocjsonfile)
					exit(1)


				task = 'sync'	
				if alloc['TaskGroup'].startswith('baseline'): task='baseline'

				#try to get the log file using api
				response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+'&type=stderr&plain=true')
				if response.ok and re.search("\d", response.content, re.M|re.I):
					logging.debug("log for job:"+alloc['ID']+" is avaialble using api")
					alloclogfile = os.path.join(jobdir,'log_'+alloc['ID']+'.log')
					try:
						with open(alloclogfile, 'w') as fp:
							fp.write(response.content)
							logging.debug("dumping log to log file:"+alloclogfile)		
					except:
						logging.error("cannot create file:"+alloclogfile)
						exit(1)

				logging.debug("caching alloc:"+alloc['ID'])

	#running nomad garbage collection
	# logging.debug("running nomad garbage collector")	
	# response = requests.put(nomadapiurl+'system/gc')
	# if response.ok:	
	# 	logging.debug("nomad garbage collector complete successfully")	
	# else:
	# 	logging.debug("nomad garbage collector did not complete successfully "+response.content)	

	#removing the lock file 
	try:
		logging.debug("removing lock file:"+lockfile)
		os.remove(lockfile)
	except:
		logging.debug("cannot remove lock file:"+lockfile)
#####################################################################################################
###################                        MAIN                                        ##############
#####################################################################################################


if not os.path.isdir(cachedir):
	try:
		os.mkdir(cachedir)
	except:
		logging.error("could not create cache directoy:" + cachedir)
		exit (1)

#filter by job or jobname
jobfilter = ''
if hasattr(args, 'job'): 
	if args.job != None:
		jobfilter = args.job

#filter by job or src
srcfilter = ''
if hasattr(args, 'source'): 
	if args.source != None:
		srcfilter = args.source

#filter by phase (relevant to status)
phasefilter = ''
if hasattr(args,'phase'):
	if args.phase != None:
		phasefilter = args.phase

#check nomad avaialbility
check_nomad()

if args.subparser_name == 'nomad':
	parse_nomad_jobs_to_files()
	exit (0)


if args.subparser_name == 'load':
	parse_csv(args.csvfile)
	create_nomad_jobs()

#load jobs from json file
load_jobs_from_json(jobdictjson)

if args.subparser_name == 'baseline':
	start_nomad_jobs('baseline')

if args.subparser_name == 'sync':
	start_nomad_jobs('sync')

if args.subparser_name == 'status' and not args.verbose:
	parse_nomad_jobs_to_files()
	create_status('general')
if args.subparser_name == 'status' and args.verbose:
	parse_nomad_jobs_to_files()
	create_status('verbose',args.logs)

if args.subparser_name in ['pause','resume','syncnow']:
	update_nomad_job_status(args.subparser_name)

if args.subparser_name == 'delete':
	delete_jobs(args.force)