#!/usr/bin/python

# XCPtion - NetApp XCP wrapper 
# Written by Haim Marko 
# Enjoy

#change log 
#2.0.7.0 - scan filesystme 

#version 
version = '2.0.7.0'

import csv
import argparse
import re
import logging
import logging.handlers
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
import fnmatch
import socket

from hurry.filesize import size
from prettytable import PrettyTable
from jinja2 import Environment, FileSystemLoader
from treelib import Node, Tree

pp = pprint.PrettyPrinter(indent=1)

#general settings
dcname = 'DC1'

#default windows tool
defaultwintool = 'xcp'
#xcp path location
xcppath = '/usr/local/bin/xcp'
#xcp windows location
xcpwinpath = 'C:\\NetApp\\XCP\\xcp.exe'
xcpwincopyparam = "-preserve-atime -acl -parallel 8"
xcpwinsyncparam = "-nodata -preserve-atime -acl -parallel 8"
xcpwinverifyparam = "-v -l -nodata -noatime -preserve-atime -parallel 8"

#robocopy windows location
robocopywinpath = 'C:\\NetApp\\XCP\\robocopy_wrapper.ps1'
robocopywinpathasses = 'C:\\NetApp\\XCP\\robocopy_wrapper.ps1'
robocopyargs = ' /COPY:DATSO /MIR /NP /DCOPY:DAT /MT:32 /R:0 /W:0 /TEE /V /BYTES /NDL '

#location of the script 
root = os.path.dirname(os.path.abspath(__file__))

#xcp repo and cache dir loaction 
xcprepopath = os.path.join(root,'system','xcp_repo')

#xcp indexes path 
xcpindexespath = os.path.join(xcprepopath,'catalog','indexes')

#cache dir for current state 
cachedir = os.path.join(xcprepopath,'nomadcache')
#cachedir = os.path.join(root,'nomadcache')

#smartasses dir for current state 
smartassesdir = os.path.join(xcprepopath,'smartasses')

#path to nomad bin 
nomadpath = '/usr/local/bin/nomad'

#location for the jobs dir
jobsdir = os.path.join(xcprepopath,'jobs') 

#exclude dirictory files location
excludedir = os.path.join(xcprepopath,'excludedir') 

#file containing loaded jobs 
jobdictjson = os.path.join(jobsdir,'jobs.json')

#smartasses json jobs file
smartassesjobdictjson = os.path.join(smartassesdir,'smartassesjobs.json')

#job template dirs
ginga2templatedir = os.path.join(root,'template') 

#log file location
logdirpath = os.path.join(root,'log') 
logfilepath = os.path.join(logdirpath,'xcption.log')

#creating the logs directory
if not os.path.isdir(logdirpath):
	try:
		os.mkdir(logdirpath)
	except:
		logging.error("could not create log directoy:" + logdirpath)
		exit (1)

#default nomad job properties 
defaultjobcron = "0 0 * * * *" #nightly @ midnight
defaultcpu = 300
defaultmemory = 800

#max logs for status -l 
maxloglinestodisplay = 200

#smartasses globals 

minsizekfortask_minborder = 0.5*1024*1024*1024 #512GB
mininodespertask_minborder = 100000 

maxjobs = 100

totaljobssizek = 0
totaljobsinode = 0
totaljobscreated = 0

parent_parser = argparse.ArgumentParser(add_help=False)

parser = argparse.ArgumentParser()
parser.add_argument('-v','--version', help="print version information", action='store_true')
parser.add_argument('-d','--debug',   help="log debug messages to console", action='store_true')
subparser = parser.add_subparsers(dest='subparser_name', help='sub commands that can be used')

# create the sub commands 
parser_nodestatus   = subparser.add_parser('nodestatus',help='display cluster nodes status',parents=[parent_parser])	
parser_status       = subparser.add_parser('status',    help='display status',parents=[parent_parser])	
parser_asses        = subparser.add_parser('asses',     help='asses fielsystem and create csv file',parents=[parent_parser])
parser_load         = subparser.add_parser('load',      help='load/update configuration from csv file',parents=[parent_parser])
parser_baseline     = subparser.add_parser('baseline',  help='start baseline (xcp copy)',parents=[parent_parser])
parser_sync         = subparser.add_parser('sync',      help='start schedule updates (xcp sync)',parents=[parent_parser])
parser_syncnow      = subparser.add_parser('syncnow',   help='initiate sync now',parents=[parent_parser])
parser_pause        = subparser.add_parser('pause',     help='disable sync schedule',parents=[parent_parser])
parser_resume       = subparser.add_parser('resume',    help='resume sync schedule',parents=[parent_parser])
parser_abort        = subparser.add_parser('abort',     help='abort running task')
parser_verify       = subparser.add_parser('verify',    help='start verify to validate consistency between source and destination (xcp verify)')
parser_delete       = subparser.add_parser('delete',    help='delete existing config',parents=[parent_parser])
parser_modifyjob    = subparser.add_parser('modifyjob', help='move tasks to diffrent group',parents=[parent_parser])
parser_nomad        = subparser.add_parser('nomad',     description='hidden command, usded to update xcption nomad cache',parents=[parent_parser])

parser_status.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_status.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_status.add_argument('-t','--jobstatus',help="change the scope of the command to specific job status ex:complete,running,failed,pending,aborted", required=False,type=str,metavar='jobstatus')
parser_status.add_argument('-v','--verbose',help="provide verbose per phase info", required=False,action='store_true')
parser_status.add_argument('-p','--phase',help="change the scope of the command to specific phase ex:baseline,sync#,verify#,lastsync (requires -v/--verbose)", required=False,type=str,metavar='phase')
parser_status.add_argument('-n','--node',help="change the scope of the command to specific node (requires -v/--verbose)", required=False,type=str,metavar='node')
parser_status.add_argument('-e','--error',help="change the scope of the command to jobs with errors (requires -v/--verbose)", required=False,action='store_true')
parser_status.add_argument('-l','--logs',help="display job logs", required=False,action='store_true')

parser_asses.add_argument('-s','--source',help="source nfs path (nfssrv:/mount)",required=True,type=str)
parser_asses.add_argument('-d','--destination',help="destintion nfs path (nfssrv:/mount)",required=True,type=str)
parser_asses.add_argument('-l','--depth',help="filesystem depth to create jobs, range of 1-12",required=True,type=int)
parser_asses.add_argument('-c','--csvfile',help="output CSV file",required=True,type=str)
parser_asses.add_argument('-p','--cpu',help="CPU allocation in MHz for each job",required=False,type=int)
parser_asses.add_argument('-m','--ram',help="RAM allocation in MB for each job",required=False,type=int)
parser_asses.add_argument('-r','--robocopy',help="use robocopy instead of xcp for windows jobs", required=False,action='store_true')
parser_asses.add_argument('-u','--failbackuser',help="failback user required for xcp for windows jobs, see xcp.exe copy -h", required=False,type=str)
parser_asses.add_argument('-g','--failbackgroup',help="failback group required for xcp for windows jobs, see xcp.exe copy -h", required=False,type=str)
parser_asses.add_argument('-j','--job',help="xcption job name", required=False,type=str,metavar='jobname')

parser_load.add_argument('-c','--csvfile',help="input CSV file with the following columns: Job Name,SRC Path,DST Path,Schedule,CPU,Memory",required=True,type=str)
parser_load.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_load.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_baseline.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_baseline.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_baseline.add_argument('-f','--force',help="force re-baseline", required=False,action='store_true')

parser_sync.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_sync.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_syncnow.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_syncnow.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_pause.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_pause.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_resume.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_resume.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_abort.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_abort.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_abort.add_argument('-t','--type',help="spefify the type of job to abort, can be baseline,sync or verify", choices=['baseline','sync','verify'],required=True,type=str,metavar='type')
parser_abort.add_argument('-f','--force',help="force abort", required=False,action='store_true')

parser_verify.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_verify.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_delete.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_delete.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_delete.add_argument('-f','--force',help="force delete", required=False,action='store_true')

parser_modifyjob.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_modifyjob.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_modifyjob.add_argument('-t','--tojob',help="move selected tasks to this job", required=True,type=str,metavar='tojob')
parser_modifyjob.add_argument('-f','--force',help="force move", required=False,action='store_true')


parser_smartasses   = subparser.add_parser('smartasses',help='scan src to create jobs based on capacity and file count (nfs only)',parents=[parent_parser])

action_subparser = parser_smartasses.add_subparsers(title="action",dest="smartasses_command")                                                                                                               
parser_smartasses_start     = action_subparser.add_parser('start',help='scan src to create jobs based on capacity and file count (nfs only)',parents=[parent_parser])
parser_smartasses_status    = action_subparser.add_parser('status',help='display scan status and filesystem info',parents=[parent_parser])
parser_smartasses_createcsv = action_subparser.add_parser('createcsv',help='create csv job file based on the scan results',parents=[parent_parser])

parser_smartasses_start.add_argument('-s','--source',help="source nfs path (nfssrv:/mount)",required=True,type=str)
parser_smartasses_start.add_argument('-l','--depth',help="filesystem depth to create jobs, range of 1-12",required=True,type=int)
parser_smartasses_start.add_argument('-k','--locate-cross-job-hardlink',help="located hardlinks that will be converted to regular files when splited to diffrent jobs",required=False,action='store_true')

#check capacity parameter 
def checkcapacity (capacity):
	matchObj = re.match("^(\d+)(KB|MB|GB|TB)$",capacity)
	if not matchObj:
		raise argparse.ArgumentTypeError("invalid capacity")
	return capacity

#convert K to human readable 
def k_to_hr (k):

	hr = format(k,',')+' KiB'
	if 1024 <= k <= 1024*1024:
		hr = format(int(k/1024),',')+' MiB'
	elif 1024*1024 <= k <= 1024*1024*1024:
		hr = format(int(k/1024/1024),',')+' GiB'
	elif 1024*1024*1024*1024 <= k:
		hr = format(int(k/1024/1024/1024),',')+' TiB'
	return hr	

parser_smartasses_status.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_smartasses_status.add_argument('-i','--min-inodes',help="minimum required inodes per task default is:"+format(mininodespertask_minborder,','), required=False,type=int,metavar='maxinodes')
parser_smartasses_status.add_argument('-c','--min-capacity',help="minimum required capacity per task default is:"+k_to_hr(minsizekfortask_minborder), required=False,type=checkcapacity,metavar='mincapacity')
parser_smartasses_status.add_argument('-t','--tasks',help="provide verbose task information per suggested path", required=False,action='store_true')
parser_smartasses_status.add_argument('-l','--hardlinks',help="provide hardlink conflict information per suggested path", required=False,action='store_true')



#parser_smartasses_status.add_argument('-l','--logs',help="display job logs", required=False,action='store_true')
#parser_smartasses_status.add_argument('-v','--verbose',help="provide verbose per phase info", required=False,action='store_true')
#parser_smartasses_status.add_argument('-d','--destination',help="destintion nfs path (nfssrv:/mount)",required=True,type=str)
#parser_smartasses.add_argument('-l','--depth',help="filesystem depth to create jobs, range of 1-12",required=True,type=int)
#parser_smartasses.add_argument('-c','--csvfile',help="output CSV file",required=True,type=str)
#parser_smartasses.add_argument('-p','--cpu',help="CPU allocation in MHz for each job",required=False,type=int)
#parser_smartasses.add_argument('-m','--ram',help="RAM allocation in MB for each job",required=False,type=int)
#parser_smartasses.add_argument('-r','--robocopy',help="use robocopy instead of xcp for windows jobs", required=False,action='store_true')
#parser_smartasses.add_argument('-u','--failbackuser',help="failback user required for xcp for windows jobs, see xcp.exe copy -h", required=False,type=str)
#parser_smartasses.add_argument('-g','--failbackgroup',help="failback group required for xcp for windows jobs, see xcp.exe copy -h", required=False,type=str)
#parser_smartasses.add_argument('-j','--job',help="xcption job name", required=False,type=str,metavar='jobname')


args = parser.parse_args()

#initialize logging 
log = logging.getLogger()
log.setLevel(logging.DEBUG)
logging.getLogger('requests').setLevel(logging.ERROR)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
formatterdebug = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')

# create file handler which logs even debug messages
#fh = logging.FileHandler(logfilepath)
fh = logging.handlers.RotatingFileHandler(
              logfilepath, maxBytes=1048576, backupCount=5)
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
smartassesdict = {}
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

#load smartasses from json 
def load_smartasses_jobs_from_json (jobdictjson):
	global smartassesdict
	if os.path.exists(jobdictjson):
		try:
			logging.debug("loading existing json file:"+jobdictjson)
			with open(jobdictjson, 'r') as f:
				smartassesdict = json.load(f)
		except:
			logging.debug("could not load existing json file:"+jobdictjson)


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

				if (jobfilter == '' or jobfilter == jobname) and (srcfilter == '' or fnmatch.fnmatch(src, srcfilter)):
	
					cron    = ''
					if 3 < len(row): cron    = row[3] 
					if cron == '':   cron    = defaultjobcron 
					try:
						now = datetime.datetime.now()
						cront = croniter.croniter(cron, now)
					except:
						logging.error("cron format: "+cron+ " for src: "+ src + " is incorrect")
						exit(1)	

					cpu     = '' 
					if 4 < len(row): cpu     = row[4] 
					if cpu == '':    cpu     = defaultcpu 
					
					memory  = ''
					if 5 < len(row): memory  = row[5] 
					if memory == '': memory  = defaultmemory 
                    
					ostype = 'linux'
					if src.__contains__('\\'):
						ostype = 'windows'
					
					tool = defaultwintool
					if 6 < len(row): tool  = row[6]

					failbackuser =''
					if 7 < len(row): failbackuser  = row[7]					

					failbackgroup =''
					if 8 < len(row): failbackgroup  = row[8]	

					excludedirfile = ''
					if 9 < len(row): excludedirfile = os.path.join(excludedir,row[9])
					#check if exclude file exists 
					if excludedirfile != '' and not os.path.isfile(excludedirfile):
						logging.error("exclude dir file:"+excludedirfile+" for src:"+src+" could not be found")
						exit(1)
					
					logging.debug("parsing entry for job:" + jobname	 + " src:" + src + " dst:" + dst + " ostype:" + ostype + " tool:"+tool+" failbackuser:"+failbackuser+" failback group:"+failbackgroup+" exclude dir file:"+excludedirfile) 

					srcbase = src.replace(':/','-_')
					srcbase = srcbase.replace('/','_')
					srcbase = srcbase.replace(' ','-')
					srcbase = srcbase.replace('\\','_')
					srcbase = srcbase.replace('$','_dollar')
					
					dstbase = dst.replace(':/','-_')
					dstbase = dstbase.replace('/','_')
					dstbase = dstbase.replace(' ','-')
					dstbase = dstbase.replace('\\','_')
					dstbase = dstbase.replace('$','_dollar')

					#validate no duplicate src and destination 
					for j in jobsdict:
						for s in jobsdict[j]:
							if j == jobname and s==src and jobsdict[j][s]["dst"] == dst:
								continue 

							if s == src and jobsdict[j][s]["dst"] != dst:
								logging.warning("duplicate source found:" + src+"->"+dst)
								#exit(1)

							if dst == jobsdict[j][s]["dst"]:
								logging.error("duplicate dst path: " + dst)
								exit(1)					

					if not jobname in jobsdict:
						jobsdict[jobname]={}

					if ostype == 'linux':
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
						
					if ostype == 'windows':
						if not re.search('^(\\\\?([^\\/]*[\\/])*)([^\\/]+)$', src):
							logging.error("src path format is incorrect: " + src) 
							exit(1)	
						if not re.search('^(\\\\?([^\\/]*[\\/])*)([^\\/]+)$', dst):
							logging.error("dst path format is incorrect: " + dst)
							exit(1)	

						logging.info("validating src:" + src + " and dst:" + dst+ " cifs paths are avaialble from one of the windows servers") 
						
						pscmd = 'if (test-path "'+src+'") {exit 0} else {exit 1}'
						psstatus = run_powershell_cmd_on_windows_agent(pscmd)['status']
						if  psstatus != 'complete':
							logging.error("cannot validate src:"+src+" using cifs, validation is:"+psstatus)
							exit(1)								
						
						pscmd = 'if (test-path "'+dst+'") {exit 0} else {exit 1}'
						psstatus = run_powershell_cmd_on_windows_agent(pscmd)['status']

						if  psstatus != 'complete':
							logging.error("cannot validate dst:"+dst+" using cifs, validation status is:"+psstatus)
							exit(1)	
							
						srchost = src.split('\\')[2]
						srcpath = src.replace('\\\\'+srchost,'')
						dsthost = dst.split('\\')[2]
						dstpath = dst.replace('\\\\'+dsthost,'')			
					
					baseline_job_name = 'baseline_'+'_'+srcbase
					sync_job_name     = 'sync_'+'_'+srcbase
					verify_job_name     = 'verify_'+'_'+srcbase
					
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
					jobsdict[jobname][src]["verify_job_name"]   = verify_job_name
					jobsdict[jobname][src]["xcpindexname"]      = xcpindexname
					jobsdict[jobname][src]["cron"]   = cron
					jobsdict[jobname][src]["cpu"]    = cpu
					jobsdict[jobname][src]["memory"] = memory
					jobsdict[jobname][src]["ostype"] = ostype
					jobsdict[jobname][src]["tool"] = tool
					jobsdict[jobname][src]["failbackuser"] = failbackuser
					jobsdict[jobname][src]["failbackgroup"] = failbackgroup
					jobsdict[jobname][src]["dcname"] = dcname
					jobsdict[jobname][src]["excludedirfile"] = excludedirfile


					logging.debug("parsed the following relation:"+src+" -> "+dst)

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

	return True

def check_job_status (jobname,log=False):
	jobdetails = {}
	try:	
		jobdetails = n.job.get_job(jobname)
	except:
		jobdetails = None

	if not jobdetails:
		logging.debug("job:"+jobname+" does not exist")
		return False,'',''


	#if job exists retrun the allocation status
	results ={}
	results['stdout'] = ''
	results['stderr'] = ''
	results['status'] = 'unknown'
	allocid = ''

	if jobdetails:
		response = requests.get(nomadapiurl+'job/'+jobname+'/allocations')	
		if not response.ok:
			results['status'] =  'failure'
		else:
			jobdetails = json.loads(response.content)
			try:
				results['status'] = jobdetails[0]['ClientStatus']
				allocid = jobdetails[0]['ID']

			except:
				results['status'] = 'unknown'	

	if log == True and (results['status'] == 'complete' or results['status'] == 'failed') and allocid != '':
		response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+jobname+'&type=stdout&plain=true')
		if response.ok:
			logging.debug("stdout log for job:"+jobname+" is avaialble using api")								
			lines = response.content.splitlines()
			if lines:
				results['stdout'] = response.content						
		
		response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+jobname+'&type=stderr&plain=true')
		if response.ok:
			logging.debug("stderr log for job:"+jobname+" is avaialble using api")								
			lines = response.content.splitlines()
			if lines:
				results['stderr'] = response.content	

	return results
	


#run powershell commnad on windows agent
def run_powershell_cmd_on_windows_agent (pscmd,log=False):


	results = {}

	psjobname = pscmd[:15]+str(os.getpid())
	psjobname = psjobname.replace(' ','_')
	psjobname = 'win_'+psjobname
	psjobname = psjobname.replace('}','-')
	psjobname = psjobname.replace('{','-')
	psjobname = psjobname.replace(')','-')
	psjobname = psjobname.replace('(','-')	
	psjobname = psjobname.replace(':/','-_')
	psjobname = psjobname.replace('/','_')
	psjobname = psjobname.replace(' ','-')
	psjobname = psjobname.replace('\\','_')
	psjobname = psjobname.replace('$','_dollar')
	psjobname = psjobname.replace(';','=')
	psjobname = psjobname.replace('\"','_')
	psjobname = psjobname.replace('\'','_')
	psjobname = psjobname.replace(':','-')
	psjobname = psjobname.replace('*','x')


	#loading job ginga2 templates 
	templates_dir = ginga2templatedir
	env = Environment(loader=FileSystemLoader(templates_dir) )
	
	try:
		ps_template = env.get_template('nomad_windows_powershell.txt')
	except:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_windows_powershell.txt'))
		exit(1)

	psjobname = psjobname + os.getpid().__str__()

	pscmd = pscmd.replace('\\','\\\\')
	pscmd = pscmd.replace('\"','\\\"')
	pscmd = pscmd.replace("\'","\\\'")

	#creating create job to validate 
	powershell_job_file = os.path.join('/tmp',psjobname+'.hcl')	
	logging.debug("creating job file: " + powershell_job_file)				
	with open(powershell_job_file, 'w') as fh:
		fh.write(ps_template.render(
			dcname=dcname,
			powershelljob=psjobname,
			cmd=pscmd
		))


	#start job and monitor status'

	psjobstatus = 'not started'
	if start_nomad_job_from_hcl(powershell_job_file, psjobname):
		retrycount = 50
		while retrycount > 0:
			results = check_job_status(psjobname,log)
			retrycount =  retrycount - 1
			if results['status'] == 'failed' or results['status'] == 'complete':
				retrycount = 0
			else:
				time.sleep(1)


	logging.debug("delete job:"+psjobname)
	response = requests.delete(nomadapiurl+'job/'+psjobname+'?purge=true')				
	if not response.ok:
		logging.debug("can't delete job:"+psjobname) 
	
	os.remove(powershell_job_file)
	return results

#create escaped sctring (used for command within hcl files)
def escapestr (str1):
	str1 = str1.replace('\\','\\\\')
	str1 = str1.replace('\"','\\\"')
	str1 = str1.replace("\'","\\\'")
	return str1

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
		verify_template = env.get_template('nomad_verify.txt')
	except:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_scan.txt'))
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
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					
					dst	              = jobdetails['dst']
					srcbase           = jobdetails['srcbase']
					dstbase           = jobdetails['dstbase']
					baseline_job_name = jobdetails['baseline_job_name']
					sync_job_name     = jobdetails['sync_job_name']
					verify_job_name   = jobdetails['verify_job_name']
					xcpindexname      = jobdetails['xcpindexname']	
					jobcron           = jobdetails['cron']
					cpu    			  = jobdetails['cpu']
					memory            = jobdetails['memory']
					ostype			  = jobdetails['ostype']
					tool              = jobdetails['tool']
					failbackuser      = jobdetails['failbackuser']
					failbackgroup     = jobdetails['failbackgroup']
					excludedirfile    = jobdetails['excludedirfile']

					if ostype == 'linux': xcpbinpath = xcppath
					if ostype == 'windows': xcpbinpath = 'powershell'
					
					#creating baseline job 
					baseline_job_file = os.path.join(jobdir,baseline_job_name+'.hcl')	
					logging.info("creating/updating relationship configs for src:"+src)
					logging.debug("creating baseline job file: " + baseline_job_file)				

					
					if ostype == 'linux':  
						if excludedirfile == '':
							cmdargs = "copy\",\"-newid\",\""+xcpindexname+"\",\""+src+"\",\""+dst
						else:
							cmdargs = "copy\",\"-newid\",\""+xcpindexname+"\",\"-match\",\"not paths('"+excludedirfile+"')\",\""+src+"\",\""+dst

					if ostype == 'windows' and tool == 'xcp': 
						cmdargs = escapestr(xcpwinpath+" copy "+xcpwincopyparam+" -fallback-user "+failbackuser+" -fallback-group "+failbackgroup+" \""+src+"\" \""+dst+"\"")
					if ostype == 'windows' and tool == 'robocopy': 
						cmdargs = escapestr(robocopywinpath+ " \""+src+"\" \""+dst+"\""+robocopyargs)
					

					with open(baseline_job_file, 'w') as fh:
						fh.write(baseline_template.render(
							dcname=dcname,
							os=ostype,
							baseline_job_name=baseline_job_name,
							xcppath=xcpbinpath,
							args=cmdargs,
							memory=memory,
							cpu=cpu
						))
					
					#creating sync job 
					sync_job_file = os.path.join(jobdir,sync_job_name+'.hcl')		
					logging.debug("creating sync job file: " + sync_job_file)				
					
					if ostype == 'linux':
						cmdargs = "sync\",\"-id\",\""+xcpindexname
					if ostype == 'windows' and tool == 'xcp': 
						cmdargs = escapestr(xcpwinpath+" sync "+xcpwinsyncparam+" -fallback-user "+failbackuser+" -fallback-group "+failbackgroup+" \""+src+"\" \""+dst)
					if ostype == 'windows' and tool == 'robocopy': 
						cmdargs = escapestr(robocopywinpath+ " \""+src+"\" \""+dst+"\""+robocopyargs)

					with open(sync_job_file, 'w') as fh:
						fh.write(sync_template.render(
							dcname=dcname,
							os=ostype,
							sync_job_name=sync_job_name,
							jobcron=jobcron,
							xcppath=xcpbinpath,
							args=cmdargs,
							memory=memory,
							cpu=cpu					
						))

					#creating verify job
					verify_job_file = os.path.join(jobdir,verify_job_name+'.hcl')	
					logging.debug("creating verify job file: " + verify_job_file)	
					
					if ostype == 'linux':  
						if excludedirfile == '':
							cmdargs = "verify\",\"-v\",\"-noid\",\"-nodata\",\""+src+"\",\""+dst
						else:
							cmdargs = "verify\",\"-v\",\"-noid\",\"-nodata\",\"-match\",\"not paths('"+excludedirfile+"')\",\""+src+"\",\""+dst
					if ostype == 'windows': cmdargs = escapestr(xcpwinpath+' verify '+xcpwinverifyparam+' "'+src+'" "'+dst+'"')
					
					with open(verify_job_file, 'w') as fh:
						fh.write(verify_template.render(
							dcname=dcname,
							os=ostype,
							verify_job_name=verify_job_name,
							xcppath=xcpbinpath,
							args=cmdargs,
							memory=memory,
							cpu=cpu
						))					


def check_baseline_job_status (baselinejobname):

	baselinecachedir = os.path.join(cachedir,'job_'+baselinejobname)

	baselinejob = {}
	try:	
		baselinejob = n.job.get_job(baselinejobname)
	except:
		baselinejob = None

	if not baselinejob and not os.path.exists(baselinecachedir):
		logging.debug("baseline job:"+baselinejobname+" does not exist and cahced folder:"+baselinecachedir+" does not exists")
		return('Baseline Not Exists')

	baselinejobcompleted = 0 
	for file in os.listdir(baselinecachedir):
		if file.startswith("periodic-"):
			baselinecachefile = os.path.join(baselinecachedir,file)
			with open(baselinecachefile) as f:
				logging.debug('loading cached info periodic file:'+baselinecachefile)
				jobdata = json.load(f)
				
				if jobdata['Status'] == 'dead' and not jobdata['Stop'] and jobdata['JobSummary']['Summary'][baselinejobname]['Complete'] == 1: baselinejobcompleted = 1

	if baselinejobcompleted != 1: 
		logging.debug("baseline job:"+baselinejobname+" exists but did not completed") 
		baselinejob = None
		return('baseline not complete')
	else:
		return('baseline is complete')
	

#start nomand job
def start_nomad_jobs(action, force):
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.error("job config directory:" + jobdir + " not exists. please init first") 
				exit (1)
					
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					
					dst	          = jobdetails['dst']
					srcbase       = jobdetails['srcbase']
					dstbase       = jobdetails['dstbase']
					nomadjobname  = jobdetails[action+'_job_name']
					xcpindexname  = jobdetails['xcpindexname']	
					ostype        = jobdetails['ostype']
					tool          = jobdetails['tool']
				
					try:	
						job = n.job.get_job(nomadjobname)
					except:
						job = ''
					
					if job:
						logging.debug("job name:"+nomadjobname+" already exists") 

					forcebaseline = False 
					if action == 'baseline' and job:
						if not force:
							logging.warning("baseline job already exists. use --force to force new baseline") 
							continue
						else:
							if query_yes_no("are you sure you want o rebaseline "+src+" to "+dst+" ?",'no'):
								if ostype == 'linux' and tool == 'xcp':
									logging.info("destroying xcp index for aborted job")
									logging.debug("running the command:"+xcppath+' diag -rmid '+xcpindexname)
									DEVNULL = open(os.devnull, 'wb')
									if subprocess.call( [ xcppath, 'diag', '-rmid', xcpindexname ],stdout=DEVNULL,stderr=DEVNULL):
										logging.debug("failed to delete xcp index:"+xcpindexname)								
								forcebaseline=True

					if (action != 'baseline' and job) or forcebaseline or not job:
						jobfile = os.path.join(jobdir,nomadjobname+'.hcl')		
						if not os.path.exists(jobfile): 
							logging.warning("job:"+nomadjobname+" could not be found, please load first") 
						else:
							logging.info("starting/updating "+action+" job for src:" + src+ " dst:"+dst) 
							nomadjobjson = subprocess.check_output([ nomadpath, 'run','-output',jobfile])
							nomadjobdict = json.loads(nomadjobjson)

							try:
								nomadout = n.job.plan_job(nomadjobname, nomadjobdict)
							except:
								logging.error("job planning failed for job:"+nomadjobname+" please run: nomad job plan "+jobfile+ " for more details") 
								exit(1)

							baselinejobname = jobdetails['baseline_job_name']
							baselinestatus = check_baseline_job_status(baselinejobname)
							
							#if sync job and baseline was not started disable schedule for sync 
							if action == 'sync':
								if baselinestatus != 'baseline is complete':
									logging.warning(action+" will be paused:"+baselinestatus.lower())									
									nomadjobdict["Job"]["Stop"] = True
								else:
									logging.debug("baseline is completed, can start "+action)

							#if sync job and baseline was not started disable schedule for sync 
							if action == 'verify' or action == 'verify':
								if baselinestatus != 'baseline is complete':
									logging.warning(action+" is not possiable:"+baselinestatus.lower())									
									continue
								else:
									logging.debug("baseline is completed, can start "+action)


							nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
							try:
								job = n.job.get_job(nomadjobname)
							except:
								logging.error("job:"+nomadjobname+" creation failed") 
								exit(1)

							#force immediate baseline / verify
							if action == 'baseline' or (action == 'verify' and baselinestatus == 'baseline is complete'):
								response = requests.post(nomadapiurl+'job/'+nomadjobname+'/periodic/force')	
								if not response.ok:
									logging.error("job:"+nomadjobname+" force start failed") 
									exit(1)

#tail n lines of a file 
def tail(file, n=1, bs=1024):
    f = open(file)
    f.seek(0,2)
    l = 1-f.read(1).count('\n')
    B = f.tell()
    while n >= l and B > 0:
            block = min(bs, B)
            B -= block
            f.seek(B, 0)
            l += f.read(block).count('\n')
    f.seek(B, 0)
    l = min(l,n)
    lines = f.readlines()[-l:]
    f.close()
    return lines


#parse stats from xcp logs, logs can be retrived from api or file in the repo
def parse_stats_from_log (type,name,logtype,task='none'):
#def parse_stats_from_log (type,name,task='none',jobstatus='unknow'):
	#output dict
	results = {}
	results['content'] = ''
	lastline = ''
	otherloglastline = ''

	if type == 'file':
		logfilepath = name
		logfilesize = 0

		try:
			logfilesize = os.path.getsize(logfilepath)			

			lines = tail(logfilepath,maxloglinestodisplay)
			seperator = ""
			results['content'] = seperator.join(lines)
			results['logfilepath'] = logfilepath
			results['logfilesize'] = logfilesize

		except:
			logging.debug("cannot read log file:"+logfilepath)	

		#store also other logtype
		otherlogfilepath = name
		if logtype == 'stderr':
			otherlogfilepath = otherlogfilepath.replace('stderr','stdout',1) 
		else:
			otherlogfilepath = otherlogfilepath.replace('stdout','stderr',1) 

		try:
			logfilesize = os.path.getsize(otherlogfilepath)			

			lines = tail(otherlogfilepath,maxloglinestodisplay)
			seperator = ""
			results['contentotherlog'] = seperator.join(lines)
			results['logfileotherpath'] = otherlogfilepath
			results['logfileothersize'] = logfilesize
		except:
			logging.debug("cannot read other log file:"+otherlogfilepath)							
			results['contentotherlog'] = ''


	elif type == 'alloc':						
		#try to get the log file using api
		allocid = name
		response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+task+'&type='+logtype+'&plain=true')
		if response.ok and re.search("\d", response.content, re.M|re.I):
			logging.debug("log for job:"+allocid+" is avaialble using api")								
			lines = response.content.splitlines()
			if lines:
				#lastline = lines[-1]
				results['content'] = response.content
		else:
			logging.debug("log for job:"+allocid+" is not avaialble using api")																								

	if results['content'] != '':
		for match in re.finditer(r"(.*([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) ?(\bscanned\b|\breviewed\b|\bcompared\b).+)",results['content'],re.M|re.I):
			lastline = match.group(0)
		results['lastline'] = lastline
	
	if results['contentotherlog'] != '':
		for match in re.finditer(r"(.*([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) ?(\bscanned\b|\breviewed\b|\bcompared\b).+)",results['contentotherlog'],re.M|re.I):
			otherloglastline = match.group(0)
		results['otherloglastline'] = otherloglastline		

	#for xcp logs 	
	if lastline:
		matchObj = re.search("\s+(\S*\d+[s|m|h])(\.)?$", lastline, re.M|re.I)
		if matchObj: 
			results['time'] = matchObj.group(1)
				#reviewed in xcp linux, compared xcp windows
                matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) ?(reviewed|compared)", lastline, re.M|re.I)
                if matchObj:
                        results['reviewed'] = matchObj.group(1)
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) scanned", lastline, re.M|re.I)
		if matchObj: 
			results['scanned'] = matchObj.group(1)
		#in case of match filter being used the scanned files will used
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) matched", lastline, re.M|re.I)
		if matchObj: 
			results['scanned'] = matchObj.group(1)			
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) copied", lastline, re.M|re.I)
		if matchObj: 
			results['copied'] = matchObj.group(1)
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) indexed", lastline, re.M|re.I)
		if matchObj: 
			results['indexed'] = matchObj.group(1)
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) gone", lastline, re.M|re.I)
		if matchObj: 
			results['gone'] = matchObj.group(1)	
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) modification", lastline, re.M|re.I)
		if matchObj: 
			results['modification'] = matchObj.group(1)
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) error", lastline, re.M|re.I)
		if matchObj: 
			results['errors'] = matchObj.group(1)

		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) file.gone", lastline, re.M|re.I)
		if matchObj: 
			results['filegone'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) dir.gone", lastline, re.M|re.I)
		if matchObj: 
			results['dirgone'] = matchObj.group(1)		

		matchObj = re.search("([-+]?[0-9]*\.?[0-9]+ \SiB out \([-+]?[0-9]*\.?[0-9]+( \SiB)?\/s\))", lastline, re.M|re.I)
		if matchObj: 
			results['bwout'] = matchObj.group(1).replace(' out ','')

		#xcp for windows
		matchObj = re.search("([-+]?[0-9]*\.?[0-9]+(\SiB)?\s\([0-9]*\.?[0-9]+(\SiB)?\/s\))", lastline, re.M|re.I)
		if matchObj: 
			results['bwout'] = matchObj.group(1)	

		#matches for verify job
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) found", lastline,re.M|re.I)
		if matchObj:
			results['found'] = matchObj.group(1)

		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?\%?) (found )?\(([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) have data\)", otherloglastline, re.M|re.I)
		if matchObj: 
			results['found'] = matchObj.group(1)
			results['withdata'] = matchObj.group(2)
			if results['found'] == '100%': 
				results['verified']='yes'
				results['found']=results['scanned']
			else:
				results['found']=format(int(results['found']),',')
		
		matchObj = re.search("100\% verified \(attrs, mods\)", lastline, re.M|re.I)
		if matchObj:
			results['verifiedmod']='yes'
			results['verifiedattr']='yes'

		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) different attr", lastline, re.M|re.I)
		if matchObj:
			results['diffattr'] = matchObj.group(1)

		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) different mod time", lastline, re.M|re.I)
		if matchObj:
			results['diffmodtime'] = matchObj.group(1)

		#xcp verify for windows 	
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) compared", lastline, re.M|re.I)
		if matchObj:
			results['scanned'] = matchObj.group(1)		
			
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) same", lastline, re.M|re.I)
		if matchObj:		
			results['found'] = matchObj.group(1)
			if results['scanned'] == results['found']: results['verified']='yes'

	
	#future optimization for status 
#	if type == 'file':
#		logjsonfile = re.sub('\.log$', '.json', logfilepath)
#		
#		logging.debug("storing log data in json file:"+logjsonfile)								
#		try:
#			# Writing JSON data
#			with open(logjsonfile, 'w') as f:
#				json.dump(results, f)
#		except:
#			logging.debug("failed storing log data in json file:"+logjsonfile)								

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

#truncate the middle of a string
def truncate_middle(s, n):
    if len(s) <= n:
        # string is already short-enough
        return s
    # half of the size, minus the 3 .'s
    n_2 = int(n) / 2 - 3
    # whatever's left
    n_1 = n - n_2 - 3
    return '{0}...{1}'.format(s[:n_1], s[-n_2:])

#create general status
def create_status (reporttype,displaylogs=False):

	#get nomad allocations 
	jobs = {}
	allocs = {}
	nodes = {}


	#if display logs then print verbose 
	if displaylogs==True: reporttype = 'verbose' 	

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
	table.field_names = ["Job","Source Path","Dest Path","BL Status","BL Time","BL Sent","SY Status","Next SY","SY Time","SY Sent","SY#","VR Status","VR Start","VR Ratio","VR#"]
	rowcount = 0
	
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.error("job config directory:" + jobdir + " not exists. please load first") 
				exit (1)
					
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					
					dst	          = jobdetails['dst']
					srcbase       = jobdetails['srcbase']
					dstbase       = jobdetails['dstbase']
					xcpindexname  = jobdetails['xcpindexname']	

					baseline_job_name = jobdetails['baseline_job_name']
					sync_job_name     = jobdetails['sync_job_name']
					verify_job_name   = jobdetails['verify_job_name']
					jobcron           = jobdetails['cron']
					ostype			  = jobdetails['ostype']
					tool              = jobdetails['tool']
					
					if ostype=='windows': logtype = 'stdout'
					if ostype=='linux': logtype = 'stderr'

					#baseline job information
					baselinejobstatus = '-'
					baselinestatus = '-'
					baselinesent = '-'
					baselinetime   = '-'					
					baselinefound = False
					#location for the cache dir for baseline  
					baselinecachedir = os.path.join(cachedir,'job_'+baseline_job_name)
					baselinestatsresults ={}
					#baseline objects 
					baselinejob={}
					baselinealloc={}
					basleinelog={}
					allocperiodiccounter = 0

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

									if jobdata['Status'] == 'dead' and jobdata['Stop'] and baselinejobstatus != 'dead':
										baselinejobstatus = 'aborted'
									else:
										baselinejob = jobdata
										baselinejobstatus = jobdata['Status']
							if file.startswith("alloc_"):
								baselinealloccachefile = os.path.join(baselinecachedir,file)
								with open(baselinealloccachefile) as f:
									logging.debug('loading cached info alloc file:'+baselinealloccachefile)
									allocdata = json.load(f)
									if allocdata['CreateTime'] > allocperiodiccounter:
										allocperiodiccounter = allocdata['CreateTime'] 
										baselinestatus = allocdata['ClientStatus']
										baselinefound  = True
										baselinealloc = allocdata
							if file.startswith(logtype+"log_"):
								baselinelogcachefile = os.path.join(baselinecachedir,file)
								logging.debug('loading cached info log file:'+baselinelogcachefile) 
								baselinestatsresults = parse_stats_from_log('file',baselinelogcachefile,logtype)
								if 'time' in baselinestatsresults.keys(): 
									baselinetime = baselinestatsresults['time']
								if 'bwout' in baselinestatsresults.keys(): 
									baselinesent = baselinestatsresults['bwout']

					#set baseline job status based on the analysis 
					if baselinejobstatus == 'pending': baselinestatus='pending'
					if baselinejobstatus == 'aborted': baselinestatus='aborted'

					#gather sync related info
					syncstatus   = '- '
					synctime     = '- '
					nodename     = '- '
					syncsched    = get_next_cron_time(jobcron)
					syncsent     = '-'
					joblastdetails = {}
					alloclastdetails = {}
					syncjobsstructure = {}
					syncjobsstructure['allocs'] = {}
					syncjobsstructure['job'] = {}
					syncjobsstructure['periodics'] = {}
					syncjobsstructure['logs'] = {}
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

							if file.startswith(logtype+"log_"):
								synclogcachefile = os.path.join(synccachedir,file)
								logallocid = file.replace(logtype+'log_','').replace('.log','')
								logging.debug('loading cached info log file:'+synclogcachefile)
								statsresults = parse_stats_from_log('file',synclogcachefile,logtype)
								#if 'time' in statsresults.keys(): 
								#	synctime = statsresults['time']
								#if 'bwout' in statsresults.keys(): 
								#	syncsent = statsresults['bwout']								
								if not syncjobsstructure.has_key('logs'): syncjobsstructure['logs'] = {}
								syncjobsstructure['logs'][logallocid] = {}										
								syncjobsstructure['logs'][logallocid] = statsresults

					if not syncjobfound: syncsched = '-'
			
					if alloclastdetails: 
						logging.debug("sync job name:"+sync_job_name+" lastjobid:"+joblastdetails['ID']+' allocjobid:'+alloclastdetails['ID'])

						synclogcachefile = os.path.join(synccachedir,logtype+'log_'+alloclastdetails['ID']+'.log')
						statsresults = parse_stats_from_log('file',synclogcachefile,logtype)
						if 'time' in statsresults.keys(): synctime = statsresults['time']
						if 'bwout' in statsresults.keys(): syncsent = statsresults['bwout']
						if 'lastline' in statsresults.keys(): synclastline = statsresults['lastline']
						
						syncstatus =  alloclastdetails['ClientStatus']
						if joblastdetails['Status'] in ['pending','running']: syncstatus =  joblastdetails['Status']
						if syncstatus == 'complete': syncstatus = 'idle'

						nodeid = ''
						if 'NodeID' in alloclastdetails: nodeid = alloclastdetails['NodeID']
						if nodeid:
							for node in nodes:
								if node['ID'] == nodeid: nodename = node['Name']


					#gather verify related info
					verifyratio = '- '
					verifystatus = '- '
					verifytime = '- '
					verifyjoblastdetails = {}
					verifyalloclastdetails = {}
					verifyjobsstructure = {}
					verifyjobsstructure['allocs'] = {}
					verifyjobsstructure['job'] = {}
					verifyjobsstructure['periodics'] = {}
					verifyjobsstructure['logs'] = {}					
					verifystatsresults = {}
					verifyperiodiccounter = 0
					verifyallocperiodiccounter = 0
					verifycounter = 0
					verifyjobfound = False
					verifystarttime = '- '
					#location for the cache dir for verify 
					verifycachedir     = os.path.join(cachedir,'job_'+verify_job_name)					

					if not os.path.exists(verifycachedir): 
						logging.debug('cannot find job cache dir:'+verifycachedir)
					else:			
						for file in os.listdir(verifycachedir):
							if file == 'job_'+verify_job_name+'.json':
								verifyjobfound = True
								verifycachefile = os.path.join(verifycachedir,file)
								with open(verifycachefile) as f:
									logging.debug('loading cached info job file:'+verifycachefile)
									jobdata = json.load(f)
									if jobdata['Stop']: verifysched = 'paused'
									if not verifyjobsstructure.has_key('job'):
										verifyjobsstructure['job'] = {}
									verifyjobsstructure['job'] = jobdata

							if file.startswith("periodic-"):
								verifycachefile = os.path.join(verifycachedir,file)
								with open(verifycachefile) as f:
									logging.debug('loading cached info periodic file:'+verifycachefile)
									jobdata = json.load(f)
									if file.split('-')[1] > verifyperiodiccounter:										
										verifystatus = jobdata['Status']
										verifyjoblastdetails = jobdata
										verifyperiodiccounter = file.split('-')[1]
									if not verifyjobsstructure.has_key('periodics'):
										verifyjobsstructure['periodics'] = {}
									verifyjobsstructure['periodics'][jobdata['ID']] = {}											
									verifyjobsstructure['periodics'][jobdata['ID']] = jobdata
									verifycounter+=1

							if file.startswith("alloc_"):
								verifyalloccachefile = os.path.join(verifycachedir,file)
								with open(verifyalloccachefile) as f:
									logging.debug('loading cached info alloc file:'+verifyalloccachefile)
									allocdata = json.load(f)
									if allocdata['CreateTime'] > verifyallocperiodiccounter:
										verifyallocperiodiccounter = allocdata['CreateTime'] 
										verifyalloclastdetails = allocdata
									if not verifyjobsstructure.has_key('allocs'):
										verifyjobsstructure['allocs'] = {}										
									verifyjobsstructure['allocs'][allocdata['ID']] = {}
									verifyjobsstructure['allocs'][allocdata['ID']] = allocdata

							logtype = 'stdout'
							if ostype == 'linux': logtype = 'stderr'

							if file.startswith(logtype+"log_"):
								verifylogcachefile = os.path.join(verifycachedir,file)
								logallocid = file.replace(logtype+'log_','').replace('.log','')
								logging.debug('loading cached info log file:'+verifylogcachefile)
								verifystatsresults = parse_stats_from_log('file',verifylogcachefile,logtype)
								if 'time' in verifystatsresults.keys(): 
									verifytime = verifystatsresults['time']
								if 'bwout' in verifystatsresults.keys(): 
									verifysent = verifystatsresults['bwout']
								if 'found' in verifystatsresults.keys(): 
									verifyratio = verifystatsresults['found']+'/'+verifystatsresults['scanned']	
								if not verifyjobsstructure.has_key('logs'):
									verifyjobsstructure['logs'] = {}
								verifyjobsstructure['logs'][logallocid] = {}										
								verifyjobsstructure['logs'][logallocid] = verifystatsresults



					if not verifyjobfound: verifysched = '-'
			
					if verifyalloclastdetails: 
						logging.debug("verify job name:"+verify_job_name+" lastjobid:"+verifyjoblastdetails['ID']+' allocjobid:'+verifyalloclastdetails['ID'])

						verifylogcachefile = os.path.join(verifycachedir,'stdoutlog_'+verifyalloclastdetails['ID']+'.log')
						verifystatsresults = parse_stats_from_log('file',verifylogcachefile,logtype)
						if 'time' in verifystatsresults.keys(): verifytime = verifystatsresults['time']
						if 'lastline' in verifystatsresults.keys(): verifylastline = verifystatsresults['lastline']
						if 'found' in verifystatsresults.keys(): verifyratio = verifystatsresults['found']+'/'+verifystatsresults['scanned']						
						verifystatus =  verifyalloclastdetails['ClientStatus']

						if verifyjoblastdetails['Status'] in ['pending','running']: verifystatus =  verifyjoblastdetails['Status']

						#aborted 
						if verifyjoblastdetails['Status'] == 'dead' and verifyjoblastdetails['Stop']: verifystatus = 'aborted'

						try:

							if verifystatus == 'complete': verifystatus = 'idle'

							#linux
							if verifystatus == 'failed' and (verifystatsresults['found'] != verifystatsresults['scanned']): verifystatus =  'diff'
							if verifystatus == 'failed' and (verifystatsresults['found'] == verifystatsresults['scanned']): verifystatus =  'equal'

							#windows
							if ostype == 'windows' and (verifystatsresults['found'] != verifystatsresults['scanned']): verifystatus =  'diff'
							
							if verifystatus == 'idle' and (verifystatsresults['found'] == verifystatsresults['scanned']): verifystatus =  'equal'
						except:
							logging.debug("verify log details:"+verifylogcachefile+" are not complete")

			 			try:
			 				verifystarttime = verifyalloclastdetails['TaskStates']['verify']['StartedAt']
			 				verifystarttime = verifystarttime.split('T')[0]+' '+verifystarttime.split('T')[1].split('.')[0]
			 			except:
			 				verifystarttime = '-'


					baselinesentshort = re.sub("\(.+\)","",baselinesent)
					syncsentshort = re.sub("\(.+\)","",syncsent)

					#work on error filter 
					addrow = True
					if args.jobstatus and not baselinestatus.startswith(args.jobstatus) and not syncstatus.startswith(args.jobstatus) and not verifystatus.startswith(args.jobstatus):
						addrow = False 
				

					if addrow:
						table.add_row([jobname,src,truncate_middle(dst,30),baselinestatus,baselinetime,baselinesentshort,syncstatus,syncsched,synctime,syncsentshort,synccounter,verifystatus,verifystarttime,verifyratio,verifycounter])
						rowcount += 1


					#printing verbose information
					if reporttype == 'verbose':
						#building verbose details table for the job
						verbosetable = PrettyTable()
						verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Reviewed','Copied','Modified','Deleted','Errors','Data Sent','Node','Status']

						#print general information 
					 	print "JOB: "+jobname
						print "SRC: "+src
						print "DST: "+dst
						print "SYNC CRON: "+jobcron+" (NEXT RUN "+syncsched+")"
					 	if ostype =='linux': print "XCP INDEX NAME: "+xcpindexname
					 	print "OS: "+ostype.upper()
					 	if ostype =='windows': print "TOOL NAME: "+tool
					 	print ""

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
				 				duration = baselinestatsresults['time']
				 			except:
				 				duration = '-'

				 			try:
				 				scanned = baselinestatsresults['scanned']
				 			except:
				 				scanned = '-'

							try:
								reviewed = baselinestatsresults['reviewed']
							except:
								reviewed = '-'
 				
				 			try:
				 				copied = baselinestatsresults['copied']
				 			except:
				 				copied = '-'

				 			try:
				 				deleted = baselinestatsresults['gone']
				 			except:
				 				deleted = '-'

				 			try:
				 				modified = baselinestatsresults['modification']
				 			except:
				 				modified = '-'						 										 				

				 			try:
				 				errors = baselinestatsresults['errors']
				 			except:
				 				errors = '-'

				 			verifyratio = '-'

				 			try:
				 				sent = baselinestatsresults['bwout']
				 			except:
				 				sent = '-'

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
								if baselinejob['Status'] == 'dead' and baselinejob['Stop']: baselinestatus = 'aborted'

							except:
								baselinestatus = '-'
							if baselinestatus == 'running': endtime = '-' 

							#filter out results based on scope 
							if phasefilter and not task.startswith(phasefilter):
								addrow = False  
							if args.node and not nodename.startswith(args.node):
								addrow = False
							if args.jobstatus and not baselinestatus.startswith(args.jobstatus):
								addrow = False 
							if args.error and errors.isdigit():
								if int(errors) == 0:
									addrow = False
							if args.error and errors == '-':
								addrow = False								

							if addrow:								
				 				verbosetable.add_row([task,starttime,endtime,duration,scanned,reviewed,copied,modified,deleted,errors,sent,nodename,baselinestatus])
				 				if displaylogs:
									verbosetable.border = False
									verbosetable.align = 'l'
									print verbosetable
									print ""

									try:
										print "Log type:"+logtype
										print baselinestatsresults['content']
							 			try:
							 				print ""
							 				print "the last "+str(maxloglinestodisplay)+" lines are displayed, full log file can be found in the following path: " +baselinestatsresults['logfilepath']
							 			except:
							 				logging.debug("logfilepath wasnt found in results ")
									except:
										print "log:"+logtype+" is not avaialble"
									print ""
									print ""

									try:
										otherlogtype = 'stdout'
										if logtype == 'stdout': otherlogtype = 'stderr'

										print "Log type:"+otherlogtype
										print baselinestatsresults['contentotherlog']
							 			try:
							 				print ""
							 				print "the last "+str(maxloglinestodisplay)+" lines are displayed, full log file can be found in the following path: " +baselinestatsresults['logfileotherpath']
							 			except:
							 				logging.debug("logfilepath wasnt found in results ")													

									except:
										print "log:"+otherlogtype+" is not avaialble"

									print ""
									print ""
									verbosetable = PrettyTable()
									verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Reviewed','Copied','Modified','Deleted','Errors','Data Sent','Node','Status']


						#get the last sync number will be used for lastsync filter 
						lastsync = len(syncjobsstructure['periodics'])

						#merge sync and verify data 
						jobstructure=syncjobsstructure.copy()
						if 'periodics' in verifyjobsstructure.keys():
							if not 'periodics' in jobstructure.keys():
								jobstructure['periodics']={}
							jobstructure['periodics'].update(verifyjobsstructure['periodics'])
						if 'allocs' in verifyjobsstructure.keys():
							if not 'allocs' in jobstructure.keys():
								jobstructure['allocs']={}							
							jobstructure['allocs'].update(verifyjobsstructure['allocs'])
						if 'logs' in verifyjobsstructure.keys():
							if not 'logs' in jobstructure.keys():
								jobstructure['logs']={}								
							jobstructure['logs'].update(verifyjobsstructure['logs'])

					 	#for each periodic 					 	
					 	synccounter = 1
					 	verifycounter = 1
					 	if 'periodics' in jobstructure.keys():
						 	for periodic in sorted(jobstructure['periodics'].keys()):
						 		currentperiodic = jobstructure['periodics'][periodic]
				 				
				 				tasktype = ''
				 				if periodic.startswith('sync'):   
				 					task = 'sync' + str(synccounter)
				 					tasktype = 'sync'
				 					synccounter+=1
				 				if periodic.startswith('verify'): 
				 					task = 'verify'+str(verifycounter)
				 					verifycounter+=1
				 					tasktype = 'verify'		

						 		for allocid in jobstructure['allocs']:
						 			if jobstructure['allocs'][allocid]['JobID'] == periodic:
						 				currentalloc = jobstructure['allocs'][allocid]
						 				currentlog = {}
						 				
						 				if allocid in jobstructure['logs'].keys():
						 					currentlog = jobstructure['logs'][allocid]

							 			try:
							 				starttime = currentalloc['TaskStates'][tasktype]['StartedAt']
							 				starttime = starttime.split('T')[0]+' '+starttime.split('T')[1].split('.')[0]
							 			except:
							 				starttime = '-'

							 			try:
							 				endtime = currentalloc['TaskStates'][tasktype]['FinishedAt']
							 				endtime = endtime.split('T')[0]+' '+endtime.split('T')[1].split('.')[0]
							 			except:
							 				endtime = '-'

							 			try:
							 				duration = currentlog['time']
							 			except:
							 				duration = '-'

							 			try:
							 				reviewed = currentlog['reviewed']
							 			except:
							 				reviewed = '-'
							 				
										try:
											scanned = currentlog['scanned']
											if tasktype == 'verify': scanned = currentlog['found']+'/'+currentlog['scanned']
										except:
											scanned = '-'

							 			try:
							 				copied = currentlog['copied']
							 			except:
							 				copied = '-'

							 			try:
							 				deleted = currentlog['gone']
							 			except:
							 				deleted = '-'

							 			try:
							 				modified = currentlog['modification']
							 			except:
							 				modified = '-'						 										 				

							 			try:
							 				errors = currentlog['errors']
							 				if tasktype == 'verify':
									 			try:
									 				diffattr = currentlog['diffattr']
									 			except:
									 				diffattr = '0'								 					

									 			try:
									 				diffmodtime = currentlog['diffmodtime']
									 			except:
									 				diffmodtime = '0'

												errors = errors+' (attr:'+diffattr+' time:'+diffmodtime+')'
							 			except:
							 				errors = '-'	

							 			try:
							 				sent = currentlog['bwout']
							 			except:
							 				sent = '-'

										try:
											nodeid = baselinealloc['NodeID']
											if nodeid:
												for node in nodes:
													if node['ID'] == nodeid: nodename = node['Name']
										except:
											nodeid = ''

							 			try:
								 			jobstatus =  currentalloc['ClientStatus']
											if currentperiodic['Status'] in ['pending','running']: jobstatus =  currentperiodic['Status']
											if tasktype == 'verify':
												if jobstatus == 'failed' and (currentlog['found'] != currentlog['scanned']): jobstatus =  'diff'
												if jobstatus == 'failed' and (currentlog['found'] == currentlog['scanned']): jobstatus =  'equal'
												if jobstatus == 'complete': jobstatus = 'idle'
												#windows
												if ostype == 'windows' and (currentlog['found'] != currentlog['scanned']): jobstatus =  'diff'
												if jobstatus == 'idle' and (currentlog['found'] == currentlog['scanned']): jobstatus =  'equal'																				
										except:
											jobstatus = '-'

								#handle aborted jobs 
								if currentperiodic['Status'] == 'dead' and currentperiodic['Stop']: jobstatus = 'aborted'											

								#validate aborted time 
								if jobstatus == 'running': endtime = '-' 
								
								#filter results
								addrow = True 
								if phasefilter and not task.startswith(phasefilter) and phasefilter != 'lastsync':
									addrow = False
								if phasefilter == 'lastsync' and task != 'sync'+str(lastsync):
									addrow = False 											
								if args.node and not nodename.startswith(args.node):
									addrow = False
								if args.jobstatus and not jobstatus.startswith(args.jobstatus):
									addrow = False 
								if args.error and errors.isdigit():
									if int(errors) == 0:
										addrow = False
								if args.error and errors == '-':
									addrow = False
													
								if addrow:
			 						verbosetable.add_row([task,starttime,endtime,duration,scanned,reviewed,copied,modified,deleted,errors,sent,nodename,jobstatus])
					 				if displaylogs:
										verbosetable.border = False
										verbosetable.align = 'l'
										print verbosetable.get_string(sortby="Start Time")
										print ""

										try:
											print "Log type:"+logtype
											print currentlog['content']
								 			try:
								 				print ""
								 				print "the last "+str(maxloglinestodisplay)+" lines are displayed, full log file can be found in the following path: " +currentlog['logfilepath']
								 			except:
								 				logging.debug("logfilepath wasnt found in results ")
										except:
											print "log:"+logtype+" is not avaialble"
										print ""
										print ""
										try:
											otherlogtype = 'stdout'
											if logtype == 'stdout': otherlogtype = 'stderr'

											print "Log type:"+otherlogtype
											print currentlog['contentotherlog']
								 			try:
								 				print ""
								 				print "the last "+str(maxloglinestodisplay)+" lines are displayed, full log file can be found in the following path: " +currentlog['logfileotherpath']
								 			except:
								 				logging.debug("logfilepath wasnt found in results ")													

										except:
											print "log:"+otherlogtype+" is not avaialble"
										print ""
										print ""												
										verbosetable = PrettyTable()
										verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Reviewed','Copied','Modified','Deleted','Errors','Data Sent','Node','Status']

						#print the table 
						verbosetable.border = False
						verbosetable.align = 'l'
						print verbosetable.get_string(sortby="Start Time")
						print ""
						print ""

					
	#dispaly general report
	if rowcount > 0 and reporttype == 'general':
		table.border = False
		table.align = 'l'
		print "\n BL=Baseline SY=Sync VR=Verify\n"
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
				logging.error("job config directory:" + jobdir + " not exists. please use 'sload' first") 
				exit (1)
					
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
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
						logging.warning("sync job does not exists for src:"+src+". please use sync command to recreate it") 
					
					else:
						baselinestatus = check_baseline_job_status(baselinejobname)
						
						syncjobdetails = {}
						try:
							syncjobdetails = n.job.get_job(nomadjobname)
						except:
							logging.error("cannot get job:"+nomadjobname+" details")

						jobfile = os.path.join(jobdir,nomadjobname+'.hcl')		
						if not os.path.exists(jobfile): 
							logging.error("job file"+jobfile+" for job:"+nomadjobname+" could not be found, please load csv again") 
							exit (1)

						nomadjobjson = subprocess.check_output([ nomadpath, 'run','-output',jobfile])
						nomadjobdict = json.loads(nomadjobjson)

						currentstopstatus = 'pause'
						if syncjobdetails["Stop"] != True : currentstopstatus = 'resume' 
							
						if action == 'resume' and baselinestatus != 'baseline is complete' and currentstopstatus == 'pause':
							logging.warning("cannot resume job:"+nomadjobname+" status changed to:"+action+"since baseline is not complete") 
						elif action in ['pause','resume'] and currentstopstatus != action:
							nomadjobdict["Job"]["Stop"] = newstate

							logging.info("src:"+src+" dst:"+dst+" status changed to:"+action) 
							nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
							try:
								job = n.job.get_job(nomadjobname)
							except:
								logging.error("job:"+nomadjobname+" update failed") 
								exit(1)
						elif action in ['pause','resume'] and currentstopstatus == action:
							logging.info("job name:"+nomadjobname+" is already:"+action) 
						elif action == 'syncnow':
							already_running = False
							if baselinestatus != 'baseline is complete':
								logging.warning("cannot syncnow for:"+src+" since "+baselinestatus.lower())
							else:
								try:
									response = requests.get(nomadapiurl+'jobs?prefix='+nomadjobname+"/")
									prefixjobs = json.loads(response.content)

									for prefixjob in prefixjobs:
										if prefixjob["Status"] == 'running':
											already_running = True 
								except:
									logging.debug("could not get job periodics for job:"+nomadjobname) 

								if already_running:
									logging.warning("cannot syncnow for src:"+src+" because it is already running")	
								else:
									logging.info("starting sync for src:"+src+" dst:"+dst) 
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
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					
					dst	          = jobdetails['dst']
					srcbase       = jobdetails['srcbase']
					dstbase       = jobdetails['dstbase']
					syncnomadjobname  = jobdetails['sync_job_name']
					baselinejobname  = jobdetails['baseline_job_name']
					verifyjobname    = jobdetails['verify_job_name']

					force = forceparam
					if not force: force = query_yes_no("delete job for source:"+src,'no')
					if force:
						logging.info("delete job for source:"+src) 
						#delete baseline jobs 
						delete_job_by_prefix(baselinejobname)
						
						#delete sync jobs 
						delete_job_by_prefix(syncnomadjobname)

						#delete verify jobs 
						delete_job_by_prefix(verifyjobname)

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

						verifycachedir = os.path.join(cachedir,'job_'+verifyjobname)
						if os.path.exists(verifycachedir):
							logging.debug("delete verify cache dir:"+verifyjobname)
							try:
								rmout = shutil.rmtree(verifycachedir)
							except:
								logging.error("could not delete verify cache dir:"+verifycachedir)


						#delete entry from jobdict
						del jobsdictcopy[jobname][src]
						#delete job when empty 
						if len(jobsdictcopy[jobname]) == 0:
							del jobsdictcopy[jobname]

						#dumping jobsdict to json file 
						try:
							with open(jobdictjson, 'w') as fp:
								json.dump(jobsdictcopy, fp)
							fp.close()
						except:
							logging.error("cannot write job json file:"+jobdictjson)
							exit(1)						

#check if nomad is available + run the xcption_gc_system job if not avaialble 
def nomadstatus():
	logging.debug("getting list of nomad nodes")
	response = requests.get(nomadapiurl+'nodes')	
	if not response.ok:
		logging.error("could not contact nomad cluster, please make sure this node is part of the cluster")
		exit(1)
	else:
		#build the table object
		table = PrettyTable()
		table.field_names = ["Name","IP","Status","OS","Reserved/Total CPU MHz","Used CPU %","Reserved/Total RAM MB","Used RAM %","# Running Jobs"]		
		nodes = json.loads(response.content)
		
		for node in nodes:
			name = node['Name']
			status = node['Status']
			nodeid = node['ID']
			ip = node['Address']

			logging.debug("getting node specifics:"+name)
			response = requests.get(nomadapiurl+'node/'+nodeid)
			if not response.ok:
				logging.error("could not get node information for node:"+name+" id:"+nodeid)
				exit(1)
			else:
				nodedetails = json.loads(response.content)
				ostype = nodedetails['Attributes']['os.name'].capitalize() 
				ip = nodedetails['Attributes']['unique.network.ip-address']
				totalcpu = nodedetails['Resources']['CPU']
				totalram = nodedetails['Resources']['MemoryMB']

				response = requests.get(nomadapiurl+'client/stats?node_id='+nodeid)
				if not response.ok:
					logging.error("could not get client stats information for node:"+name+" id:"+nodeid)
					exit(1)

				clientdetails = json.loads(response.content)
				usedmemory = str(round(float(clientdetails["Memory"]["Used"])/(clientdetails["Memory"]["Total"]),2)*100)+'%'
				
				usedcpupercent = 0
				firstcpu = True 
				for cpu in clientdetails["CPU"]:
					if firstcpu:
						usedcpupercent = 100-int(cpu['Idle'])
					else:
						usedcpupercent = int((usedcpupercent+ 100-int(cpu['Idle']))/2)

					firstcpu = False
				usedcpu = str(usedcpupercent)+'% '

			logging.debug("getting node allocations:"+name)
			response = requests.get(nomadapiurl+'node/'+nodeid+'/allocations')
			if not response.ok:
				logging.error("could not get node allocation for node:"+name+" id:"+nodeid)
				exit(1)
			else:		
				allocdetails = json.loads(response.content)	
				alloccounter = 0
				reservedcpu = 0
				reservedram = 0
				#pp.pprint(allocdetails)
				for alloc in allocdetails:
					if alloc['JobID'] != 'xcption_gc_system' and alloc['ClientStatus'] == 'running': 
						alloccounter += 1
						reservedcpu += alloc['Resources']['CPU']
						reservedram += alloc['Resources']['MemoryMB']
			cpuinfo = str(reservedcpu)+'/'+str(totalcpu) + ' ('+str(round(float(reservedcpu)/float(totalcpu)*100))+'%)'
			raminfo = str(reservedram)+'/'+str(totalram) + ' ('+str(round(float(reservedram)/float(totalram)*100))+'%)'						
			table.add_row([name,ip,status,ostype,cpuinfo,usedcpu,raminfo,usedmemory,alloccounter])
		
		table.border = False
		table.align = 'l'
		print ""
		print table			

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

	nomadserver = ''
	try:
		response = requests.get(nomadapiurl+'agent/members')
		if response.ok:
			agentinfo = json.loads(response.content)
			nomadserver = agentinfo["ServerName"]
	except:
		logging.error("could not get nomad server name")
		exit(1)
	try:
		hostname = socket.gethostname()
	except:
		logging.error("could not get hostname")
		exit(1)	

	if hostname != nomadserver:
		logging.debug("current server:"+hostname+" is not the nomad server:"+nomadserver)
		return
	else:
		logging.debug("current server:"+hostname+" is the nomad server")

	if not os.path.isdir(cachedir):
		os.mkdir(cachedir)

	lockcounter = 0
	lockfile = os.path.join(cachedir,'nomadlock')
	while os.path.exists(lockfile) and lockcounter <= 2:
		logging.debug("delaying cache update since another update is running (lock file:"+lockfile+" exists)")
		time.sleep(1)
		lockcounter+=1

	#creating the lock file 
	try:
		open(lockfile,'w').close()
	except:
		logging.debug("cannot create lock file:"+lockfile)

	for job in jobs:

		if not (job['ID'].startswith('baseline') or job['ID'].startswith('sync') or job['ID'].startswith('verify') or job['ID'].startswith('smartasses')):
			continue

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
		cachecompletefile = os.path.join(jobdir,'complete.job_'+job['ID']+'.json')
		if len(job['ID'].split('/')) > 1:
			jobjsonfile = os.path.join(jobdir,job['ID'].split('/')[1])
			cachecompletefile = os.path.join(jobdir,'complete.'+job['ID'].split('/')[1])

		#validating if final update from job already exists in cache 
		jobcomplete = False 
		try:
			if job['JobSummary']['Summary'][job['ID'].split('/')[0]]['Complete'] == 1 or job['JobSummary']['Summary'][job['ID'].split('/')[0]]['Failed'] == 1:
				jobcomplete = True	
		except:
			logging.debug("could not validate job status:"+job['ID'])

		#validting if cache done 
		cachecomplete = False 		
		if os.path.isfile(cachecompletefile):
			cachecomplete = True

		#skip caching if complete file found 
		if cachecomplete:
			logging.debug("cache for job:"+job['ID']+" is complete, skipping")
			continue

		try:
			with open(jobjsonfile, 'w') as fp:
			    json.dump(job, fp)
			    logging.debug("dumping job to json file:"+jobjsonfile)		
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
				if alloc['TaskGroup'].startswith('verify'): task='verify'
				if alloc['TaskGroup'].startswith('smartasses'): task='smartasses'

				#get stderr and stdout logs
				for logtype in ['stderr','stdout']:
					#try to get the log file using api
					response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+'&type='+logtype+'&plain=true')
					if response.ok and re.search("(\d|\S)", response.content, re.M|re.I):
						logging.debug("log for job:"+alloc['ID']+" is avaialble using api")
						alloclogfile = os.path.join(jobdir,logtype+'log_'+alloc['ID']+'.log')
						try:
							#for smartasses jobs always pull a full file 
							if not os.path.isfile(alloclogfile) or job['ID'].startswith('smartasses'):
								with open(alloclogfile, 'w') as fp:
									logging.debug("dumping log to log file:"+alloclogfile)
									fp.write(response.content)
									fp.close()
									
							else:
								#this is used to be able to add delta to the cahce file to enable tail to work
								tmpalloclogfile = '/tmp/'+str(os.getpid())+alloclogfile.replace('/','_')
								with open(tmpalloclogfile, 'w') as fp:
									logging.debug("dumping log to temp log file:"+tmpalloclogfile)
									fp.write(response.content)
									fp.close()								

								logging.debug("comparing current cached file:"+alloclogfile+" with temp file:"+tmpalloclogfile)
								apendtologfile = open(alloclogfile, 'a')
								DEVNULL = open(os.devnull, 'wb')
								subprocess.call( ['comm','-13',alloclogfile,tmpalloclogfile],stdout=apendtologfile,stderr=DEVNULL)
								apendtologfile.close()
								os.remove(tmpalloclogfile)	
						except:
							logging.error("cannot create file:"+alloclogfile)
							exit(1)

				# #get stderr logs
				# logtype = '&type=stdout'
				# #try to get the log file using api
				# response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+logtype+'&plain=true')
				# if response.ok and re.search("(\d|\S)", response.content, re.M|re.I):
				# 	logging.debug("stdout log for job:"+alloc['ID']+" is avaialble using api")
				# 	alloclogfile = os.path.join(jobdir,'stdoutlog_'+alloc['ID']+'.log')
				# 	try:
				# 		with open(alloclogfile, 'w') as fp:
				# 			fp.write(response.content)
				# 			logging.debug("dumping log to log file:"+alloclogfile)		
				# 	except:
				# 		logging.error("cannot create file:"+alloclogfile)
				# 		exit(1)						

				# if alloc['TaskGroup'].startswith('verify'): 
				# 	#get stderr logs for verify
				# 	logtype = '&type=stdout'						
				# 	#try to get the log file using api
				# 	response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+logtype+'&plain=true')
				# 	if response.ok and re.search("(\d|\S)", response.content, re.M|re.I):
				# 		logging.debug("log for job:"+alloc['ID']+" is avaialble using api")
				# 		alloclogfile = os.path.join(jobdir,'log_'+alloc['ID']+'.log')
				# 		try:
				# 			with open(alloclogfile, 'a+') as fp:
				# 				fp.write(response.content)
				# 				logging.debug("appending log to log file:"+alloclogfile)		
				# 		except:
				# 			logging.error("cannot create file:"+alloclogfile)
				# 			exit(1)

				logging.debug("caching alloc:"+alloc['ID'])

		if jobcomplete and not cachecomplete:
			logging.debug("creating file:"+cachecompletefile+" to preven further caching of the job")
			subprocess.call(['touch', cachecompletefile])
			
	#removing the lock file 
	try:
		logging.debug("removing lock file:"+lockfile)
		os.remove(lockfile)
	except:
		logging.debug("cannot remove lock file:"+lockfile)


#walk throuth a dir upto certain depth in the directory tree 
def list_dirs_linux(startpath,depth):
	num_sep = startpath.count(os.path.sep)
	for root, dirs, files in os.walk(startpath):
		#dir1 = root.lstrip(startpath)
		dir1 = root[len(startpath)+1:]
		if (dir1.startswith('.snapshot')):
			del dirs[:]
			continue
		else:
			dir1 = './'+dir1
			yield dir1,len(dirs),len(files),dirs
			num_sep_this = root.count(os.path.sep)
			if num_sep + depth <= num_sep_this:
				del dirs[:]

#unmount filesystem
def unmountdir(dir):
	if subprocess.call( [ 'umount', dir ], stderr=subprocess.STDOUT):
		logging.error("cannot unmount:"+dir)
		exit(1)

	try:
		os.rmdir(dir)
	except:
		logging.error("cannot delete temp mount point:"+dir)
		exit(1)

#check job status 
def check_smartasses_job_status (jobname):

	jobcachedir = os.path.join(cachedir,'job_'+jobname)

	#if job exists retrun the allocation status
	results ={}
	results['status'] = 'unknown'
	results['stderrlog'] = ''
	results['stdoutlog'] = ''
	results['starttime'] = '-'
	job = {}

	try:	
		job = n.job.get_job(jobname)
	except:
		job = None

	if not job and not os.path.exists(jobcachedir):
		logging.debug("baseline job:"+jobname+" does not exist and cahced folder:"+jobcachedir+" does not exists")
		results['status'] = 'not started'
		return results

	if os.path.exists(jobcachedir):
		for file in os.listdir(jobcachedir):
			if file.startswith("periodic-"):
				baselinecachefile = os.path.join(jobcachedir,file)
				with open(baselinecachefile) as f:
					logging.debug('loading cached info periodic file:'+baselinecachefile)
					jobdata = json.load(f)
					
					results['status'] = jobdata['Status']
					if jobdata['Status'] == 'dead' and not jobdata['Stop'] and jobdata['JobSummary']['Summary'][jobname]['Complete'] == 1: results['status'] = 'completed'
					if jobdata['Status'] == 'dead' and not jobdata['Stop'] and jobdata['JobSummary']['Summary'][jobname]['Failed'] == 1: results['status'] = 'failed'
					if jobdata['Status'] == 'dead' and jobdata['Stop']: results['status'] = 'aborted'

			if file.startswith("alloc_"):
				alloccachefile = os.path.join(jobcachedir,file)
				with open(alloccachefile) as f:
					logging.debug('loading cached info alloc file:'+alloccachefile)
					allocdata = json.load(f)
				 	starttime = allocdata['TaskStates']['smartasses']['StartedAt']
				 	starttime = starttime.split('T')[0]+' '+starttime.split('T')[1].split('.')[0]				
					results['starttime'] = starttime

			for file in os.listdir(jobcachedir):
				if file.startswith('stderrlog_'): results['stderrlog'] = os.path.join(jobcachedir,file)
				if file.startswith('stdoutlog_'): results['stdoutlog'] = os.path.join(jobcachedir,file)			

	return results

#get a list of soruces that should be created 
def createtasksfromtree(dirtree, nodeid):

	global totaljobssizek, totaljobsinode, totaljobscreated
	
	nodechildren = dirtree.children(nodeid.identifier)
	for node in nodechildren:
		#recurse ntil getting to the bottom of the tree
		dirtree = createtasksfromtree(dirtree,node)
		
		jobcreated = False 

		if not node.data.createjob and not node.data.excludejob:
			if minsizekfortask_minborder <= node.data.sizek <= minsizekforjob or mininodespertask_minborder <= node.data.inodes <= mininodespertask:
				logging.debug(node.identifier+" will be a normal job inodes:"+node.data.inodes_hr+" size:"+node.data.size_hr)
				jobcreated = True
				totaljobscreated += 1
			elif node.data.sizek > minsizekforjob or node.data.inodes > mininodespertask:
				logging.debug(node.identifier+" will be a mega job inodes:"+node.data.inodes_hr+" size:"+node.data.size_hr)
				jobcreated = True
				totaljobscreated += 1

		#if job created		
		if jobcreated:

			node.data.createjob = True
			totaljobssizek += node.data.sizek
			totaljobsinode += node.data.inodes

			if not node.is_root():
				dirtree.get_node(dirtree.root).data.inodes -= node.data.inodes
				dirtree.get_node(dirtree.root).data.sizek -= node.data.sizek

			tempnode = node
			while tempnode:
				tempnode.data.excludejob = True
				#print tempnode.identifier+" is marked with exclude flag"
				if not tempnode.is_root():
					tempnode = dirtree.parent(tempnode.identifier)
				else:
					tempnode = None 

	if nodeid.is_root():
		if 1024 <= nodeid.data.sizek <= 1024*1024:
			nodeid.data.sizek_hr = format(int(nodeid.data.sizek/1024),',')+' MiB'
		elif 1024*1024 <= nodeid.data.sizek <= 1024*1024*1024:
			nodeid.data.sizek_hr = format(int(nodeid.data.sizek/1024/1024),',')+' GiB'
		elif 1024*1024*1024*1024 <= nodeid.data.sizek:
			nodeid.data.sizek_hr = format(int(nodeid.data.sizek/1024/1024/1024),',')+' TiB'
		nodeid.data.inodes_hr = format(nodeid.data.inodes,',')

		logging.debug(nodeid.identifier+" will be a root job inodes:"+str(nodeid.data.inodes)+" size:"+str(nodeid.data.sizek)+" (excluding data from all other jobs)")
		nodeid.data.createjob = True
		totaljobscreated += 1

	return dirtree 

#parse hardlink log file and return results based on the suggested tasks 
def createhardlinkmatches(dirtree,inputfile):

	class dirdata:
		def __init__(self, inodes,sizek,inodes_hr,size_hr,createjob,excludejob,hardlinks): 
			self.inodes = inodes
			self.sizek = sizek
			self.inodes_hr = inodes_hr
			self.size_hr  = size_hr
			self.createjob = createjob
			self.excludejob = excludejob
			self.hardlinks = hardlinks
	

	if not os.path.isfile(inputfile):
		logging.error("log file:"+inputfile+" does not exists")
		exit(1)

	with open(inputfile) as f:
	    content = f.readlines()

	hardlinks ={}
	crosstaskcount = 0 

	content = [x.strip() for x in content] 
	for line in content:
		path,inode = line.split(',')
		if path and inode:
			if not inode in hardlinks.keys(): 
				hardlinks[inode] = {}
				hardlinks[inode]['count'] = 0
				hardlinks[inode]['tasks'] = {}

			hardlinks[inode]['count'] += 1

			taskobj = None
			longesttask = ''			
			for task in dirtree.filter_nodes(lambda x: path.startswith(x.identifier) and x.data.createjob):
				if len(task.identifier) > len(longesttask):
					longesttask = task.identifier
					taskobj = task
			if not longesttask in hardlinks[inode]['tasks'].keys(): 
				hardlinks[inode]['tasks'][longesttask] = {}
				hardlinks[inode]['tasks'][longesttask]['count'] = 1
				hardlinks[inode]['tasks'][longesttask]['paths'] = {}
				hardlinks[inode]['tasks'][longesttask]['paths'][path] = True
				if not 'taskcount' in hardlinks[inode].keys():
					hardlinks[inode]['taskcount'] = 1
				else:	
					hardlinks[inode]['taskcount'] += 1
				
				#updating tree structure with number of hardlink nuber of tasks 
				if hardlinks[inode]['taskcount'] > task.data.hardlinks:
					dirtree.update_node(longesttask,data=dirdata(taskobj.data.inodes,
						taskobj.data.sizek,taskobj.data.inodes_hr,taskobj.data.size_hr,taskobj.data.createjob,taskobj.data.excludejob,
						hardlinks[inode]['taskcount']))
					crosstaskcount = hardlinks[inode]['taskcount']
			else:
				hardlinks[inode]['tasks'][longesttask]['count'] += 1
				hardlinks[inode]['tasks'][longesttask]['paths'][path] = True

	return hardlinks,crosstaskcount

def gethardlinklistpertask(hardlinks,src):
	hardlinkpaths = {}
	for inode in hardlinks:
		for task in hardlinks[inode]['tasks']:
			for path in hardlinks[inode]['tasks'][task]['paths']:
				if task == src:
					for task1 in hardlinks[inode]['tasks']:
						if task1 != src: 
							for path1 in hardlinks[inode]['tasks'][task1]['paths']:
								
								if not task in hardlinkpaths.keys():
									hardlinkpaths[task] = {}
								if not path in hardlinkpaths[task].keys():
									hardlinkpaths[task][path] = {}

								logging.debug("task:"+task+" path:"+path+" have the following links in another task:"+task1+" path:"+path1)
								hardlinkpaths[task][path][path1]=task1

	return hardlinkpaths


#show status of the smartasses jobs
def smartasses_fs_linux_status(displaytasks,displaylinks):
	global mininodespertask_minborder, mininodespertask
	global smartassesdict
	global totaljobscreated,totaljobssizek

	infofound = False 
	logging.debug("starting smartasses status") 	

	table = PrettyTable()
	table.field_names = ["Path","Scan Status","Scan Start","Scan Time",'Scanned','Errors',"Hardlink Scan","HL Scan Time",'HL Scanned','HL Errors','Total Capacity','# Suggested Tasks','# Cross Task Hardlinks']	

	for smartassesjob in smartassesdict:
		totaljobscreated = 0 
		totaljobssizek = 0 

		src = smartassesdict[smartassesjob]['src']
		if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
			results = check_smartasses_job_status(smartassesjob)
			resultshardlink = check_smartasses_job_status(smartassesjob+'_hardlink_scan')

			scantime = '-'
			scanned = '-'
			errors = '-'

			if results['status'] != 'not started':
				#stderr parse
				stderrresults = parse_stats_from_log ('file',results['stderrlog'],'stderr')
				if 'time' in stderrresults.keys(): 
					scantime = stderrresults['time']
				if 'scanned' in stderrresults.keys(): 
					scanned = stderrresults['scanned']
				if 'errors' in stderrresults.keys(): 
					errors = stderrresults['errors']			

			scantimehl = '-'
			scannedhl = '-'
			errorshl = '-'
			crosstaskcount = 0
			if resultshardlink['status'] != 'not started':
				#stderr parse
				stderrresults = parse_stats_from_log ('file',resultshardlink['stderrlog'],'stderr')
				if 'time' in stderrresults.keys(): 
					scantimehl = stderrresults['time']
				if 'scanned' in stderrresults.keys(): 
					scannedhl = stderrresults['scanned']
				if 'errors' in stderrresults.keys(): 
					errorshl = stderrresults['errors']	

			if results['status'] == 'completed' and (resultshardlink['status'] == 'not started' or resultshardlink['status'] == 'completed'):
				#parsing log to tree
				dirtree = smartasses_parse_log_to_tree(src,results['stdoutlog'])
				dirtree = createtasksfromtree(dirtree, dirtree.get_node(src))

				if resultshardlink['status'] == 'completed':
					hardlinks,crosstaskcount = createhardlinkmatches(dirtree,resultshardlink['stdoutlog'])
									

			if totaljobscreated == 0: totaljobscreated = '-'
			if totaljobssizek > 0:
				size_hr = k_to_hr(totaljobssizek)
			else:
				size_hr = '-'
			if crosstaskcount >0: crosstaskcount -= 1

			crosstaskcountlabel = crosstaskcount
			if crosstaskcount == 0 and resultshardlink['status'] == 'completed': crosstaskcountlabel = 'no conflicts'
			if crosstaskcount == 0 and resultshardlink['status'] == 'not started': crosstaskcountlabel = 'not evaluated'
			
			table.add_row([src,results['status'],results['starttime'],scantime,scanned,errors,resultshardlink['status'],scantimehl,scannedhl,errorshl,size_hr,totaljobscreated,crosstaskcountlabel])
			infofound = True 
			if displaytasks:

				table.border = False
				table.align = 'l'
				print ""
				print table	

				if results['status'] == 'completed' and (resultshardlink['status'] == 'not started' or resultshardlink['status'] == 'completed'):
					table = PrettyTable()
					table.field_names = ["Path","Scan Status","Scan Start","Scan Time",'Scanned','Errors',"Hardlink Scan","HL Scan Time",'HL Scanned','HL Errors','Total Capacity','# Suggested Tasks','# Cross Task Hardlinks']	

					print ""
					print "   Suggested tasks:"
					print ""
					tasktable = PrettyTable()
					tasktable.field_names = ["Path","Total Capacity","Inodes","Root Task","Cross Path Hardlinks"]	
					
					for task in dirtree.filter_nodes(lambda x: x.data.createjob):
						
						taskhardlinksinothertasks = 0
						if crosstaskcount > 0:
							hardlinklist = gethardlinklistpertask(hardlinks,task.identifier)
							
							if task.identifier in hardlinklist.keys():
								taskhardlinksinothertasks = len(hardlinklist[task.identifier])

						tasktable.add_row([task.identifier,task.data.size_hr,task.data.inodes_hr,task.is_root(),taskhardlinksinothertasks])
						if taskhardlinksinothertasks > 0 and displaylinks:

							tasktable.border = False
							tasktable.align = 'l'
							tasktable.padding_width = 5
							print tasktable
							tasktable = PrettyTable()
							tasktable.field_names = ["Path","Total Capacity","Inodes","Root Task","Cross Path Hardlinks"]	

							hardlinktable = PrettyTable()
							hardlinktable.field_names = ["Hardlink Path","Linked To","Destination Task"]							
							for path in hardlinklist[task.identifier]:
								for path1 in hardlinklist[task.identifier][path]:
									hllinktask = hardlinklist[task.identifier][path][path1]

									hardlinktable.add_row([path,path1,hllinktask])

							hardlinktable.border = False
							hardlinktable.align = 'l'
							hardlinktable.padding_width = 8
							print ""
							print hardlinktable				
							print ""


					tasktable.border = False
					tasktable.align = 'l'
					tasktable.padding_width = 5
					#tasktable.sortby = 'Path'
					print tasktable								

				else:
					print '     vebose information not yet avaialable. it will be avaialble when scan will be completed'
				

		
	if not displaytasks and infofound:
		table.border = False
		table.align = 'l'

		print ""
		print table			

	if not infofound:
		print "     no info found"


def smartasses_parse_log_to_tree (basepath, inputfile):
	
	dirtree = Tree()

	class dirdata:
		def __init__(self, inodes,sizek,inodes_hr,size_hr,createjob,excludejob,hardlinks): 
			self.inodes = inodes
			self.sizek = sizek
			self.inodes_hr = inodes_hr
			self.size_hr  = size_hr
			self.createjob = createjob
			self.excludejob = excludejob
			self.hardlinks = hardlinks
	
	dirtree.create_node('/', basepath)

	if not os.path.isfile(inputfile):
		logging.error("log file:"+inputfile+" does not exists")
		exit(1)
		s
	with open(inputfile) as f:
	    content = f.readlines()

	content = [x.strip() for x in content] 
	for line in content:
		matchObj = re.search("^([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) (\SiB) ([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) inode. ("+basepath+".+$)", line)
		if matchObj:
			size = float(matchObj.group(1).replace(',',''))
			sizeq = matchObj.group(4)
			inodes = int(matchObj.group(5).replace(',',''))
			inodes_hr = matchObj.group(5)
			size_hr = matchObj.group(1)+' '+sizeq
			path = matchObj.group(8)

			if re.search("^"+basepath+"($|\/)",path):
				if sizeq == 'KiB': sizek = float(size)
				if sizeq == 'MiB': sizek = float(size)*1024
				if sizeq == 'GiB': sizek = float(size)*1024*1024
				if sizeq == 'TiB': sizek = float(size)*1024*1024*1024

				directory = path[len(basepath):]

				dirsinpath = directory[1:].split("/")
				dirparent = basepath

				for subdir in dirsinpath:
					if subdir != '':
						currentpath = dirparent+'/'+subdir
						if currentpath == path and not dirtree.get_node(currentpath):
							logging.debug(currentpath+" - pushing deepest subdir:"+subdir+" to tree as:"+currentpath+" parent:"+dirparent)
							dirtree.create_node(subdir,currentpath,parent=dirparent,data=dirdata(inodes,sizek,inodes_hr,size_hr,False,False,0))
						elif currentpath == path and dirtree.get_node(currentpath):
							logging.debug(currentpath +" - updating subdir:"+subdir+" to tree as:"+currentpath+" parent:"+dirparent)
							dirtree.update_node(currentpath,data=dirdata(inodes,sizek,inodes_hr,size_hr,False,False,0))
						elif not dirtree.get_node(currentpath):
							logging.debug(currentpath+" - pushing new subdir:"+subdir+" to tree as:"+currentpath+" parent:"+dirparent)
							dirtree.create_node(subdir,currentpath,parent=dirparent)				

					dirparent += '/'+subdir 
	
	#calculate root sizek + inodes
	a = dirtree.children(basepath)
	rootinodes = 0 
	rootsizek = 0 
	for node in a:
		rootsizek += node.data.sizek
		rootinodes += node.data.inodes

	if rootsizek < 0:
		rootsizek = 0
		logging.debug('rootsizek calculation is lower than 0, setting it to 0')

	if rootinodes < 0:
		rootinodes = 0
		logging.debug('rootinodes calculation is lower than 0, setting it to 0')

	rootsizek_hr = k_to_hr(rootsizek)

	dirtree.update_node(basepath,data=dirdata(rootinodes,rootsizek,format(rootinodes,","),rootsizek_hr,False,False,0))

	#return the dirtree value 
	return dirtree


#smart assesment for linux based on capacity and inode count. this will initiate a scan 
def smartasses_fs_linux_start(src,depth,locate_cross_job_hardlink):
	global smartassesdict

	logging.debug("starting smartasses jobs for src:"+src) 

	smartasses_job_name = 'smartasses_'+src.replace(':/','-_')
	smartasses_job_name = smartasses_job_name.replace('/','_')
	smartasses_job_name = smartasses_job_name.replace(' ','-')
	smartasses_job_name = smartasses_job_name.replace('\\','_')
	smartasses_job_name = smartasses_job_name.replace('$','_dollar')	

	if smartasses_job_name in smartassesdict.keys():
		logging.error("smartasses job already exists for src:"+src+', to run again please delete exisiting task 1st') 
		exit(1)	

	if not re.search("\S+\:\/\S+", src):
		logging.error("source format is incorrect: " + src) 
		exit(1)	

	tempmountpointsrc = '/tmp/src_'+str(os.getpid())

	logging.debug("temporary mount for assement will be:"+tempmountpointsrc)

	#check if src can be mounted
	subprocess.call( [ 'mkdir', '-p',tempmountpointsrc ] )

	logging.debug("validating src:"+src+" is mountable")

	#clearing possiable previous mounts 
	DEVNULL = open(os.devnull, 'wb')
	subprocess.call( [ 'umount', tempmountpointsrc ], stdout=DEVNULL, stderr=DEVNULL)

	if subprocess.call( [ 'mount', '-t', 'nfs', '-o','vers=3', src, tempmountpointsrc ],stderr=subprocess.STDOUT):
		logging.error("cannot mount src using nfs: " + src)
		exit(1)					

	if (depth < 1 or depth > 12):
		logging.error("depth should be between 1 to 12, provided depth is:"+str(depth))
		exit(1)	

	#create smartasses job

	#loading job ginga2 templates 
	templates_dir = ginga2templatedir
	env = Environment(loader=FileSystemLoader(templates_dir) )
	
	try:
		smartasses_template = env.get_template('nomad_smartassses.txt')
	except:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_smartassses.txt'))
		exit(1)

	jobdir = os.path.join(smartassesdir,smartasses_job_name)
	if not os.path.exists(jobdir):
		logging.debug("creating job dir:"+jobdir)
		try:
			os.makedirs(jobdir)
		except:
			logging.error("could not create job dir:"+jobdir)
			exit(1)		

	srchost,srcpath = src.split(":")

	#creating smaetasses job 
	smartassesjob_file = os.path.join(jobdir,smartasses_job_name+'.hcl')	
	logging.debug("creating smartasses job file: " + smartassesjob_file)				
		
	#check if job dir exists
	if os.path.exists(jobdir):
		logging.debug("job directory:" + jobdir + " - already exists") 
	else:	
		if os.makedirs(jobdir):
			logging.error("could not create output directory: " + jobdir)				
			exit(1)

	defaultprocessor = defaultcpu
	defaultram = defaultmemory
	ostype = 'linux'	
	if ostype == 'linux': xcpbinpath = xcppath
	depth += 1
	cmdargs = "diag\",\"find\",\"-v\",\"-branch-match\",\"depth<"+str(depth)+"\",\""+src

	with open(smartassesjob_file, 'w') as fh:
		fh.write(smartasses_template.render(
			dcname=dcname,
			os=ostype,
			smartasses_job_name=smartasses_job_name,
			xcppath=xcpbinpath,
			args=cmdargs,
			memory=defaultram,
			cpu=defaultprocessor
		))

	logging.info("starting smartasses scan:"+smartasses_job_name)
	if not start_nomad_job_from_hcl(smartassesjob_file, smartasses_job_name):
		logging.error("failed to create nomad job:"+smartasses_job_name)
		exit(1)
	response = requests.post(nomadapiurl+'job/'+smartasses_job_name+'/periodic/force')	
	if not response.ok:
		logging.error("job:"+smartasses_job_name+" force start failed") 
		exit(1)		

	#creating hadlink scan smaetasses job 
	smartasses_hardlink_job_name = smartasses_job_name+'_hardlink_scan'
	hardlinksmartassesjob_file = os.path.join(jobdir,smartasses_hardlink_job_name+'.hcl')	
	logging.debug("creating hardlink smartasses job file: " + hardlinksmartassesjob_file)			

	cmdargs = "scan\",\"-noid\",\"-match\",\"type == f and nlinks > 1\",\"-fmt\",\"'{},{}'.format(x,fileid)\",\""+src
	with open(hardlinksmartassesjob_file, 'w') as fh:
		fh.write(smartasses_template.render(
			dcname=dcname,
			os=ostype,
			smartasses_job_name=smartasses_hardlink_job_name,
			xcppath=xcpbinpath,
			args=cmdargs,
			memory=defaultram,
			cpu=defaultprocessor
		))

	if locate_cross_job_hardlink:
		logging.info("starting smartasses hardlink scan:"+smartasses_hardlink_job_name)
		if not start_nomad_job_from_hcl(hardlinksmartassesjob_file, smartasses_hardlink_job_name):
			logging.error("failed to create nomad job:"+smartasses_hardlink_job_name)
			exit(1)
		response = requests.post(nomadapiurl+'job/'+smartasses_hardlink_job_name+'/periodic/force')	
		if not response.ok:
			logging.error("job:"+smartasses_hardlink_job_name+" force start failed") 
			exit(1)		

	#fill dict with info
	smartassesdict[smartasses_job_name] = {}
	smartassesdict[smartasses_job_name]['src'] = src
	smartassesdict[smartasses_job_name]['src'] = src
	smartassesdict[smartasses_job_name]['cpu'] = defaultprocessor
	smartassesdict[smartasses_job_name]['memory'] = defaultram
	smartassesdict[smartasses_job_name]['ostype'] = ostype
	smartassesdict[smartasses_job_name]['depth'] = depth
	smartassesdict[smartasses_job_name]['locate_cross_job_hardlink'] = locate_cross_job_hardlink
	smartassesdict[smartasses_job_name]['dcname'] = dcname

	#dumping jobsdict to json file 
	try:
		with open(smartassesjobdictjson, 'w') as fp:
			json.dump(smartassesdict, fp)
		fp.close()
	except:
		logging.error("cannot write smart asses job json file:"+smartassesjobdictjson)
		exit(1)


#assesment of filesystem and creation of csv file out of it 
def asses_fs_linux(csvfile,src,dst,depth,jobname):
	logging.debug("starting to asses src:" + src + " dst:" + dst) 

	if not re.search("\S+\:\/\S+", src):
		logging.error("source format is incorrect: " + src) 
		exit(1)	
	if not re.search("\S+\:\/\S+", dst):
		logging.error("destination format is incorrect: " + dst)
		exit(1)	

	defaultprocessor = defaultcpu
	if args.cpu: 
		defaultprocessor = args.cpu 
		if defaultprocessor < 0 or defaultprocessor > 20000:
			logging.error("cpu allocation is illegal:"+defaultprocessor)
			exit(1)	

	defaultram = defaultmemory
	if args.ram: 
		defaultram = args.ram
		if defaultram < 0 or defaultram > 20000:
			logging.error("ram allocation is illegal:"+defaultram)
			exit(1)	

	tempmountpointsrc = '/tmp/src_'+str(os.getpid())
	tempmountpointdst = '/tmp/dst_'+str(os.getpid())

	logging.debug("temporary mounts for assement will be:"+tempmountpointsrc+" and "+tempmountpointdst)

	#check if src/dst can be mounted
	subprocess.call( [ 'mkdir', '-p',tempmountpointsrc ] )
	subprocess.call( [ 'mkdir', '-p',tempmountpointdst ] )

	logging.debug("validating src:" + src + " and dst:" + dst+ " are mountable")

	#clearing possiable previous mounts 
	DEVNULL = open(os.devnull, 'wb')
	subprocess.call( [ 'umount', tempmountpointsrc ], stdout=DEVNULL, stderr=DEVNULL)
	subprocess.call( [ 'umount', tempmountpointdst ], stdout=DEVNULL, stderr=DEVNULL)

	if subprocess.call( [ 'mount', '-t', 'nfs', '-o','vers=3', src, tempmountpointsrc ],stderr=subprocess.STDOUT):
		logging.error("cannot mount src using nfs: " + src)
		exit(1)					
	
	if subprocess.call( [ 'mount', '-t', 'nfs', '-o','vers=3', dst, tempmountpointdst ],stderr=subprocess.STDOUT):
		logging.error("cannot mount dst using nfs: " + dst)
		subprocess.call( [ 'umount', tempmountpointsrc ],stderr=subprocess.STDOUT)
		exit(1)


	if (depth < 1 or depth > 12):
		logging.error("depth should be between 1 to 12, provided depth is:"+str(depth))
		exit(1)	

	#prepare things for csv creation
	if jobname == '': jobname = 'job'+str(os.getpid())
	csv_columns = ["#JOB NAME","SOURCE PATH","DEST PATH","SYNC SCHED","CPU MHz","RAM MB"]
	csv_data = []

	if os.path.isfile(csvfile):
		logging.warning("csv file:"+csvfile+" already exists")
		if not query_yes_no("do you want to overwrite it?", default="no"): exit(0)

	#will be true if warning identified 
	warning = False 

	#will set to true if Ctrl-C been pressed during os.walk
	end = False

	srcdirstructure = list_dirs_linux(tempmountpointsrc,depth-1)

	try:
		for o in srcdirstructure:
			path = o[0]
			dircount = o[1]
			filecount = o[2]

			currentdepth = path.count(os.path.sep)
			if path == './': currentdepth = 0

			#print path,depth,currentdepth
			nfssrcpath = src+path.lstrip('.')
			nfsdstpath = dst+path.lstrip('.')

			dstpath = tempmountpointdst+path.lstrip('.')


			if filecount > 0 and (currentdepth < depth-1 or (currentdepth == depth-1 and dircount > 0)):
				logging.warning("source directory: "+nfssrcpath+" contains "+str(filecount)+" files. those files will not be included in the xcption jobs and need to be copied externaly")
	
				warning=True 
			else:
				if os.path.exists(dstpath):
					dstdirfiles = os.listdir(dstpath)
					#print dstdirfiles 
					if len(dstdirfiles) > 0:
						if len(dstdirfiles) > 1 and dstdirfiles[0] != '.snapshot':
							logging.error("destination dir: "+nfsdstpath+ " for source dir: "+nfssrcpath+" already exists and contains files")
							unmountdir(tempmountpointsrc)
							unmountdir(tempmountpointdst)
							exit(1)
						else:
							logging.info("destination dir: "+nfsdstpath+ " for source dir: "+nfssrcpath+" already exists but empty")

			#check if destination directory exists/contains files
			if dircount > 20:
				logging.warning("the amount of directories under: "+nfssrcpath+" is above 20, this will create extensive amount of xcption jobs")
				warning=True  

			#create xcption job entry
			#print depth,currentdepth,dircount,nfssrcpath,path
			if (currentdepth < depth-1 and dircount == 0) or (currentdepth == depth-1 and currentdepth > 0) or (depth == 1):
				if nfssrcpath == src+"/" and nfsdstpath == dst+"/": 
					nfssrcpath = src
					nfsdstpath = dst

				logging.debug("src path: "+nfssrcpath+" and dst path: "+nfsdstpath+ " will be configured as xcp job")
				#append data to csv 
				csv_data.append({"#JOB NAME":jobname,"SOURCE PATH":nfssrcpath,"DEST PATH":nfsdstpath,"SYNC SCHED":defaultjobcron,"CPU MHz":defaultprocessor,"RAM MB":defaultram})


		if warning:
			if query_yes_no("please review the warnings above, do you want to continue?", default="no"): end=False 
		
		if not end:
			try:
			    with open(csvfile, 'w') as c:
			        writer = csv.DictWriter(c, fieldnames=csv_columns)
			        writer.writeheader()
			        for data in csv_data:
			            writer.writerow(data)
			        logging.info("job csv file:"+csvfile+" created")
			except IOError:
				logging.error("could not write data to csv file:"+csvfile)
				unmountdir(tempmountpointsrc)
				unmountdir(tempmountpointdst)
				exit(1)		
			if depth > 1:
				depthrsync = ''
				for x in xrange(depth):
					depthrsync += '/*'
				rsynccmd = 'rsync -av --exclude ".snapshot" --exclude="'+depthrsync+ '" "'+tempmountpointsrc+'/" "'+tempmountpointdst+'/"'
				logging.info("rsync can be used to create the destination initial directory structure for xcption jobs")
				logging.info("rsync command to sync directory structure for the required depth will be:")
				logging.info(rsynccmd)
				logging.info("("+src+" is mounted on:"+tempmountpointsrc+" and "+dst+" is mounted on:"+tempmountpointdst+")")
				if query_yes_no("do you want to run rsync ?", default="no"): 
					end=False 
					logging.info("=================================================================")
					logging.info("========================Starting rsync===========================")
					logging.info("=================================================================")
					#run rsync and check if failed 
					if os.system(rsynccmd):
						logging.error("rsync failed")
						unmountdir(tempmountpointsrc)
						unmountdir(tempmountpointdst)
						exit(1)
					logging.info("=================================================================")
					logging.info("===================rsync ended successfully======================")
					logging.info("=================================================================")

				logging.info("csv file:"+csvfile+ " is ready to be loaded into xcption")

	except KeyboardInterrupt:
		print ""
		print "aborted"
		end = True	

	end = True 	
	if end:
		unmountdir(tempmountpointsrc)
		unmountdir(tempmountpointdst)


def list_dirs_windows(startpath,depth):

	matchObj = re.search(r".+\\(.+)$", startpath, re.M|re.I)
	if matchObj:
		startfolder = matchObj.group(1)
	else:
		logging.error("unexpected format for path:"+startpath)
		exit(1)

	pscmd = xcpwinpath+' scan -l -depth '+str(depth)+' "'+startpath+'"'
	results = run_powershell_cmd_on_windows_agent(pscmd,True)

	if results['status'] != 'complete':
		logging.error("directory scan for path:"+startpath+" failed")
		exit(1)			

	if results['stderr']:
		matchObj = re.search("(\d+) errors,", results['stderr'], re.M|re.I)
		if matchObj:
			if matchObj.group(1) > 1:
				logging.error("errors encountered during while scanning path:"+startpath)
				logging.error("\n\n"+results['stderr'])
				exit(1)


	dirs = {}

	lines = results['stdout'].splitlines()
	for line in lines:
		matchObj = re.search("^(f|d)\s+\S+\s+\S+\s+(.+)$", line, re.M|re.I)
		if matchObj:
			path = matchObj.group(2).replace(startfolder,".",1)
			#if path == ".": path = ".\\"
			pathtype = matchObj.group(1)


			matchObj = re.search(r"(.+)\\.+$", path, re.M|re.I)
			if matchObj:
				basedir = matchObj.group(1)
			else:
				basedir = ''

			if pathtype == "d": 
				if not path in dirs.keys():
					dirs[path]={}
					dirs[path]["filecount"] = 0
					dirs[path]["dircount"] = 0

				if basedir != '':
					if basedir in dirs.keys():
						dirs[basedir]["dircount"] += 1
					else:
						dirs[basedir]={}
						dirs[basedir]["filecount"] = 0
						dirs[basedir]["dircount"] = 1						

			elif pathtype == "f":
				if basedir in dirs.keys():
					dirs[basedir]["filecount"] += 1
				else:
					dirs[basedir]={}
					dirs[basedir]["filecount"] = 1
					dirs[basedir]["dircount"] = 0

	return dirs

#assesment of filesystem and creation of csv file out of it 
def asses_fs_windows(csvfile,src,dst,depth,jobname):
	logging.debug("trying to asses src:" + src + " dst:" + dst) 

	if not re.search(r'^(\\\\?([^\\/]*[\\/])*)([^\\/]+)$', src):
		logging.error("src path format is incorrect: " + src) 
		exit(1)	
	if not re.search(r'^(\\\\?([^\\/]*[\\/])*)([^\\/]+)$', dst):
		logging.error("dst path format is incorrect: " + dst)
		exit(1)	

	defaultprocessor = defaultcpu
	if args.cpu: 
		defaultprocessor = args.cpu 
		if defaultprocessor < 0 or defaultprocessor > 20000:
			logging.error("cpu allocation is illegal:"+defaultprocessor)
			exit(1)	

	defaultram = defaultmemory
	if args.ram: 
		defaultram = args.ram
		if defaultram < 0 or defaultram > 20000:
			logging.error("cpu allocation is illegal:"+defaultram)
			exit(1)	


	tool = defaultwintool
	if args.robocopy:
		tool = 'robocopy'

	failbackuser = ''
	failbackgroup = ''
	if tool == 'xcp' and (not args.failbackuser or not args.failbackgroup):
		logging.error("--failbackuser and --failbackgroup are required to use xcp for windows")
		exit(1)	
	else:		
		failbackuser = args.failbackuser
		failbackgroup = args.failbackgroup		

	logging.info("validating src:" + src + " and dst:" + dst+ " cifs paths are avaialble from one of the windows server") 
	pscmd = 'if (test-path "'+src+'") {exit 0} else {exit 1}'
	psstatus = run_powershell_cmd_on_windows_agent(pscmd)['status']
	if  psstatus != 'complete':
		logging.error("cannot validate src:"+src+" using cifs, validation is:"+psstatus)
		exit(1)								
	pscmd = 'if (test-path "'+dst+'") {exit 0} else {exit 1}'
	psstatus = run_powershell_cmd_on_windows_agent(pscmd)['status']
	if  psstatus != 'complete':
		logging.error("cannot validate dst:"+dst+" using cifs, validation status is:"+psstatus)
		exit(1)	

	if (depth < 1 or depth > 12):
		logging.error("depth should be between 1 to 12, provided depth is:"+str(depth))
		exit(1)	

	#prepare things for csv creation
	if jobname == '': jobname = 'job'+str(os.getpid())
	csv_columns = ["#JOB NAME","SOURCE PATH","DEST PATH","SYNC SCHED","CPU MHz","RAM MB","TOOL","FAILBACKUSER","FAILBACKGROUP"]
	csv_data = []

	if os.path.isfile(csvfile):
		logging.warning("csv file:"+csvfile+" already exists")
		if not query_yes_no("do you want to overwrite it?", default="no"): exit(0)

	#will be true if warning identified 
	warning = False 

	#will set to true if Ctrl-C been pressed during os.walk
	end = True
	srcdirstructure = list_dirs_windows(src,depth-1)
	dstdirstructure = list_dirs_windows(dst,depth)

	excludedir = ''

	for path in srcdirstructure:
		currentdepth = len(path.split("\\"))-1
		#print path, currentdepth

		dircount = srcdirstructure[path]['dircount']
		filecount = srcdirstructure[path]['filecount']

		srcpath = src+path.replace('.','',1)
		dstpath = dst+path.replace('.','',1)


		if filecount > 0 and dircount > 0 and currentdepth < depth :
			logging.warning("source path: "+srcpath+" contains "+str(filecount)+" files. those files will not be included in the xcption jobs and need to be copied externaly")

			warning=True 

		if path in dstdirstructure.keys():
			dstdircount = dstdirstructure[path]['dircount']
			dstfilecount = dstdirstructure[path]['filecount']		

			if (dstfilecount  > 0 or dstdircount >0) and ((currentdepth < depth-1 and dstdircount == 0)
					or (currentdepth == depth-1 and (dstdircount > 0 or dstfilecount >0))):
				logging.error("destination path: "+dstpath+ " for source dir: "+srcpath+" exists and contains files")
				exit(1)
			#elsif :
			#	logging.info("destination path: "+dstpath+ " for source dir: "+srcpath+" exists but empty")

		#check if destination have tomuch directories 
		if dircount > 20:
			logging.warning("the amount of directories under: "+dstpath+" is above 20, this will create extensive amount of xcption jobs")
			warning=True  

		#create xcption job entry
		
		if (currentdepth < depth-1 and dircount == 0) or (currentdepth == depth-1 and currentdepth > 0) or (depth-1 == 0):
			logging.info("src path: "+srcpath+" and dst path: "+dstpath+ " will be configured as xcp job")

			#append data to csv 
			csv_data.append({"#JOB NAME":jobname,"SOURCE PATH":srcpath,"DEST PATH":dstpath,"SYNC SCHED":defaultjobcron,"CPU MHz":defaultprocessor,"RAM MB":defaultram,"TOOL":tool,"FAILBACKUSER":failbackuser,"FAILBACKGROUP":failbackgroup})

			#exlude copy of files in this dir 
			if currentdepth < depth-1:
				if excludedir == '': excludedir = " /XD "
				excludedir += "\""+srcpath+"\" "

	if warning:
		if query_yes_no("please review the warnings above, do you want to continue?", default="no"): end=False 
	else:
		end = False

	if not end:
		try:
		    with open(csvfile, 'w') as c:
		        writer = csv.DictWriter(c, fieldnames=csv_columns)
		        writer.writeheader()
		        for data in csv_data:
		            writer.writerow(data)
		        logging.info("job csv file:"+csvfile+" created")
		except IOError:
			logging.error("could not write data to csv file:"+csvfile)
			exit(1)	

		if depth-1 > 0:
			depthxcpcopy = ''

			pscmd1 = robocopywinpathasses+" /E /NP /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:"+str(depth)+" \""+src+"\" \""+dst+"\" /XF *"
			pscmd2 = robocopywinpathasses+" /E /NP /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:"+str(depth-1)+" \""+src+"\" \""+dst+"\""+excludedir

			logging.info("robocopy can be used to create the destination initial directory structure for xcption jobs")
			logging.info("robocopy command to sync directory structure for the required depth will be:")
			logging.info(pscmd1+" ------ for directory structure")
			logging.info(pscmd2+" ------ for files")
			if query_yes_no("do you want to run robocopy ?", default="no"): 
				end=False 
				logging.info("=================================================================")
				logging.info("========================Starting robocopy========================")
				logging.info("=================================================================")

				results = run_powershell_cmd_on_windows_agent(pscmd1,True)
				if results['status'] != 'complete':
					logging.error("robocopy failed")
					if results['stderr']:
						logging.error("errorlog:\n"+results['stderr'])	
					if results['stdout']:
						logging.error("errorlog:\n"+results['stdout'])						
					exit(1)		

				print results['stdout']

				results = run_powershell_cmd_on_windows_agent(pscmd2,True)
				if results['status'] != 'complete':
					logging.error("robocopy failed")
					if results['stderr']:
						logging.error("errorlog:\n"+results['stderr'])	
					if results['stdout']:
						logging.error("errorlog:\n"+results['stdout'])							
					exit(1)							
				print results['stdout']

				logging.info("=================================================================")
				logging.info("=================robocopy ended successfully=====================")
				logging.info("=================================================================")

			logging.info("csv file:"+csvfile+ " is ready to be loaded into xcption")
	


#move job 
def move_job(tojob,forceparam):

	jobsdictcopy = copy.deepcopy(jobsdict)
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:			
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]

					force = forceparam

					if jobname == tojob:
						logging.info("src:"+src+" is already in job:"+tojob+",skipping")
						continue 

					if not force: force = query_yes_no("move source:"+src+" from job:"+jobname+" to:"+tojob,'no')
					if force:					
						logging.info("moving src:"+src+" to job:"+tojob+" from jobname:"+jobname)
						#delete entry from jobdict
						del jobsdictcopy[jobname][src]
						#delete job when empty 
						if len(jobsdictcopy[jobname]) == 0:
							del jobsdictcopy[jobname]
						if not tojob in jobsdictcopy:
							jobsdictcopy[tojob] = {}

						jobsdictcopy[tojob][src] = jobdetails
						
						srcjobdir = os.path.join(jobsdir,jobname) 
						dstjobdir = os.path.join(jobsdir,tojob) 

						baseline_job_file = jobdetails['baseline_job_name']+'.hcl'
						sync_job_file     = jobdetails['sync_job_name']+'.hcl'
						verify_job_file   = jobdetails['verify_job_name']+'.hcl'				

						#creating new job dir
						if not os.path.isdir(dstjobdir):
							try:
								logging.debug("tryin to create new job dir:"+dstjobdir)
								os.mkdir(dstjobdir)
							except:
								logging.error("could not create new job dir:" + dstjobdir)
								exit (1)

						#moving files 
						try:
							logging.debug("tring to move:"+os.path.join(srcjobdir,baseline_job_file)+" to:"+os.path.join(dstjobdir,baseline_job_file))
							shutil.copy(os.path.join(srcjobdir,baseline_job_file),os.path.join(dstjobdir,baseline_job_file))
						except:
							logging.error("could not move file:"+os.path.join(srcjobdir,baseline_job_file)+" to:"+os.path.join(dstjobdir,baseline_job_file))
							exit (1)						

						try:
							logging.debug("tring to move:"+os.path.join(srcjobdir,sync_job_file)+" to:"+os.path.join(dstjobdir,sync_job_file))
							shutil.copy(os.path.join(srcjobdir,sync_job_file),os.path.join(dstjobdir,sync_job_file))
						except:
							logging.error("could not move file:"+os.path.join(srcjobdir,sync_job_file)+" to:"+os.path.join(dstjobdir,sync_job_file))
							exit (1)	

						try:
							logging.debug("tring to move:"+os.path.join(srcjobdir,verify_job_file)+" to:"+os.path.join(dstjobdir,verify_job_file))
							shutil.copy(os.path.join(srcjobdir,verify_job_file),os.path.join(dstjobdir,verify_job_file))
						except:
							logging.error("could not move file:"+os.path.join(srcjobdir,verify_job_file)+" to:"+os.path.join(dstjobdir,verify_job_file))
							exit (1)	

						#dumping jobsdict to json file 
						try:
							with open(jobdictjson, 'w') as fp:
								json.dump(jobsdictcopy, fp)
							fp.close()
						except:
							logging.error("cannot write job json file:"+jobdictjson)
							exit(1)	

#abort jobs 
def abort_jobs(jobtype, forceparam):

	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.warning("job config directory:" + jobdir + " not exists. please init first") 
			
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					
					dst	             = jobdetails['dst']
					srcbase          = jobdetails['srcbase']
					dstbase          = jobdetails['dstbase']
					syncnomadjobname = jobdetails['sync_job_name']
					baselinejobname  = jobdetails['baseline_job_name']
					verifyjobname    = jobdetails['verify_job_name']
					ostype           = jobdetails['ostype']
					tool             = jobdetails['tool']
					xcpindexname     = jobdetails['xcpindexname']

					if jobtype == 'baseline':
						abortjobname = baselinejobname
					if jobtype == 'sync':
						abortjobname = syncnomadjobname
					if jobtype == 'verify':
						abortjobname = verifyjobname

					force = forceparam
					if not force: force = query_yes_no("abort job for source:"+src,'no')
					if force:
						logging.info("aborting "+jobtype+" job for source:"+src) 

						response = requests.get(nomadapiurl+'jobs?prefix='+abortjobname+'/per')	
						if not response.ok:
							logging.warning("could not get jobs list prefixed by:"+abortjobname) 
						else:
							nomadjobs = json.loads(response.content)
							jobaborted = False
							for nomadjob in nomadjobs:
								jobstatus = nomadjob['Status']
								#pp.pprint(nomadjob)
								if jobstatus == 'running':
									logging.info("job status is:"+jobstatus+', aborting')
									logging.debug("stoping job:"+nomadjob['ID'])
									response = requests.delete(nomadapiurl+'job/'+nomadjob['ID'])				
									if not response.ok:
										logging.error("can't abort nomad job:"+nomadjob['ID']) 
										exit(1)									

									if jobtype == 'baseline' and ostype == 'linux' and tool == 'xcp':
										logging.info("destroying xcp index for aborted job")
										logging.debug("running the command:"+xcppath+' diag -rmid '+xcpindexname)
										DEVNULL = open(os.devnull, 'wb')
										if subprocess.call( [ xcppath, 'diag', '-rmid', xcpindexname ],stdout=DEVNULL,stderr=DEVNULL):
											logging.debug("failed to delete xcp index:"+xcpindexname)

									jobaborted = True
								elif jobstatus == 'pending':
									logging.info("job status is:"+jobstatus+', aborting and purging job')
									logging.debug("stoping job:"+nomadjob['ID'])
									response = requests.delete(nomadapiurl+'job/'+nomadjob['ID']+'?purge=true')				
									if not response.ok:
										logging.error("can't abort nomad job:"+nomadjob['ID']) 
										exit(1)
									logging.debug("removing cache for job:"+nomadjob['ID'])
									
									#in case of baseline delete also the job father 
									if jobtype == 'baseline':
										logging.debug("stoping job:"+abortjobname)
										response = requests.delete(nomadapiurl+'job/'+abortjobname+'?purge=true')			
										if not response.ok:
											logging.error("can't abort nomad job:"+abortjobname) 
											exit(1)	
									#remove cache dir if exists 
									jobcachedir = os.path.join(cachedir,'job_'+abortjobname)
									if os.path.exists(jobcachedir):
										logging.debug("trying to remove cache dir"+jobcachedir)
										try:
											shutil.rmtree(jobcachedir)
										except:
											logging.warning("could not delete dir:"+jobcachedir)

									jobaborted = True									
								else:
									logging.debug("job status us is:"+jobstatus+', skipping')
								

							if not jobaborted:
								logging.info("no running/pending jobs found")


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
if srcfilter != '' and not '*' in srcfilter:
	srcfilter = '*'+srcfilter+'*'


#filter by phase (relevant to status)
phasefilter = ''
if hasattr(args,'phase'):
	if args.phase != None:
		phasefilter = args.phase

if args.version: print "XCPtion version:"+version

#check nomad avaialbility
check_nomad()

if args.subparser_name == 'nodestatus':
	nomadstatus()
	exit(0)

if args.subparser_name == 'nomad':
	parse_nomad_jobs_to_files()
	exit (0)

if args.subparser_name == 'asses':
	if not re.search(r'^(\\\\?([^\\/]*[\\/])*)([^\\/]+)$', args.source):
		asses_fs_linux(args.csvfile,args.source,args.destination,args.depth,jobfilter)
	else:
		asses_fs_windows(args.csvfile,args.source,args.destination,args.depth,jobfilter)

#load jobs from json file
load_jobs_from_json(jobdictjson)

if args.subparser_name == 'load':
	parse_csv(args.csvfile)
	create_nomad_jobs()

if args.subparser_name == 'baseline':
	start_nomad_jobs('baseline',args.force)

if args.subparser_name == 'sync':
	start_nomad_jobs('sync',False)

if args.subparser_name == 'verify':
	start_nomad_jobs('verify',False)

if args.subparser_name == 'status' and not args.verbose:
	parse_nomad_jobs_to_files()
	create_status('general',args.logs)
if args.subparser_name == 'status' and args.verbose:
	parse_nomad_jobs_to_files()
	create_status('verbose',args.logs)

if args.subparser_name in ['pause','resume','syncnow']:
	update_nomad_job_status(args.subparser_name)

if args.subparser_name == 'delete':
	delete_jobs(args.force)

if args.subparser_name == 'abort':
	abort_jobs(args.type, args.force)

if args.subparser_name == 'modifyjob':
	move_job(args.tojob,args.force)
	parse_nomad_jobs_to_files()

if args.subparser_name == 'smartasses':
	load_smartasses_jobs_from_json(smartassesjobdictjson)

	if args.smartasses_command == 'start':
		smartasses_fs_linux_start(args.source,args.depth,args.locate_cross_job_hardlink)

	if args.smartasses_command == 'status':
		if args.min_capacity:
			matchObj = re.match("^(\d+)(KB|MB|GB|TB)$",args.min_capacity)
			if matchObj.group(2) == 'KB': minsizekfortask_minborder=int(matchObj.group(1))
			if matchObj.group(2) == 'MB': minsizekfortask_minborder=int(matchObj.group(1))*1024
			if matchObj.group(2) == 'GB': minsizekfortask_minborder=int(matchObj.group(1))*1024*1024
			if matchObj.group(2) == 'TB': minsizekfortask_minborder=int(matchObj.group(1))*1024*1024*1024		
		minsizekforjob = minsizekfortask_minborder + 100000

		if args.min_inodes:
			mininodespertask_minborder = args.min_inodes
		mininodespertask = mininodespertask_minborder + 200000

		parse_nomad_jobs_to_files()
		smartasses_fs_linux_status(args.tasks,args.hardlinks)		
