#!/usr/bin/python3

# XCPtion - NetApp XCP wrapper 
# Written by Haim Marko 
# Enjoy

#version 
version = '3.1.0.0'

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
import string

from hurry.filesize import size
from prettytable import PrettyTable
from jinja2 import Environment, FileSystemLoader
from treelib import Node, Tree

pp = pprint.PrettyPrinter(indent=1)

#general settings DO NOT CHANGE 
dcname = 'DC1'

#default windows tool
defaultwintool = 'xcp'

#xcp windows location
winpath = 'C:\\NetApp\\XCP'
xcpwinpath = 'C:\\NetApp\\XCP\\xcp.exe'
xcpwincopyparam = "-preserve-atime -acl -root"
xcpwinsyncparam = "-preserve-atime -acl -root"
xcpwinverifyparam = "-v -l -nodata -noatime -preserve-atime "

#robocopy windows location
robocopywinpath = 'C:\\NetApp\\XCP\\robocopy_wrapper.ps1'
robocopywinpathassess = 'C:\\NetApp\\XCP\\robocopy_wrapper.ps1'
robocopyargs = ' /COPY:DATSO /MIR /NP /DCOPY:DAT /MT:32 /R:0 /W:0 /TEE /BYTES /NDL '

#location of the script 
root = os.path.dirname(os.path.abspath(__file__))

#path to file containing the location of robocopy unicode log file (usefull for hebrew)
robocopylogpath = os.path.join(root,'windows','robocopy_log_file_dir')

#xcp repo and cache dir loaction 
xcprepopath = os.path.join(root,'system','xcp_repo')

#xcplinux path - need wrapper to support xcp 1.6
xcppath = os.path.join(root,'system','xcp_wrapper.sh')
xcplocation = '/usr/local/bin/xcp'

#xcp indexes path 
xcpindexespath = os.path.join(xcprepopath,'catalog','indexes')

#cache dir for current state 
cachedir = os.path.join(xcprepopath,'nomadcache')
#cachedir = os.path.join(root,'nomadcache')

#smartassess dir for current state 
smartassessdir = os.path.join(xcprepopath,'smartassess')

#path to nomad bin 
nomadpath = '/usr/local/bin/nomad'

#location for the jobs dir
jobsdir = os.path.join(xcprepopath,'jobs') 

#exclude dirictory files location
excludedir = os.path.join(xcprepopath,'excludedir') 

#file containing loaded jobs 
jobdictjson = os.path.join(jobsdir,'jobs.json')

#smartassess json jobs file
smartassessjobdictjson = os.path.join(smartassessdir,'smartassessjobs.json')

#job template dirs
ginga2templatedir = os.path.join(root,'template') 

#webtemplates 
webtemplatedir = os.path.join(root,'webtemplates') 

#file pload location within the webtempate dir
uploaddir = os.path.join(webtemplatedir,'upload') 

#cloudsync integration script 
cloudsyncscript = os.path.join(root,'cloudsync','cloudsync.py')

#log file location
logdirpath = os.path.join(root,'log') 
logfilepath = os.path.join(logdirpath,'xcption.log')

#creating the logs directory
if not os.path.isdir(logdirpath):
	try:
		os.mkdir(logdirpath)
	except Exception as e:
		logging.error("could not create log directoy:" + logdirpath)
		exit (1)

#default nomad job properties 
defaultjobcron = "0 0 * * * *" #nightly @ midnight
defaultcpu = 3000
defaultmemory = 800

#max logs for status -l 
maxloglinestodisplay = 50

#max syncs to keep per job (when sync count is bigger than this number older syncs will be deleted)
maxsyncsperjob = 10

#smartassess globals 
minsizekfortask_minborder = 0.5*1024*1024*1024 #512GB
mininodespertask_minborder = 100000 
maxjobs = 100

totaljobssizek = 0
totaljobsinode = 0
totaljobscreated = 0

#default http port for flask 
defaulthttpport = 1234

parent_parser = argparse.ArgumentParser(add_help=False)

parser = argparse.ArgumentParser()
parser.add_argument('-v','--version', help="print version information", action='store_true')
parser.add_argument('-d','--debug',   help="log debug messages to console", action='store_true')
subparser = parser.add_subparsers(dest='subparser_name', help='sub commands that can be used')

# create the sub commands 
parser_nodestatus   = subparser.add_parser('nodestatus', help='display cluster nodes status',parents=[parent_parser])	
parser_status       = subparser.add_parser('status',     help='display status',parents=[parent_parser])	
parser_assess       = subparser.add_parser('assess',     help='assess filesystem and create csv file',parents=[parent_parser])
parser_load         = subparser.add_parser('load',       help='load/update configuration from csv file',parents=[parent_parser])
parser_baseline     = subparser.add_parser('baseline',   help='start baseline (xcp copy)',parents=[parent_parser])
parser_sync         = subparser.add_parser('sync',       help='start schedule updates (xcp sync)',parents=[parent_parser])
parser_syncnow      = subparser.add_parser('syncnow',    help='initiate sync now',parents=[parent_parser])
parser_pause        = subparser.add_parser('pause',      help='disable sync schedule',parents=[parent_parser])
parser_resume       = subparser.add_parser('resume',     help='resume sync schedule',parents=[parent_parser])
parser_abort        = subparser.add_parser('abort',      help='abort running task')
parser_verify       = subparser.add_parser('verify',     help='start verify to validate consistency between source and destination (xcp verify)')
parser_delete       = subparser.add_parser('delete',     help='delete existing config',parents=[parent_parser])
parser_modify       = subparser.add_parser('modify',     help='modify task job',parents=[parent_parser])
parser_copydata     = subparser.add_parser('copy-data',  help='perfored monitored copy of source to destination (nfs only)',parents=[parent_parser])
parser_deletedata   = subparser.add_parser('delete-data',help='perfored monitored delete of data using xcp (nfs only)',parents=[parent_parser])
parser_nomad        = subparser.add_parser('nomad',      description='hidden command, usded to update xcption nomad cache',parents=[parent_parser])
parser_export       = subparser.add_parser('export',     help='export existing jobs to csv',parents=[parent_parser])
parser_web          = subparser.add_parser('web',        help='start web interface to display status',parents=[parent_parser])
parser_fileupload   = subparser.add_parser('fileupload', help='transfer files to all nodes, usefull for xcp license update on all nodes',parents=[parent_parser])

parser_status.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_status.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_status.add_argument('-t','--jobstatus',help="change the scope of the command to specific job status ex:complete,running,failed,pending,aborted", required=False,type=str,metavar='jobstatus')
parser_status.add_argument('-v','--verbose',help="provide verbose per phase info", required=False,action='store_true')
parser_status.add_argument('-p','--phase',help="change the scope of the command to specific phase ex:baseline,sync#,verify#,lastsync (requires -v/--verbose)", required=False,type=str,metavar='phase')
parser_status.add_argument('-n','--node',help="change the scope of the command to specific node (requires -v/--verbose)", required=False,type=str,metavar='node')
parser_status.add_argument('-e','--error',help="change the scope of the command to jobs with errors (requires -v/--verbose)", required=False,action='store_true')
parser_status.add_argument('-o','--output',help="output type: [csv|json]",choices=['csv','json'],required=False,type=str,metavar='output')
parser_status.add_argument('-l','--logs',help="display job logs", required=False,action='store_true')

parser_assess.add_argument('-s','--source',help="source nfs/cifs path",required=True,type=str)
parser_assess.add_argument('-d','--destination',help="destination nfs/cifs path",required=True,type=str)
parser_assess.add_argument('-l','--depth',help="filesystem depth to create jobs, range of 1-12",required=True,type=int)
parser_assess.add_argument('-c','--csvfile',help="output CSV file",required=True,type=str)
parser_assess.add_argument('-p','--cpu',help="CPU allocation in MHz for each job",required=False,type=int)
parser_assess.add_argument('-m','--ram',help="RAM allocation in MB for each job",required=False,type=int)
parser_assess.add_argument('-r','--robocopy',help="use robocopy instead of xcp for windows jobs", required=False,action='store_true')
parser_assess.add_argument('-u','--failbackuser',help="failback user required for xcp for windows jobs, see xcp.exe copy -h", required=False,type=str)
parser_assess.add_argument('-g','--failbackgroup',help="failback group required for xcp for windows jobs, see xcp.exe copy -h", required=False,type=str)
parser_assess.add_argument('-j','--job',help="xcption job name", required=False,type=str,metavar='jobname')
parser_assess.add_argument('-n','--cron',help="create all task with schedule ", required=False,type=str,metavar='cron')
parser_assess.add_argument('-a','--acl',help="use no-win-acl to prevent acl copy for cifs jobs or nfs4-acl to enable nfs4-acl copy", choices=['no-win-acl','nfs4-acl'], required=False,type=str,metavar='aclcopy')

parser_copydata.add_argument('-s','--source',help="source nfs path (nfssrv:/mount)",required=True,type=str)
parser_copydata.add_argument('-d','--destination',help="destination nfs path (nfssrv:/mount)",required=True,type=str)
parser_copydata.add_argument('-f','--force',help="force copy event if destination contains files", required=False,action='store_true')
parser_copydata.add_argument('-a','--nfs4acl',help="use to include nfs4-acl", required=False,action='store_true')

parser_deletedata.add_argument('-s','--source',help="source nfs path (nfssrv:/mount)",required=True,type=str)
parser_deletedata.add_argument('-f','--force',help="force delete data without confirmation", required=False,action='store_true')

parser_load.add_argument('-c','--csvfile',help="input CSV file with the following columns: Job Name,SRC Path,DST Path,Schedule,CPU,Memory",required=True,type=str)
parser_load.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_load.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_load.add_argument('-v','--novalidation',help="load can be faster for windows paths since valaidation is prevented", required=False,action='store_true')

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
parser_abort.add_argument('-t','--type',help="specify the type of job to abort, can be baseline,sync or verify", choices=['baseline','sync','verify'],required=True,type=str,metavar='type')
parser_abort.add_argument('-f','--force',help="force abort", required=False,action='store_true')

parser_verify.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_verify.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_verify.add_argument('-q','--quick',help="perform quicker verify by using xcp random file verify (1 out of 1000)", required=False,action='store_true')
parser_verify.add_argument('-w','--withdata',help="perform deep data verification (xcp verify without the -nodata flag)", required=False,action='store_true')
parser_verify.add_argument('-r','--reverse',help="perform reverse verify (dst will be compared to the src)", required=False,action='store_true')

parser_delete.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_delete.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_delete.add_argument('-f','--force',help="force delete", required=False,action='store_true')

parser_modify.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_modify.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_modify.add_argument('-t','--tojob',help="move selected tasks to this job", required=False,type=str,metavar='tojob')
parser_modify.add_argument('-c','--cron',help="modify the sync schedule for this job", required=False,type=str,metavar='cron')
parser_modify.add_argument('-p','--cpu',help="modify CPU allocation in MHz for each job",required=False,type=int)
parser_modify.add_argument('-m','--ram',help="modify RAM allocation in MB for each job",required=False,type=int)
parser_modify.add_argument('-f','--force',help="force modify", required=False,action='store_true')

parser_export.add_argument('-c','--csvfile',help="input CSV file with the following columns: Job Name,SRC Path,DST Path,Schedule,CPU,Memory",required=True,type=str)
parser_export.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_export.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_web.add_argument('-p','--port',help="tcp port to start the web server on (default:"+str(defaulthttpport)+')', required=False,default=defaulthttpport,type=int,metavar='port')

parser_fileupload.add_argument('-f','--file',help="path to upload", required=True,type=str,metavar='file')
parser_fileupload.add_argument('-l','--linuxpath',help="destination path for linux hosts. license file default: /opt/NetApp/xFiles/xcp/license", required=False,type=str,metavar='linuxpath')
parser_fileupload.add_argument('-w','--windowspath',help="destination path for linux hosts. license file default: C:\\NetApp\\XCP\\license", required=False,type=str,metavar='windowspath')
parser_fileupload.add_argument('-p','--port',help="tcp port to start the web server on (default:"+str(defaulthttpport)+')', required=False,default=defaulthttpport,type=int,metavar='port')

parser_smartassess   = subparser.add_parser('smartassess',help='create tasks based on capacity and file count (nfs only)',parents=[parent_parser])

action_subparser = parser_smartassess.add_subparsers(title="action",dest="smartassess_command")                                                                                                               
parser_smartassess_start     = action_subparser.add_parser('start',help='scan src to create tasks based on capacity and inode count (nfs only)',parents=[parent_parser])
parser_smartassess_status    = action_subparser.add_parser('status',help='display scan status and filesystem info',parents=[parent_parser])
parser_smartassess_createcsv = action_subparser.add_parser('createcsv',help='create csv job file based on the scan results',parents=[parent_parser])
parser_smartassess_delete    = action_subparser.add_parser('delete',help='delete existing scan information',parents=[parent_parser])

parser_smartassess_start.add_argument('-s','--source',help="source nfs path (nfssrv:/mount)",required=True,type=str)
parser_smartassess_start.add_argument('-l','--depth',help="filesystem depth to create jobs, range of 1-12",required=True,type=int)
parser_smartassess_start.add_argument('-k','--locate-cross-task-hardlink',help="located hardlinks that will be converted to regular files when splited to diffrent jobs",required=False,action='store_true')

#check capacity parameter 
def checkcapacity (capacity):
	matchObj = re.match("^(\d+)(\s+)?(K|B|M|G|T)(i)?B$",capacity)
	if not matchObj:
		raise argparse.ArgumentTypeError("invalid capacity")
	return capacity

#convert K to human readable 
def k_to_hr (k):

	hr = format(k,',')+'KiB'
	if 1024 <= k <= 1024*1024:
		hr = format(int(k/1024),',')+'MiB'
	elif 1024*1024 <= k <= 1024*1024*1024:
		hr = format(int(k/1024/1024),',')+'GiB'
	elif 1024*1024*1024*1024 <= k:
		hr = format(int(k/1024/1024/1024),',')+'TiB'
	return hr	

parser_smartassess_status.add_argument('-s','--source',help="change the scope of the command to specific source path", required=False,type=str,metavar='srcpath')
parser_smartassess_status.add_argument('-i','--min-inodes',help="minimum required inodes per task default is:"+format(mininodespertask_minborder,','), required=False,type=int,metavar='mininodes')
parser_smartassess_status.add_argument('-a','--min-capacity',help="minimum required capacity per task default is:"+k_to_hr(minsizekfortask_minborder), required=False,type=checkcapacity,metavar='mincapacity')
parser_smartassess_status.add_argument('-t','--tasks',help="provide verbose task information per suggested path", required=False,action='store_true')
parser_smartassess_status.add_argument('-l','--hardlinks',help="provide cross task hardlink information per suggested path", required=False,action='store_true')

parser_smartassess_createcsv.add_argument('-s','--source',help="create CSV for the following src", required=True,type=str,metavar='srcpath')
parser_smartassess_createcsv.add_argument('-d','--destination',help="set destination path", required=True,type=str,metavar='dstpath')
parser_smartassess_createcsv.add_argument('-c','--csvfile',help="output CSV file",required=True,type=str)
parser_smartassess_createcsv.add_argument('-i','--min-inodes',help="minimum required inodes per task default is:"+format(mininodespertask_minborder,','), required=False,type=int,metavar='maxinodes')
parser_smartassess_createcsv.add_argument('-a','--min-capacity',help="minimum required capacity per task default is:"+k_to_hr(minsizekfortask_minborder), required=False,type=checkcapacity,metavar='mincapacity')
parser_smartassess_createcsv.add_argument('-p','--cpu',help="CPU allocation in MHz for each job",required=False,type=int)
parser_smartassess_createcsv.add_argument('-m','--ram',help="RAM allocation in MB for each job",required=False,type=int)
parser_smartassess_createcsv.add_argument('-j','--job',help="xcption job name", required=False,type=str,metavar='jobname')

parser_smartassess_delete.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_smartassess_delete.add_argument('-f','--force',help="force delete", required=False,action='store_true')

#parser_smartassess.print_help()
args = parser.parse_args(args=None if sys.argv[1:] else ['--help'])

#initialize logging 
log = logging.getLogger()
log.setLevel(logging.DEBUG)
logging.getLogger('requests').setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
formatterdebug = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')

# create file handler which logs even debug messages
#fh = logging.FileHandler(logfilepath)
fh = logging.handlers.RotatingFileHandler(logfilepath, maxBytes=1048576, backupCount=5)
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
smartassessdict = {}
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
	except Exception as e:
		assert not job 
	return job

#load smartassess from json 
def load_smartassess_jobs_from_json (jobdictjson):
	global smartassessdict
	if os.path.exists(jobdictjson):
		try:
			logging.debug("loading existing json file:"+jobdictjson)
			with open(jobdictjson, 'r') as f:
				smartassessdict = json.load(f)
		except Exception as e:
			logging.debug("could not load existing json file:"+jobdictjson)


#load jobsdict from json 
def load_jobs_from_json (jobdictjson):
	global jobsdict
	if os.path.exists(jobdictjson):
		try:
			logging.debug("loading existing json file:"+jobdictjson)
			with open(jobdictjson, 'r') as f:
				jobsdict = json.load(f)
		except Exception as e:
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
					except Exception as e:
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
					if tool == '': tool = defaultwintool

					failbackuser =''
					if 7 < len(row): failbackuser  = row[7]					

					failbackgroup =''
					if 8 < len(row): failbackgroup  = row[8]	

					excludedirfile = ''
					if 9 < len(row) and row[9] != '' : excludedirfile = os.path.join(excludedir,row[9])
					#check if exclude file exists 
					if excludedirfile != '' and not os.path.isfile(excludedirfile):
						logging.error("exclude dir file:"+excludedirfile+" for src:"+src+" could not be found")
						exit(1)
					
					aclcopy = ''
					if 10 < len(row) and row[10] != '': aclcopy = row[10]
					if aclcopy != '':
						if not aclcopy in ['nfs4-acl','no-win-acl']:
							logging.error("provided acl copy method:"+aclcopy+" for src:"+src+" is not supported. can be one of the following: nfs4-acl,no-win-acl")
							exit(1)
						if aclcopy == 'nfs4-acl' and ostype == 'windows':
							logging.error("acl type: nfs4-acl is not supported for windows task")
							exit(1)
						if aclcopy == 'no-win-acl' and ostype == 'linux':
							logging.error("acl type: nfs4-acl is not supported for windows task")
							exit(1)
					
					logging.debug("parsing entry for job:" + jobname	 + " src:" + src + " dst:" + dst + " ostype:" + ostype + " tool:"+tool+" failbackuser:"+failbackuser+" failback group:"+failbackgroup+" exclude dir file:"+excludedirfile) 

					srcbase = src.replace(':/','-_')
					srcbase = srcbase.replace('/','_')
					srcbase = srcbase.replace(' ','-')
					srcbase = srcbase.replace('\\','_')
					srcbase = srcbase.replace('$','_dollar')
					srcbase = srcbase.replace('@','_at')
					
					dstbase = dst.replace(':/','-_')
					dstbase = dstbase.replace('/','_')
					dstbase = dstbase.replace(' ','-')
					dstbase = dstbase.replace('\\','_')
					dstbase = dstbase.replace('$','_dollar')
					dstbase = dstbase.replace('@','_at')

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
					
					createcloudsync = False
					if tool == 'cloudsync':
						cloudsync_cmd = [cloudsyncscript,'validate','-s',escapestr(src),'-d',escapestr(dst)]
						cloudsyncrel = {}
						try:
							validatejson = subprocess.check_output(cloudsync_cmd,stderr=subprocess.STDOUT)
							cloudsyncrel = json.loads(validatejson.decode('utf-8'))							
						except Exception as e:
							logging.error("cannot validate source/destination paths for cloudsync src:"+src+" dst:"+dst)
							os.system(' '.join(cloudsync_cmd))
							exit(1)	
						if cloudsyncrel: 
							log.info("cloudsync relationship for src:"+src+" dst:"+dst+" already exists. status:"+cloudsyncrel['activity']['status']+' type:"'+cloudsyncrel['activity']['type']+'"')
						else:
							log.info("cloudsync relationship for src:"+src+" dst:"+dst+" does not exists")							
							createcloudsync = True

						#set required params 
						srchost=''; srcpath=''; dsthost=''; dstpath=''; 
					else:
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

								if aclcopy == 'nfs4-acl':
									if subprocess.call( [ 'mount', '-t', 'nfs4', src, '/tmp/temp_mount' ],stderr=subprocess.STDOUT):
										logging.error("cannot mount src:"+src+" using nfs version 4 which is required for nfs4 acl processing")
										exit(1)					
									subprocess.call( [ 'umount', '/tmp/temp_mount' ],stderr=subprocess.STDOUT)

									if subprocess.call( [ 'mount', '-t', 'nfs4', dst, '/tmp/temp_mount' ],stderr=subprocess.STDOUT):
										logging.error("cannot mount dst:"+dst+"using nfs version 4 which is required for nfs4 acl processing")
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

							if not args.novalidation:
								logging.info("validating src:" + src + " and dst:" + dst+ " cifs paths are available from one of the windows servers") 
								
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
							else:
								logging.debug("skipping path validation src:"+src+" dst:"+dst)
								
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
					jobsdict[jobname][src]["aclcopy"] = aclcopy
					jobsdict[jobname][src]["createcloudsync"] = createcloudsync

					logging.debug("parsed the following relationship:"+src+" -> "+dst)

					dstdict[dst] = 1
					line_count += 1
	#dumping jobsdict to json file 
	try:
		with open(jobdictjson, 'w') as fp:
			json.dump(jobsdict, fp)
		fp.close()
	except Exception as e:
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
		
		#hclcontent = hclcontent.replace('\n', '').replace('\r', '').replace('\t','')
		
		hcljson = {}
		hcljson['JobHCL'] = hclcontent
		hcljson['Canonicalize'] = True

		response = requests.post(nomadapiurl+'jobs/parse',json=hcljson)
		if response.ok:
			nomadjobdict={}
			nomadjobdict['Job'] = json.loads(response.content)
			try:
			 	nomadout = n.job.plan_job(nomadjobname, nomadjobdict)
			except Exception as e:
			 	logging.error("job planning failed for job:"+nomadjobname+" please run: nomad job plan "+hclpath+ " for more details") 
			 	exit(1)
			logging.debug("starting job:"+nomadjobname)
			try:
				nomadout = n.job.register_job(nomadjobname, nomadjobdict)
			except Exception as e:
				logging.error("job:"+nomadjobname+" creation failed") 
				exit(1)
		else:
			logging.error("could not start "+nomadjobname)
			return False

	return True

def check_job_status (jobname,log=False):
	jobdetails = {}
	try:	
		jobdetails = n.job.get_job(jobname)
	except Exception as e:
		jobdetails = None

	if not jobdetails:
		logging.debug("job:"+jobname+" does not exist")
		return False,'',''

	#if job exists retrun the allocation status
	results ={}
	results['stdout'] = ''
	results['stderr'] = ''
	results['status'] = 'unknown'
	#will be used for fileupload 
	results['allocations'] = {}
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
				results['allocations'] = jobdetails

			except Exception as e:
				results['status'] = 'unknown'	


	if log == True and (results['status'] == 'complete' or results['status'] == 'failed') and allocid != '':
		response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+jobname+'&type=stdout&plain=true')
		if response.ok:
			logging.debug("stdout log for job:"+jobname+" is available using api")								
			lines = response.content.splitlines()
			if lines:
				results['stdout'] = response.content.decode('utf-8')						
		
		response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+jobname+'&type=stderr&plain=true')
		if response.ok:
			logging.debug("stderr log for job:"+jobname+" is available using api")								
			lines = response.content.splitlines()
			if lines:
				results['stderr'] = response.content.decode('utf-8')

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
	except Exception as e:
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
	except Exception as e:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_baseline.txt'))
		exit(1)
	
	try:	
		sync_template = env.get_template('nomad_sync.txt')
	except Exception as e:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_sync.txt'))
		exit(1)
	
	try:
		verify_template = env.get_template('nomad_verify.txt')
	except Exception as e:
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
					aclcopy           = jobdetails['aclcopy']

					if ostype == 'linux': xcpbinpath = xcppath
					if ostype == 'windows': xcpbinpath = 'powershell'
					if tool == 'cloudsync': xcpbinpath = cloudsyncscript
					
					#creating baseline job 
					baseline_job_file = os.path.join(jobdir,baseline_job_name+'.hcl')	
					logging.info("creating/updating relationship configs for src:"+src)
					logging.debug("creating baseline job file: " + baseline_job_file)				

					if tool == 'cloudsync':
						if 'createcloudsync' in jobdetails:
							if jobdetails['createcloudsync']:
								cloudsync_cmd = [cloudsyncscript,'create','-s',escapestr(src),'-d',escapestr(dst)]
								try:
									subprocess.check_output(cloudsync_cmd,stderr=subprocess.STDOUT)
								except Exception as e:
									logging.error("cannot create cloudsync relationship src:"+src+" dst:"+dst)
									os.system(' '.join(cloudsync_cmd))
															
						cmdargs = "baseline\",\"-s\",\""+src+"\",\"-d\",\""+dst

					if ostype == 'linux' and tool != 'cloudsync':
						aclcopyarg = ''
						if aclcopy == 'nfs4-acl':  
							aclcopyarg = "\"-acl4\","
						if excludedirfile == '':
							cmdargs = "copy\","+aclcopyarg+"\"-newid\",\""+xcpindexname+"\",\""+src+"\",\""+dst
						else:
							cmdargs = "copy\","+aclcopyarg+"\"-newid\",\""+xcpindexname+"\",\"-exclude\",\"paths('"+excludedirfile+"')\",\""+src+"\",\""+dst

					if ostype == 'windows' and tool == 'xcp': 
						if aclcopy == 'no-win-acl':
							xcpwincopyparam = "-preserve-atime"
						else:
							xcpwincopyparam = "-preserve-atime -acl -root"

						if excludedirfile == '':						
							cmdargs = escapestr(xcpwinpath+" copy "+xcpwincopyparam+" -fallback-user \""+failbackuser+"\" -fallback-group \""+failbackgroup+"\" \""+src+"\" \""+dst+"\"")
						else:
							logging.error("exclude directory is not yet supported when xcp for windows is used for src:" + src)	
							exit(1)

					robocopyunicodelogpath = ''
					robocopyexcludedirs = ''
					if ostype == 'windows' and tool == 'robocopy': 
						try:
							f = open(robocopylogpath)
							robocopyunicodelogpath = f.readline().rstrip()
							f.close()                        
						except Exception as e:
							logging.debug("robocopy unicode log path cannot be opened: " + robocopylogpath)	
						
						if robocopyunicodelogpath != '':
							robocopyunicodelogpath = " /UNILOG:"+robocopyunicodelogpath+"\\"+xcpindexname+".log"

						if aclcopy == 'no-win-acl':
							robocopyargs = ' /COPY:DAT /MIR /NP /DCOPY:DAT /MT:32 /R:0 /W:0 /TEE /BYTES /NDL '
						else:
							robocopyargs = ' /COPY:DATSO /MIR /NP /DCOPY:DAT /MT:32 /R:0 /W:0 /TEE /BYTES /NDL '

						if excludedirfile == '':						
							cmdargs = escapestr(robocopywinpath+ " \""+src+"\" \""+dst+"\""+robocopyargs+robocopyunicodelogpath)
						else:
							try:
								f = open(excludedirfile)
								excludepaths = f.readlines()
								excludepaths = [x.strip() for x in excludepaths]
								excludepaths = ['"' + path for path in excludepaths] 
								excludepaths = [path + '"' for path in excludepaths] 
								robocopyexcludedirs = " /XD "+ ' '.join(excludepaths)
								f.close()                        
								logging.debug("exclude directories for robocopy: " + robocopyexcludedirs)
							except Exception as e:
								logging.error("exclude directories file cannot be parsed: " + robocopylogpath)	
								exit(1)

							cmdargs = escapestr(robocopywinpath+ " \""+src+"\" \""+dst+"\""+robocopyargs+robocopyunicodelogpath+robocopyexcludedirs)
                    
					
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

					if tool == 'cloudsync':
						cmdargs = "sync\",\"-s\",\""+src+"\",\"-d\",\""+dst								
					
					if ostype == 'linux' and tool != 'cloudsync':
						cmdargs = "sync\",\"-id\",\""+xcpindexname

					if ostype == 'windows' and tool == 'xcp': 
						if aclcopy == 'no-win-acl':
							xcpwinsyncparam = "-preserve-atime"
						else:
							xcpwinsyncparam = "-preserve-atime -acl -root"						
						cmdargs = escapestr(xcpwinpath+" sync "+xcpwinsyncparam+" -fallback-user \""+failbackuser+"\" -fallback-group \""+failbackgroup+"\" \""+src+"\" \""+dst+"\"")
					if ostype == 'windows' and tool == 'robocopy': 
						if excludedirfile == '':
							cmdargs = escapestr(robocopywinpath+ " \""+src+"\" \""+dst+"\""+robocopyargs+robocopyunicodelogpath)
						else:
							cmdargs = escapestr(robocopywinpath+ " \""+src+"\" \""+dst+"\""+robocopyargs+robocopyunicodelogpath+robocopyexcludedirs)

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
					
					if tool=='cloudsync':
						cmdargs = "validate\",\"-s\",\""+src+"\",\"-d\",\""+dst

					if ostype == 'linux' and tool != 'cloudsync':  
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
	except Exception as e:
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
				logging.error("job config directory:" + jobdir + " not exists") 
				exit (1)
					
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					
					dst                 = jobdetails['dst']
					srcbase             = jobdetails['srcbase']
					dstbase             = jobdetails['dstbase']
					nomadjobname        = jobdetails[action+'_job_name']
					xcpindexname        = jobdetails['xcpindexname']	
					ostype              = jobdetails['ostype']
					tool                = jobdetails['tool']
                    
					try:	
						job = n.job.get_job(nomadjobname)
					except Exception as e:
						job = ''
					if job:
						logging.debug("job name:"+nomadjobname+" already exists") 
                    
					baseline_job_name   = jobdetails['baseline_job_name']				
					baselinecachedir    = os.path.join(cachedir,'job_'+baseline_job_name)                        
					if os.path.exists(baselinecachedir):
						logging.debug("baseline job dir:"+baselinecachedir+" exists") 
                    
					#validate if there is clousync job that been created exteranly using cloudsync ui
					cloudsyncrel = {} 
					if action=='baseline' and tool=='cloudsync' and not (job or os.path.exists(baselinecachedir)):
						cloudsync_cmd = [cloudsyncscript,'validate','-s',src,'-d',dst]
						cloudsyncrel = {}
						try:
							validatejson = subprocess.check_output(cloudsync_cmd,stderr=subprocess.STDOUT)
							cloudsyncrel = json.loads(validatejson.decode('utf-8'))							
						except Exception as e:
							logging.error("cannot validate source/destination paths for cloudsync src:"+src+" dst:"+dst)
							os.system(' '.join(cloudsync_cmd))
							exit(1)	
						if cloudsyncrel: 
							log.debug("cloudsync relationship for src:"+src+" dest:"+dst+" already exists. status:"+cloudsyncrel['activity']['status']+' type:"'+cloudsyncrel['activity']['type']+'"')

					forcebaseline = False 
					if action == 'baseline' and (job or os.path.exists(baselinecachedir)):
						if not force:
							if not (cloudsyncrel and not (job or os.path.exists(baselinecachedir))):
								logging.warning("baseline job already exists for src:"+src+" to dst:"+dst+". use --force to force new baseline") 
								continue
						else:
							if cloudsyncrel and not (job or os.path.exists(baselinecachedir)):
								logging.warning("cloudsync job already exists for src:"+src+" to dst:"+dst+". use --force import it to XCPtion") 	
							if query_yes_no("are you sure you want to rebaseline "+src+" to "+dst+" ?",'no'):
								logging.info("destroying existing baseline job")
								if ostype == 'linux' and (tool == 'xcp' or tool == '') and tool != 'cloudsync':
									logging.debug("destroying xcp index:"+xcplocation+' diag -rmid '+xcpindexname)
									DEVNULL = open(os.devnull, 'wb')
									if subprocess.call( [ xcplocation, 'diag', '-rmid', xcpindexname ],stdout=DEVNULL,stderr=DEVNULL):
										logging.debug("failed to delete xcp index:"+xcpindexname)					
								#delete baseline jobs 
								logging.debug("destroying job prefixed by:"+nomadjobname)
								delete_job_by_prefix(nomadjobname)

								baselinecachedir = os.path.join(cachedir,'job_'+nomadjobname)
								if os.path.exists(baselinecachedir):
									logging.debug("delete baseline cache dir:"+baselinecachedir)
									try:
										rmout = shutil.rmtree(baselinecachedir) 
									except Exception as e:
										logging.error("could not delete baseline cache dir:"+baselinecachedir)								

								#pausing sync job if exists 
								syncjobname = jobdetails['sync_job_name']
								try:	
									syncjob = n.job.get_job(syncjobname)
								except Exception as e:
									syncjob = False
								
								if syncjob:
									logging.info("pausing existing sync job for src:"+src)
									syncjob["Stop"] = True
									syncjob1={}
									syncjob1['Job']=syncjob
									nomadout = n.job.register_job(syncjobname, syncjob1)

								forcebaseline=True

					if (action != 'baseline' and job) or forcebaseline or not job:
						jobfile = os.path.join(jobdir,nomadjobname+'.hcl')		
						if not os.path.exists(jobfile): 
							logging.warning("job:"+nomadjobname+" could not be found, please load first") 
						else:
							logging.info("starting/updating "+action+" job for src:" + src+ " dst:"+dst) 


							#if action is verify recreate job file based on the quick option
							if action == 'verify':
								logging.debug("recreting job:"+nomadjobname+" to support quick verify") 
								#recreating verify job to support the quick option 
								verify_job_name = jobdetails['verify_job_name']
								excludedirfile  = jobdetails['excludedirfile']
								memory          = jobdetails['memory']
								cpu             = jobdetails['cpu'] 

								verify_job_file = os.path.join(jobdir,verify_job_name+'.hcl')	
								logging.debug("recreating verify job file: " + verify_job_file)	

								nodata = ",\"-nodata\""
								if args.withdata: nodata=''

								if not args.reverse:
									srcverify = src 
									dstverify = dst 
								else:
									srcverify = dst
									dstverify = src
								
								if ostype == 'linux' and not args.quick:  
									xcpbinpath = xcppath
									if excludedirfile == '':
										cmdargs = "verify\",\"-v\",\"-noid\""+nodata+",\""+srcverify+"\",\""+dstverify
									else:
										cmdargs = "verify\",\"-v\",\"-noid\""+nodata+",\"-match\",\"not paths('"+excludedirfile+"')\",\""+srcverify+"\",\""+dstverify
								
								if ostype == 'linux' and args.quick:  
									xcpbinpath = xcppath
									if excludedirfile == '':
										cmdargs = "verify\",\"-v\",\"-noid\""+nodata+",\"-match\",\"type==f and rand(1000)\",\""+srcverify+"\",\""+dstverify
									else:
										cmdargs = "verify\",\"-v\",\"-noid\""+nodata+",\"-match\",\"not paths('"+excludedirfile+"') and type==f and rand(1000)\",\""+src+"\",\""+dst
									
								if ostype == 'windows': 
									xcpbinpath = 'powershell'
									verifyparam = xcpwinverifyparam
									if args.withdata: verifyparam = xcpwinverifyparam.replace("-nodata ","")
									if not args.quick:
										cmdargs = escapestr(xcpwinpath+' verify '+verifyparam+' "'+srcverify+'" "'+dstverify+'"')
									else:
										cmdargs = escapestr(xcpwinpath+' verify '+verifyparam+' -match "rand(1000)" "'+srcverify+'" "'+dstverify+'"')


								templates_dir = ginga2templatedir
								env = Environment(loader=FileSystemLoader(templates_dir) )

								try:
									verify_template = env.get_template('nomad_verify.txt')
								except Exception as e:
									logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_scan.txt'))
									exit(1)
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
							

							nomadjobjson = subprocess.check_output([ nomadpath, 'run','-output',jobfile])
							nomadjobdict = json.loads(nomadjobjson)

							try:
								nomadout = n.job.plan_job(nomadjobname, nomadjobdict)
							except Exception as e:
								logging.error("job planning failed for job:"+nomadjobname+" please run: nomad job plan "+jobfile+ " for more details") 
								exit(1)

							baselinejobname = jobdetails['baseline_job_name']
							baselinestatus = check_baseline_job_status(baselinejobname)
							
							#if sync job and baseline was not started disable schedule for sync 
							if action == 'sync':
								if baselinestatus != 'baseline is complete':
									logging.warning(action+" will be paused for src:"+src+" to dst:"+dst+" - "+baselinestatus.lower())									
									nomadjobdict["Job"]["Stop"] = True
								else:
									logging.debug("baseline is completed, can start "+action)

							#if action is verify 
							if action == 'verify':
								if tool=='cloudsync':
									logging.warning(action+" is not supported for cloudsync")
									continue
								if baselinestatus != 'baseline is complete':
									logging.warning(action+" is not possiable:"+baselinestatus.lower())									
									continue
								else:
									logging.debug("baseline is completed, can start "+action)

							nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
							try:
								job = n.job.get_job(nomadjobname)
							except Exception as e:
								logging.error("job:"+nomadjobname+" creation failed") 
								exit(1)

							#force immediate baseline / verify
							if action == 'baseline' or (action == 'verify' and baselinestatus == 'baseline is complete'):
								response = requests.post(nomadapiurl+'job/'+nomadjobname+'/periodic/force')	
								if not response.ok:
									logging.error("job:"+nomadjobname+" force start failed") 
									exit(1)

#tail n lines of a file 
# def tail(file, n=1, bs=1024):
#     f = open(file)
#     f.seek(0,2)
#     l = 1-f.read(1).count('\n')
#     B = f.tell()
#     while n >= l and B > 0:
#             block = min(bs, B)
#             B -= block
#             f.seek(B, 0)
#             l += f.read(block).count('\n')
#     f.seek(B, 0)
#     l = min(l,n)
#     lines = f.readlines()[-l:]
#     f.close()
#     return lines

def tail (file,n=1):
	tailfile = ''
	if os.path.isfile:
		logging.debug("starting log tail:"+file)
		tailfile = subprocess.check_output(['tail','-'+str(n),file])
		logging.debug("ending log tail")
	else:
		logging.debug("can't tail:"+file)

	return tailfile.splitlines(True)

#parse stats from xcp logs, logs can be retrived from api or file in the repo
def parse_stats_from_log (type,name,logtype,task='none'):
#def parse_stats_from_log (type,name,task='none',jobstatus='unknow'):
	#output dict
	logging.debug("starting log parsing type:"+type+" name:"+name+" type:"+type)
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
			seperator = b""
			results['content'] = seperator.join(lines).decode("utf-8")
			results['logfilepath'] = logfilepath
			results['logfilesize'] = logfilesize

		except Exception as e:
			#print(e)
			logging.debug("cannot read log file:"+logfilepath)	

		#store also other logtype
		otherlogfilepath = name
		if logtype == 'stderr':
			otherlogfilepath = otherlogfilepath.replace('stderr','stdout',1) 
			results['stderrlogpath'] = logfilepath
			results['stdoutlogpath'] = otherlogfilepath
		else:
			otherlogfilepath = otherlogfilepath.replace('stdout','stderr',1) 
			results['stdoutlogpath'] = logfilepath
			results['stderrlogpath'] = otherlogfilepath			

		results['stdoutlogexists'] = False
		results['stderrlogexists'] = False
		if os.path.isfile(results['stdoutlogpath']): results['stdoutlogexists'] = True
		if os.path.isfile(results['stderrlogpath']): results['stderrlogexists'] = True

		try:
			logfilesize = os.path.getsize(otherlogfilepath)			

			lines = tail(otherlogfilepath,maxloglinestodisplay)
			seperator = b""
			results['contentotherlog'] = seperator.join(lines).decode("utf-8")
			results['logfileotherpath'] = otherlogfilepath
			results['logfileothersize'] = logfilesize
		except Exception as e:
			logging.debug("cannot read other log file:"+otherlogfilepath)							
			results['contentotherlog'] = ''
	elif type == 'alloc':						
		#try to get the log file using api
		allocid = name
		response = requests.get(nomadapiurl+'client/fs/logs/'+allocid+'?task='+task+'&type='+logtype+'&plain=true')
		if response.ok and re.search("\d", response.content, re.M|re.I):
			logging.debug("log for job:"+allocid+" is available using api")								
			lines = response.content.splitlines()
			if lines:
				#lastline = lines[-1]
				results['content'] = response.content.decode('utf-8')
		else:
			logging.debug("log for job:"+allocid+" is not available using api")																								

	if results['content'] != '':
		for match in re.finditer(r"(.*([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) ?(\bscanned\b|\breviewed\b|\bcompared\b).+)",results['content'],re.M|re.I):
			lastline = match.group(0)
		results['lastline'] = lastline

		#updated for xcp1.6 log format:
		for match in re.finditer(r"Total Time\s+\:\s+(\S+[s|m|h])\.?$",results['content'],re.M|re.I):
			results['time'] = match.group(1)		
		if 'time' in results:
			for match in re.finditer(r"Speed\s+\:.+,\s+([-+]?[0-9]*\.?[0-9]+ \SiB out \([-+]?[0-9]*\.?[0-9]+( \SiB)?\/s\))",results['content'],re.M|re.I):
				results['bwout'] = match.group(1)
		
		# for cases when xcp failed buy did not return exit code 
		# example: Cannot start sync: 0.6 GiB memory available, 5.0 total, at least 2 GiB required
		if not lastline and logtype == 'stderr':
			for match in re.finditer(r"Cannot start ?(\bcopy\b|\bsync\b|\bverify\b)\:",results['content'],re.M|re.I):
				results['failure'] = True
			for match in re.finditer(r"xcp: ERROR: License file",results['content'],re.M|re.I):
				results['failure'] = True
	
	if results['contentotherlog'] != '':
		for match in re.finditer(r"(.*([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) ?(\bscanned\b|\breviewed\b|\bcompared\b).+)",results['contentotherlog'],re.M|re.I):
			otherloglastline = match.group(0)
		results['otherloglastline'] = otherloglastline
		#updated for xcp1.6 log format:
		for match in re.finditer(r"Total Time\s+\:\s+(\S+[s|m|h])\.?$",results['contentotherlog'],re.M|re.I):
			results['time'] = match.group(1)		
		if 'time' in results:
			for match in re.finditer(r"Speed\s+\:.+,\s+([-+]?[0-9]*\.?[0-9]+ \SiB out \([-+]?[0-9]*\.?[0-9]+( \SiB)?\/s\))",results['contentotherlog'],re.M|re.I):
				results['bwout'] = match.group(1)
		#if otherloglastline != '' and lastline == '':
        #xcp for windiws displays the summary in the stderr when there are errors 
		if otherloglastline != '':
			lastline = otherloglastline	
	
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
			if 	matchObj.group(1) != '0':		
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

		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) removes", lastline, re.M|re.I)
		if matchObj: 
			results['removes'] = matchObj.group(1)
		
		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) rmdirs", lastline, re.M|re.I)
		if matchObj: 
			results['rmdirs'] = matchObj.group(1)			

		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) file.gone", lastline, re.M|re.I)
		if matchObj: 
			if not re.search(" gone\,.+ file\.gone",lastline, re.M|re.I):
				if not 'gone' in results: results['gone'] = 0
				results['gone'] += int(matchObj.group(1).replace(',',''))

		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?) dir.gone", lastline, re.M|re.I)
		if matchObj: 
			if not re.search (" gone\,.+ dir\.gone",lastline, re.M|re.I):
				if not 'gone' in results: results['gone'] = 0
				results['gone'] += int(matchObj.group(1).replace(',',''))

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

		matchObj = re.search("([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?\%?|\d+) (found )?\(([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) have data\)", otherloglastline, re.M|re.I)
		if matchObj: 
			results['found'] = matchObj.group(1)
			results['withdata'] = matchObj.group(2)
			if results['found'] == '100%': 
				results['verified']='yes'
				results['found']=results['scanned']
			else:
				results['found']=format(int(results['found'].replace(',','')),',')
		
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
		
		#cloudsync broker name
		matchObj = re.search("broker:(\S+)\s", lastline, re.M|re.I)
		if matchObj:		
			results['broker'] = matchObj.group(1)

	
	#future optimization for status 
#	if type == 'file':
#		logjsonfile = re.sub('\.log$', '.json', logfilepath)
#		
#		logging.debug("storing log data in json file:"+logjsonfile)								
#		try:
#			# Writing JSON data
#			with open(logjsonfile, 'w') as f:
#				json.dump(results, f)
#		except Exception as e:
#			logging.debug("failed storing log data in json file:"+logjsonfile)								
	logging.debug("ending log parsing type:"+type+" name:"+name+" type:"+type)
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
	return '{:}d{:02}h{:02}m{:02}s'.format(int(delta.days),int(hours), int(minutes), int(seconds))

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
	n_2 = int(int(n) / 2 - 3)
	# whatever's left
	n_1 = int(n - n_2 - 3)
	return '{0}...{1}'.format(s[:n_1], s[-n_2:])

#create eneral status json 
def addtogeneralstatusjson(details,jsongeneraldict):
	(jobname,src,dst,baselinestatus,baselinetime,baselinesentshort,syncstatus,syncsched,synctime,syncsentshort,synccounter,verifystatus,verifystarttime,verifyratio,verifycounter) = details 
	jsongeneraldict.append( {
		'jobname': jobname,
		'src': src,
		'dst': dst,
		'baselinestatus':baselinestatus,
		'baselinetime':baselinetime,
		'baselinesentshort':baselinesentshort,
		'syncstatus':syncstatus,
		'syncsched':syncsched,
		'synctime':synctime,
		'syncsentshort':syncsentshort,
		'synccounter':synccounter,
		'verifystatus':verifystatus,
		'verifystarttime':verifystarttime,
		'verifyratio':verifyratio,
		'verifycounter':verifycounter
		})
	return jsongeneraldict

#create status json 
def addtostatusjson(jobname,src,details,jsondict):

	if not jobname in jsondict: jsondict[jobname] = {}
	if not src in jsondict[jobname]: 
		jsondict[jobname][src] = {}
		jsondict[jobname][src] = jobsdict[jobname][src]
	if not 'phases' in jsondict[jobname][src]: jsondict[jobname][src]['phases'] = []

	if len(details) > 0:
		(task,starttime,endtime,duration,scanned,reviewed,copied,modified,deleted,errors,sent,nodename,status,stdoutlogpath,stderrlogpath,stdoutlogexists,stderrlogexists,stdoutlogcontent,stderrlogcontent) = details

		jsondict[jobname][src]['phases'].append( {
												"phase": task,
												"starttime": starttime,
												"endtime": endtime,
												"duration": duration,
												"scanned": scanned,
												"reviewed": reviewed,
												"copied": copied,
												"modified": modified,
												"deleted": deleted,
												"errors": errors,
												"sent": sent,
												"nodename": nodename,
												"stdoutlogpath": stdoutlogpath,
												"stderrlogpath": stderrlogpath,
												"stdoutlogexists": stdoutlogexists,
												"stderrlogexists": stderrlogexists,
												"stdoutlogcontent": stdoutlogcontent,
												"stderrlogcontent": stderrlogcontent,												
												"status": status}
		)

	return jsondict

#create vcsv status 
def create_csv_status (jsondict):
	try: 
		writer = csv.writer(sys.stdout,delimiter="\t")
		writer.writerow(["#JOB NAME","SOURCE PATH","DEST PATH","SYNC SCHED","CPU MHz","RAM MB","TOOL","EXCLUDE DIRS","PHASE",'Start Time','End Time','Duration','Scanned','Reviewed','Copied','Modified','Deleted','Errors','Data Sent','Node','Status',"Std Err Path","Std Out Path"])

		for job in jsondict:
			for src in jsondict[job]:		
				jobdetails = copy.deepcopy(jsondict[job][src])
				for phase in jobdetails['phases']:
					writer.writerow([job,src,jobdetails['dst'],jobdetails['cron'],jobdetails['cpu'],jobdetails['memory'],jobdetails['tool'],jobdetails['excludedirfile'],
						phase['phase'],phase['starttime'],phase['endtime'],phase['duration'],phase['scanned'],phase['reviewed'],phase['copied'],phase['modified'],
						phase['deleted'],phase['errors'],phase['sent'],phase['nodename'],phase['status'],phase['stderrlogpath'],phase['stdoutlogpath']])
	except Exception as e:
		logging.error("error creating csv file:"+csvfile)
		exit(1)


#create general status
def create_general_status (jsongeneraldict):
	
	if len(jsongeneraldict) == 0:
		print("no data found")
		return

	#build the table object
	table = PrettyTable()
	table.field_names = ["Job","Source Path","Dest Path","BL Status","BL Time","BL Sent","SY Status","Next SY","SY Time","SY Sent","SY#","VR Status","VR Start","VR Ratio","VR#"]
	rowcount = 0
	for job in 	jsongeneraldict:
		table.add_row([job['jobname'],job['src'],truncate_middle(job['dst'],30),job['baselinestatus'],job['baselinetime'],job['baselinesentshort'],
			job['syncstatus'],job['syncsched'],job['synctime'],job['syncsentshort'],job['synccounter'],job['verifystatus'],
			job['verifystarttime'],job['verifyratio'],job['verifycounter']])
	
	table.border = False
	table.align = 'l'
	print("\n BL=Baseline SY=Sync VR=Verify\n")
	print(table)
	

#create verbose status 
def create_verbose_status (jsondict, displaylogs=False):

	print('')

	for job in jsondict:
		for src in jsondict[job]:
			jobdetails = copy.deepcopy(jsondict[job][src])

			#print general information 
			print(("JOB: "+job))
			print(("SRC: "+src))
			print(("DST: "+jobdetails['dst']))
			
			if jobdetails['aclcopy'] == "nfs4-acl": print("ACL: NFS4 ACL COPY")
			if jobdetails['aclcopy'] == "no-win-acl": print("ACL: NO CIFS ACL COPY")
			
			nextrun = get_next_cron_time(jobdetails['cron'])
			if 'paused' in jobdetails:
				nextrun = 'paused'
			print(("SYNC CRON: "+jobdetails['cron']+" (NEXT RUN "+nextrun+")"))

			print(("RESOURCES: " + str(jobdetails['cpu'])+"MHz CPU "+str(jobdetails['memory'])+'MB RAM'))

			if jobdetails['ostype'] =='linux' and jobdetails['tool'] != 'cloudsync': print(("XCP INDEX NAME: "+jobdetails['xcpindexname']))
			if jobdetails['excludedirfile'] != '': print(("EXCLUDE DIRS FILE: "+jobdetails['excludedirfile']))
			if jobdetails['tool'] != 'cloudsync': print(("OS: "+jobdetails['ostype'].upper()))
			if jobdetails['ostype']=='windows' or jobdetails['tool']=='cloudsync': print(("TOOL NAME: "+jobdetails['tool']))
			print("")

			if len(jobdetails['phases']) > 0:
				begining = True 
				for phase in jobdetails['phases']:
					if begining or displaylogs:
						verbosetable = PrettyTable()
						verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Reviewed','Copied','Modified','Deleted','Errors','Data Sent','Node','Status']
						begining = False

					verbosetable.add_row([phase['phase'],phase['starttime'],phase['endtime'],phase['duration'],phase['scanned'],phase['reviewed'],phase['copied'],phase['modified'],phase['deleted'],phase['errors'],phase['sent'],phase['nodename'],phase['status']])

					if displaylogs:
						verbosetable.border = False
						verbosetable.align = 'l'
						print((verbosetable.get_string(sortby="Start Time")))
						print("")

						for logtype in ['stdout','stderr']:
							print(("Log type:"+logtype))
							if phase[logtype+'logexists']:
								print((phase[logtype+'logcontent']))
								print(("the last "+str(maxloglinestodisplay)+" lines are displayed"))
								print(("full log file path: " +phase[logtype+'logpath']))
							else:
								print(("log:"+logtype+" is not available"))
								print("")
						
						print("")
			else:
				print(" no data found")
				print("")

			if not displaylogs and len(jobdetails['phases']) > 0:
				verbosetable.border = False
				verbosetable.align = 'l'
				print((verbosetable.get_string(sortby="Start Time")))
				print("")


#create general status
def create_status (reporttype,displaylogs=False, output='text'):

	#text output if output not provided 
	if not output: output = 'text'

	#get nomad allocations 
	jobs = {}
	allocs = {}
	nodes = {}

	#used to create json outpput 
	jsondict = {}
	jsongeneraldict = []

	#if display logs then print verbose 
	if displaylogs==True: reporttype = 'verbose' 	

	#if output is json or html report type is verbose 
	if output in ['json','csv']: reporttype = 'verbose' 

	try:
		jobs  = n.jobs.get_jobs()
	except Exception as e:
		logging.error('cannot get nomad job list')
		exit(1)
	try:
		allocs = n.allocations.get_allocations()
	except Exception as e:
		logging.error('cannot get alloc list')
		exit(1)
	try:
		nodes = n.nodes.get_nodes()
	except Exception as e:
		logging.error('cannot get node list')
		exit(1)

	nodename = '-'
	
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

					displayheader = True
					
					dst	          = jobdetails['dst']
					srcbase       = jobdetails['srcbase']
					dstbase       = jobdetails['dstbase']
					xcpindexname  = jobdetails['xcpindexname']	

					baseline_job_name = jobdetails['baseline_job_name']
					sync_job_name     = jobdetails['sync_job_name']
					verify_job_name   = jobdetails['verify_job_name']
					jobcron           = jobdetails['cron']
					ostype            = jobdetails['ostype']
					tool              = jobdetails['tool']
					excludedirfile    = jobdetails['excludedirfile']
					aclcopy           = jobdetails['aclcopy']
					
					#xcp logs for linux are in stderr for windows they are in stdout 
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
									if int(allocdata['CreateTime']) > allocperiodiccounter:
										allocperiodiccounter = allocdata['CreateTime'] 
										baselinestatus = allocdata['ClientStatus']
										baselinefound  = True
										baselinealloc = allocdata
							if file.startswith(logtype+"log_"):
								baselinelogcachefile = os.path.join(baselinecachedir,file)
								logging.debug('loading cached info log file:'+baselinelogcachefile) 
								baselinestatsresults = parse_stats_from_log('file',baselinelogcachefile,logtype)
								if 'time' in list(baselinestatsresults.keys()): 
									baselinetime = baselinestatsresults['time']
								if 'bwout' in list(baselinestatsresults.keys()): 
									baselinesent = baselinestatsresults['bwout']
								if 'failure' in list(baselinestatsresults.keys()):
									baselinestatus = 'failed'

							if file.startswith("warning."):
								baselinestatus = baselinestatus + '(warning)'
							if file.startswith("error."):
								baselinestatus = 'failed'

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
									if jobdata['Stop']: 
										syncsched = 'paused'
										jobsdict[jobname][src]['paused'] = True 

									if 'job' not in syncjobsstructure:
										syncjobsstructure['job'] = {}
									syncjobsstructure['job'] = jobdata

							if file.startswith("periodic-"):
								synccachefile = os.path.join(synccachedir,file)
								try:
									with open(synccachefile) as f:
										logging.debug('loading cached info periodic file:'+synccachefile)
										jobdata = json.load(f)
									
										if int(file.split('-')[1]) > int(syncperiodiccounter):										
											syncstatus = jobdata['Status']
											joblastdetails = jobdata
											syncperiodiccounter = file.split('-')[1]
										if 'periodics' not in syncjobsstructure:
											syncjobsstructure['periodics'] = {}
										syncjobsstructure['periodics'][jobdata['ID']] = {}											
										syncjobsstructure['periodics'][jobdata['ID']] = jobdata
										synccounter+=1
								except Exception as e:
									logging.debug("file:"+synccachefile+" no longer exists")

							if file.startswith("alloc_"):
								syncalloccachefile = os.path.join(synccachedir,file)
								try:
									with open(syncalloccachefile) as f:
										logging.debug('loading cached info alloc file:'+syncalloccachefile)
										allocdata = json.load(f)
										if int(allocdata['CreateTime']) > allocperiodiccounter:
											allocperiodiccounter = allocdata['CreateTime'] 
											alloclastdetails = allocdata
										if 'allocs' not in syncjobsstructure:
											syncjobsstructure['allocs'] = {}										
										syncjobsstructure['allocs'][allocdata['ID']] = {}
										syncjobsstructure['allocs'][allocdata['ID']] = allocdata
								except Exception as e:
									logging.debug("file:"+syncalloccachefile+" no longer exists")

						for file in os.listdir(synccachedir):
							if file.startswith(logtype+"log_"):
								synclogcachefile = os.path.join(synccachedir,file)
								logallocid = file.replace(logtype+'log_','').replace('.log','')
								if 'allocs' not in syncjobsstructure:
									syncjobsstructure['allocs'] = {}
								if logallocid in syncjobsstructure['allocs']:
									logging.debug('loading cached info log file:'+synclogcachefile)
									statsresults = parse_stats_from_log('file',synclogcachefile,logtype)							
									if 'logs' not in syncjobsstructure: syncjobsstructure['logs'] = {}
									syncjobsstructure['logs'][logallocid] = {}										
									syncjobsstructure['logs'][logallocid] = statsresults

					if not syncjobfound: syncsched = '-'
			
					if alloclastdetails: 
						logging.debug("sync job name:"+sync_job_name+" lastjobid:"+joblastdetails['ID']+' allocjobid:'+alloclastdetails['ID'])

						synclogcachefile = os.path.join(synccachedir,logtype+'log_'+alloclastdetails['ID']+'.log')
						statsresults = parse_stats_from_log('file',synclogcachefile,logtype)
						if 'time' in list(statsresults.keys()): synctime = statsresults['time']
						if 'bwout' in list(statsresults.keys()): syncsent = statsresults['bwout']
						if 'lastline' in list(statsresults.keys()): synclastline = statsresults['lastline']
						if 'failure' in list(statsresults.keys()): syncstatus = 'failed'

						syncstatus =  alloclastdetails['ClientStatus']
						if joblastdetails['Status'] in ['pending','running']: syncstatus =  joblastdetails['Status']
						if syncstatus == 'complete': syncstatus = 'idle'

						#check to see if the log file includes warnings
						if os.path.isfile(os.path.join(synccachedir,'warning.'+alloclastdetails['JobID'].split('/')[1])):
							syncstatus = syncstatus+ '(warning)'
						#check to see if the log file includes nfs error
						if os.path.isfile(os.path.join(synccachedir,'error.'+alloclastdetails['JobID'].split('/')[1])):
							syncstatus = 'failed'						

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
									if 'job' not in verifyjobsstructure:
										verifyjobsstructure['job'] = {}
									verifyjobsstructure['job'] = jobdata

							if file.startswith("periodic-"):
								verifycachefile = os.path.join(verifycachedir,file)
								with open(verifycachefile) as f:
									logging.debug('loading cached info periodic file:'+verifycachefile)
									jobdata = json.load(f)
									if int(file.split('-')[1]) > int(verifyperiodiccounter):
										verifystatus = jobdata['Status']
										verifyjoblastdetails = jobdata
										verifyperiodiccounter = file.split('-')[1]
									if 'periodics' not in verifyjobsstructure:
										verifyjobsstructure['periodics'] = {}
									verifyjobsstructure['periodics'][jobdata['ID']] = {}											
									verifyjobsstructure['periodics'][jobdata['ID']] = jobdata
									verifycounter+=1

							if file.startswith("alloc_"):
								verifyalloccachefile = os.path.join(verifycachedir,file)
								with open(verifyalloccachefile) as f:
									logging.debug('loading cached info alloc file:'+verifyalloccachefile)
									allocdata = json.load(f)
									if int(allocdata['CreateTime']) > verifyallocperiodiccounter:
										verifyallocperiodiccounter = allocdata['CreateTime'] 
										verifyalloclastdetails = allocdata
									if 'allocs' not in verifyjobsstructure:
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
								if 'time' in list(verifystatsresults.keys()): 
									verifytime = verifystatsresults['time']
								if 'bwout' in list(verifystatsresults.keys()): 
									verifysent = verifystatsresults['bwout']
								if 'found' in list(verifystatsresults.keys()): 
									verifyratio = verifystatsresults['found']+'/'+verifystatsresults['scanned']	
								if 'logs' not in verifyjobsstructure:
									verifyjobsstructure['logs'] = {}
								verifyjobsstructure['logs'][logallocid] = {}										
								verifyjobsstructure['logs'][logallocid] = verifystatsresults



					if not verifyjobfound: verifysched = '-'
			
					if verifyalloclastdetails: 
						logging.debug("verify job name:"+verify_job_name+" lastjobid:"+verifyjoblastdetails['ID']+' allocjobid:'+verifyalloclastdetails['ID'])

						verifylogcachefile = os.path.join(verifycachedir,'stdoutlog_'+verifyalloclastdetails['ID']+'.log')
						verifystatsresults = parse_stats_from_log('file',verifylogcachefile,logtype)
						if 'time' in list(verifystatsresults.keys()): verifytime = verifystatsresults['time']
						if 'lastline' in list(verifystatsresults.keys()): verifylastline = verifystatsresults['lastline']
						if 'found' in list(verifystatsresults.keys()): verifyratio = verifystatsresults['found']+'/'+verifystatsresults['scanned']						
						if 'failure' in list(verifystatsresults.keys()): verifystatus = 'failed'
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
							if verifystatus != 'running' and ostype == 'windows' and (verifystatsresults['found'] != verifystatsresults['scanned']): verifystatus =  'diff'
							
							if verifystatus == 'idle' and (verifystatsresults['found'] == verifystatsresults['scanned']): verifystatus =  'equal'
						except Exception as e:
							logging.debug("verify log details:"+verifylogcachefile+" are not complete")

						try:
							verifystarttime = verifyalloclastdetails['TaskStates']['verify']['StartedAt']
							verifystarttime = verifystarttime.split('T')[0]+' '+verifystarttime.split('T')[1].split('.')[0]
						except Exception as e:
							verifystarttime = '-'
						
						#check to see if the log file includes warnings
						if os.path.isfile(os.path.join(verifycachedir,'warning.'+verifyalloclastdetails['JobID'].split('/')[1])):
							verifystatus = verifystatus+ '(warning)'							 
						#check to see if the log file includes nfs error
						#if os.path.isfile(os.path.join(verifycachedir,'error.'+verifyalloclastdetails['JobID'].split('/')[1])):
						#	verifystatus = 'failed'	

					baselinesentshort = re.sub("\(.+\)","",baselinesent)
					syncsentshort = re.sub("\(.+\)","",syncsent)

					#work on error filter 
					addrow = True
					try:
						if args.jobstatus and not baselinestatus.startswith(args.jobstatus) and not syncstatus.startswith(args.jobstatus) and not verifystatus.startswith(args.jobstatus):
							addrow = False 
					except Exception as e:
						logging.debug("filter was not passed")
				

					if addrow:		
						jsongeneraldict = addtogeneralstatusjson([jobname,src,dst,baselinestatus,baselinetime,baselinesentshort,syncstatus,syncsched,synctime,syncsentshort,synccounter,verifystatus,verifystarttime,verifyratio,verifycounter],jsongeneraldict)
						jsondict = addtostatusjson(jobname,src,[],jsondict)
						rowcount += 1


					#printing verbose information
					if reporttype == 'verbose':
						#keep pending status since pending don't have alloc and we need to reflect in status 
						baselinestatus1=''
						if baselinestatus == 'pending': baselinestatus1 = 'pending'
						#for baseline 
						if (baselinejob and baselinealloc) or baselinestatus == 'pending':
							task = 'baseline'
							try:
								starttime = baselinealloc['TaskStates']['baseline']['StartedAt']
								starttime = starttime.split('T')[0]+' '+starttime.split('T')[1].split('.')[0]
							except Exception as e:
								starttime = '-'

							try:
								endtime = baselinealloc['TaskStates']['baseline']['FinishedAt']
								endtime = endtime.split('T')[0]+' '+endtime.split('T')[1].split('.')[0]
							except Exception as e:
								endtime = '-'

							try:
								duration = baselinestatsresults['time']
							except Exception as e:
								duration = '-'

							try:
								scanned = baselinestatsresults['scanned']
							except Exception as e:
								scanned = '-'

							try:
								reviewed = baselinestatsresults['reviewed']
							except Exception as e:
								reviewed = '-'
 				
							try:
								copied = baselinestatsresults['copied']
							except Exception as e:
								copied = '-'

							try:
								deleted = baselinestatsresults['gone']
							except Exception as e:
								deleted = '-'

							try:
								modified = baselinestatsresults['modification']
							except Exception as e:
								modified = '-'						 										 				

							try:
								errors = baselinestatsresults['errors']
							except Exception as e:
								errors = '-'

							verifyratio = '-'

							try:
								sent = baselinestatsresults['bwout']
							except Exception as e:
								sent = '-'

							try:
								nodeid = baselinealloc['NodeID']
								if nodeid:
									for node in nodes:
										if node['ID'] == nodeid: nodename = node['Name']
							except Exception as e:
								nodeid = ''
							
							#cloud sync broker name
							if 'broker' in baselinestatsresults: nodename = baselinestatsresults['broker']						

							try:
								baselinestatus =  baselinealloc['ClientStatus']
								if baselinejob['Status'] in ['pending','running']: baselinestatus =  baselinejob['Status']
								if baselinejob['Status'] == 'dead' and baselinejob['Stop']: baselinestatus = 'aborted'

								if 'failure' in baselinestatsresults: baselinestatus = 'failed'

								#check to see if the log file includes warnings
								if os.path.isfile(os.path.join(baselinecachedir,'warning.'+baselinealloc['JobID'].split('/')[1])):
									baselinestatus = baselinestatus+ '(warning)'								
								
								#check to see if the log file includes nfs3 error
								#if os.path.isfile(os.path.join(baselinecachedir,'error.'+baselinealloc['JobID'].split('/')[1])):
								#	baselinestatus = 'failed'

							except Exception as e:
								baselinestatus = '-'
							
							#restore pending status when alloc not yet created 
							if baselinestatus1 == 'pending': baselinestatus = 'pending'

							if baselinestatus == 'running': endtime = '-' 

							try:
								#filter out results based on scope 
								#if phasefilter and not task.startswith(phasefilter):
								if phasefilter and not task==phasefilter:
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
							except Exception as e:
								logging.debug("filter was not passed")

							if addrow:								
				 				stdoutkey = 'content'; stderrkey = 'contentotherlog'
				 				if logtype == 'stderr': 
				 					stdoutkey = 'contentotherlog'
				 					stderrkey = 'content'

				 				#prevent excption if current log is not avaialble yet
				 				if not 'stdoutlogpath' in baselinestatsresults: baselinestatsresults['stdoutlogpath'] = ''
				 				if not 'stderrlogpath' in baselinestatsresults: baselinestatsresults['stderrlogpath'] = ''
			 					if not 'stdoutlogexists' in baselinestatsresults: baselinestatsresults['stdoutlogexists'] = ''
			 					if not 'stderrlogexists' in baselinestatsresults: baselinestatsresults['stderrlogexists'] = ''
			 					if not stdoutkey in baselinestatsresults: baselinestatsresults[stdoutkey] = ''
			 					if not stderrkey in baselinestatsresults: baselinestatsresults[stderrkey] = ''

				 				jsondict = addtostatusjson(jobname,src,[task,starttime,endtime,duration,scanned,reviewed,copied,modified,deleted,errors,sent,nodename,baselinestatus,
				 												baselinestatsresults['stdoutlogpath'],baselinestatsresults['stderrlogpath'],
				 												baselinestatsresults['stdoutlogexists'],baselinestatsresults['stderrlogexists'],
				 												baselinestatsresults[stdoutkey],baselinestatsresults[stderrkey]],jsondict)



						#get the last sync number will be used for lastsync filter 
						lastsync = len(syncjobsstructure['periodics'])

						#merge sync and verify data 
						jobstructure=syncjobsstructure.copy()
						if 'periodics' in list(verifyjobsstructure.keys()):
							if not 'periodics' in list(jobstructure.keys()):
								jobstructure['periodics']={}
							jobstructure['periodics'].update(verifyjobsstructure['periodics'])
						if 'allocs' in list(verifyjobsstructure.keys()):
							if not 'allocs' in list(jobstructure.keys()):
								jobstructure['allocs']={}							
							jobstructure['allocs'].update(verifyjobsstructure['allocs'])
						if 'logs' in list(verifyjobsstructure.keys()):
							if not 'logs' in list(jobstructure.keys()):
								jobstructure['logs']={}								
							jobstructure['logs'].update(verifyjobsstructure['logs'])

						#for each periodic 					 	
						synccounter = 1
						verifycounter = 1
						if 'periodics' in list(jobstructure.keys()):
							for periodic in sorted(jobstructure['periodics'].keys()):
								jobstatus = '-'
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

								jobstatus = currentperiodic['Status']
								
								starttime = 'future'
								endtime = '-'
								duration = '-'
								reviewed = '-'
								scanned = '-'
								copied = '-'
								deleted = '-'
								modified = '-'
								errors = '-'
								sent = '-'
								nodename = '-'								
								currentlog = {}

								for allocid in jobstructure['allocs']:
									if jobstructure['allocs'][allocid]['JobID'] == periodic:
										currentalloc = jobstructure['allocs'][allocid]
										currentlog = {}
										
										if allocid in list(jobstructure['logs'].keys()):
											currentlog = jobstructure['logs'][allocid]

										if tasktype == 'verify' and 'content' in currentlog:
											st = dst+' '+src
											
											if re.search(st.encode('unicode_escape').decode("utf-8"),currentlog['content']):
												task = 'verify'+str(verifycounter-1)+'(reverse)'

										try:
											starttime = currentalloc['TaskStates'][tasktype]['StartedAt']
											starttime = starttime.split('T')[0]+' '+starttime.split('T')[1].split('.')[0]
										except Exception as e:
											starttime = '-'

										try:
											endtime = currentalloc['TaskStates'][tasktype]['FinishedAt']
											endtime = endtime.split('T')[0]+' '+endtime.split('T')[1].split('.')[0]
										except Exception as e:
											endtime = '-'

										try:
											duration = currentlog['time']
										except Exception as e:
											duration = '-'

										try:
											reviewed = currentlog['reviewed']
										except Exception as e:
											reviewed = '-'
							 				
										try:
											scanned = currentlog['scanned']
											if tasktype == 'verify': scanned = currentlog['found']+'/'+currentlog['scanned']
										except Exception as e:
											scanned = '-'

										try:
											copied = currentlog['copied']
										except Exception as e:
											copied = '-'

										try:
											deleted = currentlog['gone']
										except Exception as e:
											deleted = '-'

										try:
											modified = currentlog['modification']
										except Exception as e:
											modified = '-'						 										 				

										try:
											errors = currentlog['errors']
											if tasktype == 'verify':
												try:
													diffattr = currentlog['diffattr']
												except Exception as e:
													diffattr = '0'								 					

												try:
													diffmodtime = currentlog['diffmodtime']
												except Exception as e:
													diffmodtime = '0'

												errors = errors+' (attr:'+diffattr+' time:'+diffmodtime+')'
										except Exception as e:
											errors = '-'	

										try:
											sent = currentlog['bwout']
										except Exception as e:
											sent = '-'

										try:
											nodeid = currentalloc['NodeID']
											if nodeid:
												for node in nodes:
													if node['ID'] == nodeid: nodename = node['Name']
										except Exception as e:
											nodeid = ''
										#cloud sync broker name
										if 'broker' in currentlog: nodename = currentlog['broker']	

										try:
											jobstatus =  currentalloc['ClientStatus']
											if currentperiodic['Status'] in ['pending','running']: jobstatus =  currentperiodic['Status']

											if tasktype == 'verify' and jobstatus != 'running':
												if jobstatus == 'failed' and (currentlog['found'] != currentlog['scanned']): jobstatus =  'diff'
												if jobstatus == 'failed' and (currentlog['found'] == currentlog['scanned']): jobstatus =  'equal'
												if jobstatus == 'complete': jobstatus = 'idle'
												#windows
												if ostype == 'windows' and (currentlog['found'] != currentlog['scanned']): jobstatus =  'diff'
												if jobstatus == 'idle' and (currentlog['found'] == currentlog['scanned']): jobstatus =  'equal'
											
											if tasktype == 'sync':
												#check to see if the log file includes warnings
												currentjobcachedir = os.path.dirname(currentlog['logfilepath'])
												if os.path.isfile(os.path.join(currentjobcachedir,'warning.'+currentalloc['JobID'].split('/')[1])):
													jobstatus = jobstatus+ '(warning)'													
												
												#check to see if the log file includes nfsv3 error
												if os.path.isfile(os.path.join(currentjobcachedir,'error.'+currentalloc['JobID'].split('/')[1])):
													jobstatus = 'failed'	

										except Exception as e:
											jobstatus = '-'

										try:
											#job failed but did not exit with error 
											if 'failure' in list(currentlog.keys()): jobstatus = 'failed'
										except Exception as e:
											pp.pprint(currentlog)											
										

								#handle aborted jobs 
								if currentperiodic['Status'] == 'dead' and currentperiodic['Stop']: jobstatus = 'aborted'											

								#validate aborted time 
								if jobstatus == 'running': endtime = '-' 
								
								#filter results
								addrow = True 
								try:
									#if phasefilter and not task.startswith(phasefilter) and phasefilter != 'lastsync':
									if phasefilter and not task == phasefilter and phasefilter != 'lastsync':
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
								except Exception as e:
									logging.debug("filter was not passed")
													
								if addrow:

					 				stdoutkey = 'content'; stderrkey = 'contentotherlog'
					 				if logtype == 'stderr': 
					 					stdoutkey = 'contentotherlog'
					 					stderrkey = 'content'

					 				#prevent excption if current log is not avaialble yet
					 				if not 'stdoutlogpath' in currentlog: currentlog['stdoutlogpath'] = ''
					 				if not 'stderrlogpath' in currentlog: currentlog['stderrlogpath'] = ''
				 					if not 'stdoutlogexists' in currentlog: currentlog['stdoutlogexists'] = ''
				 					if not 'stderrlogexists' in currentlog: currentlog['stderrlogexists'] = ''
				 					if not stdoutkey in currentlog: currentlog[stdoutkey] = ''
				 					if not stderrkey in currentlog: currentlog[stderrkey] = ''


			 						jsondict = addtostatusjson(jobname,src,
			 													[task,starttime,endtime,duration,scanned,reviewed,copied,modified,deleted,errors,sent,nodename,jobstatus,
			 													 currentlog['stdoutlogpath'],currentlog['stderrlogpath'],
				 												 currentlog['stdoutlogexists'],currentlog['stderrlogexists'],
				 												 currentlog[stdoutkey],currentlog[stderrkey]],
				 												jsondict)			 						

			 						task = ''
			 						starttime='-'
			 						endtime='-'
			 						duration='-'
			 						scanned='-'
			 						reviewed='-'
			 						copied='-'
			 						modified='-'
			 						deleted='-'
			 						errors='-'
			 						sent='-'
			 						nodename='-'
			 						jobstatus='-'

	if reporttype == 'verbose':
		if output == 'text':
			if len(list(jsondict.keys())) > 0:
				create_verbose_status(jsondict,displaylogs)
			else:
				print("no data found")				

		elif output == 'json':
			print((json.dumps(jsondict)))
		elif output == 'csv':
			create_csv_status(jsondict)

	#dispaly general report
	if reporttype == 'general':
		if output == 'text':
			create_general_status(jsongeneraldict)

	return jsondict,jsongeneraldict

	
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
				exit(1)
					
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

					except Exception as e:
						job = ''
					
					if not job:
						logging.warning("sync job does not exists for src:"+src+". please use sync command to recreate it") 
					
					else:
						baselinestatus = check_baseline_job_status(baselinejobname)
						
						syncjobdetails = {}
						try:
							syncjobdetails = n.job.get_job(nomadjobname)
						except Exception as e:
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
							logging.warning("cannot resume job:"+nomadjobname+" status changed to:"+action+" since baseline is not complete") 
						elif action in ['pause','resume'] and currentstopstatus != action:
							nomadjobdict["Job"]["Stop"] = newstate

							logging.info("src:"+src+" dst:"+dst+" status changed to:"+action) 
							nomadout = n.job.register_job(nomadjobname, nomadjobdict)	
							try:
								job = n.job.get_job(nomadjobname)
							except Exception as e:
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
								except Exception as e:
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
										except Exception as e:
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
										except Exception as e:
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
        choice = input().lower()
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
						except Exception as e:
							logging.debug('could not delete temp alloc directory'+allocationlogs)
							exit(1)

			logging.debug("delete job:"+nomadjob['ID'])
			response = requests.delete(nomadapiurl+'job/'+nomadjob['ID']+'?purge=true')				
			if not response.ok:
				logging.error("can't delete job:"+nomadjob['ID']) 
				exit(1)
			#ruuning gabage collection to kill deleted job
			response = requests.put(nomadapiurl+'system/gc')
			if not response.ok:
				logging.debug("can't run gc") 
				exit(1)
#delete jobs 
def delete_jobs(forceparam):

	jobsdictcopy = copy.deepcopy(jobsdict)
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.warning("job config directory:" + jobdir + " not exists") 
			
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					
					dst	          = jobdetails['dst']
					srcbase       = jobdetails['srcbase']
					dstbase       = jobdetails['dstbase']
					syncnomadjobname  = jobdetails['sync_job_name']
					baselinejobname  = jobdetails['baseline_job_name']
					verifyjobname    = jobdetails['verify_job_name']
					excludedirfile	 = jobdetails['excludedirfile']
					tool			 = jobdetails['tool']

					force = forceparam
					if not force: 
						if tool != 'cloudsync':
							force = query_yes_no("delete job for source:"+src,'no')
						else:
							force = query_yes_no("delete xcption and cloudsync job for src:"+src+' dst:'+dst+' ?','no')
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
							except Exception as e:
								logging.error("could not delete xcp repo from:"+indexpath) 

						baselinecachedir = os.path.join(cachedir,'job_'+baselinejobname)
						if os.path.exists(baselinecachedir):
							logging.debug("delete baseline cache dir:"+baselinecachedir)
							try:
								rmout = shutil.rmtree(baselinecachedir) 
							except Exception as e:
								logging.error("could not delete baseline cache dir:"+baselinecachedir)

						synccachedir = os.path.join(cachedir,'job_'+syncnomadjobname)
						if os.path.exists(synccachedir):
							logging.debug("delete sync cache dir:"+synccachedir)
							try:
								rmout = shutil.rmtree(synccachedir) 
							except Exception as e:
								logging.error("could not delete sync cache dir:"+synccachedir)

						verifycachedir = os.path.join(cachedir,'job_'+verifyjobname)
						if os.path.exists(verifycachedir):
							logging.debug("delete verify cache dir:"+verifyjobname)
							try:
								rmout = shutil.rmtree(verifycachedir)
							except Exception as e:
								logging.error("could not delete verify cache dir:"+verifycachedir)
						if tool == 'cloudsync':
							cloudsync_cmd = [cloudsyncscript,'delete','-s',src,'-d',dst,'--force']
							try:
								deleterel = subprocess.check_output(cloudsync_cmd,stderr=subprocess.STDOUT)
							except Exception as e:
								os.system(' '.join(cloudsync_cmd))
								logging.warning("cannot delete source/destination paths for cloudsync src:"+src+" dst:"+dst)	
							
						# if excludedirfile != '':
						# 	excludedirfilepath = os.path.join(excludedir,excludedirfile)
						# 	logging.debug("delete exclude file:"+excludedirfilepath)
						# 	if os.remove(excludedirfilepath):
						# 		logging.error("could not delete exludedir file:"+excludedirfilepath)

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
						except Exception as e:
							logging.error("cannot write job json file:"+jobdictjson)
							exit(1)						

#check if nomad is available + run the xcption_gc_system job if not available 
def nomadstatus():
	logging.debug("getting list of nomad nodes")
	response = requests.get(nomadapiurl+'nodes')	
	if not response.ok:
		logging.error("could not contact nomad cluster, please make sure this node is part of the cluster")
		exit(1)
	else:
		#build the table object
		table = PrettyTable()
		table.field_names = ["Name","IP","Status","OS","Reserved/Total CPU MHz","Used CPU %","Reserved/Total RAM MB","Used RAM %","# Running Tasks"]		
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
		print("")
		print(table)			

#check if nomad is available + run the xcption_gc_system job if not available 
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
			if response.content.decode('utf-8') == "job not found":
				logging.debug("xcption_gc_system job is not running, starting it now")

				#loading job ginga2 templates 
				templates_dir = ginga2templatedir
				env = Environment(loader=FileSystemLoader(templates_dir) )

				try:
					gc_template = env.get_template('xcption_gc_system.txt')
				except Exception as e:
					logging.error("could not find template file: " + os.path.join(templates_dir,'xcption_gc_system.txt'))
					exit(1)
				
				#creating the jobs directory
				xcptiongcsystemhcldir = jobsdir
				if not os.path.isdir(xcptiongcsystemhcldir):
					try:
						os.mkdir(xcptiongcsystemhcldir)
					except Exception as e:
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
def parse_nomad_jobs_to_files (parselog=True):
	#get nomad allocations 
	jobs = {}
	allocs = {}
	nodes = {}
	
	try:
		jobs  = n.jobs.get_jobs()
	except Exception as e:
		logging.error('cannot get nomad job list')
		exit(1)
	try:
		allocs = n.allocations.get_allocations()
	except Exception as e:
		logging.error('cannot get alloc list')
		exit(1)
	try:
		nodes = n.nodes.get_nodes()
	except Exception as e:
		logging.error('cannot get node list')
		exit(1)

	nomadserver = ''
	try:
		response = requests.get(nomadapiurl+'agent/members')
		if response.ok:
			agentinfo = json.loads(response.content)
			nomadserver = agentinfo["ServerName"]
	except Exception as e:
		logging.error("could not get nomad server name")
		exit(1)
	try:
		hostname = socket.gethostname()
	except Exception as e:
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
	except Exception as e:
		logging.debug("cannot create lock file:"+lockfile)

	for job in jobs:
		if not (job['ID'].startswith('baseline') or job['ID'].startswith('sync') or job['ID'].startswith('verify') or job['ID'].startswith('smartassess') or job['ID'].startswith('xcpdelete')):
			continue

		jobdir = os.path.join(cachedir,'job_'+job['ID'])	

		if len(job['ID'].split('/')) == 1:
			if not os.path.isdir(jobdir):
				logging.debug("creating dir:"+jobdir)
				try:
					logging.debug("creating directory:"+jobdir)
					os.mkdir(jobdir)
				except Exception as e:
					logging.error("cannot create dir:"+jobdir)
					exit(1)
		else:
			#because the sub jobs contains the job name
			jobdir = os.path.join(cachedir,'job_'+job['ID'].split('/')[0])

		jobjsonfile = os.path.join(jobdir,'job_'+job['ID']+'.json')		
		cachecompletefile = os.path.join(jobdir,'complete.job_'+job['ID']+'.json')
		cachewarningfile = os.path.join(jobdir,'warning.job_'+job['ID']+'.json')
		cacheerrorfile = os.path.join(jobdir,'error.job_'+job['ID']+'.json')
		if len(job['ID'].split('/')) > 1:
			jobjsonfile = os.path.join(jobdir,job['ID'].split('/')[1])
			cachecompletefile = os.path.join(jobdir,'complete.'+job['ID'].split('/')[1])
			cachewarningfile = os.path.join(jobdir,'warning.'+job['ID'].split('/')[1])
			cacheerrorfile = os.path.join(jobdir,'error.'+job['ID'].split('/')[1])
	
		#validating if final update from job already exists in cache 
		jobcomplete = False 
		try:
			if job['JobSummary']['Summary'][job['ID'].split('/')[0]]['Complete'] == 1 or job['JobSummary']['Summary'][job['ID'].split('/')[0]]['Failed'] == 1:
				jobcomplete = True	
		except Exception as e:
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
		except Exception as e:
			logging.error("cannot create file:"+jobjsonfile)
			#exit(1)

		logging.debug("caching job:"+job['ID'])

		for alloc in allocs:		
			if alloc['JobID'] == job['ID']:
				allocjsonfile = os.path.join(jobdir,'alloc_'+alloc['ID']+'.json')				
				try:
					with open(allocjsonfile, 'w') as fp:
					    json.dump(alloc, fp)
					    logging.debug("dumping alloc to json file:"+allocjsonfile)		
				except Exception as e:
					logging.error("cannot create file:"+allocjsonfile)
					exit(1)

				task = 'sync'	
				if alloc['TaskGroup'].startswith('baseline'): task='baseline'
				if alloc['TaskGroup'].startswith('verify'): task='verify'
				if alloc['TaskGroup'].startswith('smartassess'): task='smartassess'
				if alloc['TaskGroup'].startswith('xcpdelete'): task='xcpdelete'

				# don't cache logs to make xcption status run faster (updated info will be delayed (max 10s) until next gc will run)
				if parselog:
					#get stderr and stdout logs
					for logtype in ['stderr','stdout']:
						#try to get the log file using api
						response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+'&type='+logtype+'&plain=true')
						if response.ok and re.search(rb"(\d|\S)", response.content, re.M|re.I):
							logging.debug("log for job:"+alloc['ID']+" is available using api")
							alloclogfile = os.path.join(jobdir,logtype+'log_'+alloc['ID']+'.log')
							try:
								#for smartassess and xcp delete jobs always pull a full file 
								if not os.path.isfile(alloclogfile) or job['ID'].startswith('smartassess') or job['ID'].startswith('xcpdelete'):
									with open(alloclogfile, 'w') as fp:
										logging.debug("dumping log to log file:"+alloclogfile)
										fp.write(response.content.decode('utf-8'))
										fp.close()
								else:
									#this is used to be able to add delta to the cache file to enable tail to work
									tmpalloclogfile = '/tmp/'+str(os.getpid())+alloclogfile.replace('/','_')
									with open(tmpalloclogfile, 'wb') as fp:
										logging.debug("dumping log to temp log file:"+tmpalloclogfile)
										fp.write(response.content)
										fp.close()								
									
									tmpalloclogfilenobin = tmpalloclogfile+".nobin"
									DEVNULL = open(os.devnull, 'wb')
									tr = "tr -cd '"+'\11\12\15\40-\176'+"' < "+tmpalloclogfile+" > "+tmpalloclogfilenobin

									logging.debug("running tr:"+tr)
									subprocess.call(tr,shell=True,stdout=DEVNULL,stderr=DEVNULL)

									logging.debug("comparing current cached file:"+alloclogfile+" with temp file:"+tmpalloclogfilenobin)
									apendtologfile = open(alloclogfile, 'a')
									DEVNULL = open(os.devnull, 'wb')
									#subprocess.call( ['comm','-13','--nocheck-order',alloclogfile,tmpalloclogfile],stdout=apendtologfile,stderr=DEVNULL)
									diff = "diff "+alloclogfile+" "+tmpalloclogfilenobin+" | grep '^>' | cut -c 3-"
									logging.debug("running diff:"+diff)
									subprocess.call(diff,shell=True,stdout=apendtologfile,stderr=DEVNULL)

									apendtologfile.close()
									os.remove(tmpalloclogfile)	
									os.remove(tmpalloclogfilenobin)	
									logging.debug("diff ended and new entries merged into the old cached log file")
							except Exception as e:
								print (e)
								logging.error("cannot create file:"+alloclogfile)
								exit(1)
				else:
					logging.debug("skpping log cache update for:"+job['ID'])
				
				#validating no error in the log that did not resulted with exit code 1
				if jobcomplete and not cachecomplete and parselog and not os.path.isfile(cachecompletefile):
					for logtype in ['stderr']:    #,'stdout']:
						logfile =  os.path.join(jobdir,logtype+'log_'+alloc['ID']+'.log')
						if os.path.isfile(logfile):
							logging.debug("looking for warnings in the log")
							with open(logfile) as f:
								content = f.readlines()
							content = [x.strip() for x in content] 
							for line in content:
								if re.search(" WARNING: ", line):
									logging.debug("warning found in the log, creating file:"+cachewarningfile)
									subprocess.call(['touch', cachewarningfile])
								if re.search(" nfs3 error", line):
									logging.debug("nfs3 error found in the log, creating file:"+cacheerrorfile)
									subprocess.call(['touch', cacheerrorfile])
									break

				logging.debug("caching alloc:"+alloc['ID'])

		# mark jobs as completed only as part of nomad subcommand and not status
		if jobcomplete and not cachecomplete and parselog:
			logging.debug("creating file:"+cachecompletefile+" to prevent further caching for the job")
			subprocess.call(['touch', cachecompletefile])


			
	#removing the lock file 
	try:
		logging.debug("removing lock file:"+lockfile)
		os.remove(lockfile)
	except Exception as e:
		logging.debug("cannot remove lock file:"+lockfile)


#walk throuth a dir upto certain depth in the directory tree 
def list_dirs_linux(startpath,depth):
	num_sep = startpath.count(os.path.sep)
	for root, dirs, files in os.walk(startpath):
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
	except Exception as e:
		logging.error("cannot delete temp mount point:"+dir)
		exit(1)

def nfs_unmount(mountpoint):
	DEVNULL = open(os.devnull, 'wb')
	if subprocess.call( [ 'umount', mountpoint ], stdout=DEVNULL, stderr=DEVNULL):
		return False
	return True

def nfs_mount(export, mountpoint):
	nfs_unmount(mountpoint)	
	logging.debug("validating export:"+export+"is mountable on:"+mountpoint)
	if not os.path.isdir(mountpoint):
		subprocess.call( [ 'mkdir', '-p',mountpoint ] )	

	if subprocess.call( [ 'mount', '-t', 'nfs', '-o','vers=3', export, mountpoint ],stderr=subprocess.STDOUT):
		logging.debug("cannot mount path:"+export)
		nfs_unmount(mountpoint)	
		return False

	logging.debug("export:"+export+" is mounted on:"+mountpoint)
	return True



#check job status 
def check_verbose_job_status (jobname, task='smartassess'):

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
	except Exception as e:
		job = None

	if not job and not os.path.exists(jobcachedir):
		logging.debug("job:"+jobname+" does not exist and cahced folder:"+jobcachedir+" does not exists")
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
					try:
				 		starttime = allocdata['TaskStates'][task]['StartedAt']
				 		starttime = starttime.split('T')[0]+' '+starttime.split('T')[1].split('.')[0]				
					except Exception as e:
						starttime = '-'
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

		if nodeid.data.sizek < 0: nodeid.data.sizek = 0

		nodeid.data.size_hr = str(nodeid.data.sizek)+' KiB'
		if 1024 <= nodeid.data.sizek <= 1024*1024:
			nodeid.data.size_hr = format(int(nodeid.data.sizek/1024),',')+' MiB'
		elif 1024*1024 <= nodeid.data.sizek <= 1024*1024*1024:
			nodeid.data.size_hr = format(int(nodeid.data.sizek/1024/1024),',')+' GiB'
		elif 1024*1024*1024*1024 <= nodeid.data.sizek:
			nodeid.data.size_hr = format(int(nodeid.data.sizek/1024/1024/1024),',')+' TiB'

		if nodeid.data.inodes < 0: nodeid.data.inodes = 0
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
			if not inode in list(hardlinks.keys()): 
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
			if not longesttask in list(hardlinks[inode]['tasks'].keys()): 
				hardlinks[inode]['tasks'][longesttask] = {}
				hardlinks[inode]['tasks'][longesttask]['count'] = 1
				hardlinks[inode]['tasks'][longesttask]['paths'] = {}
				hardlinks[inode]['tasks'][longesttask]['paths'][path] = True
				if not 'taskcount' in list(hardlinks[inode].keys()):
					hardlinks[inode]['taskcount'] = 1
				else:	
					hardlinks[inode]['taskcount'] += 1
				
				#updating tree structure with number of hardlink nuber of tasks 
				if int(hardlinks[inode]['taskcount']) > task.data.hardlinks:
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
								
								if not task in list(hardlinkpaths.keys()):
									hardlinkpaths[task] = {}
								if not path in list(hardlinkpaths[task].keys()):
									hardlinkpaths[task][path] = {}

								logging.debug("task:"+task+" path:"+path+" have the following links in another task:"+task1+" path:"+path1)
								hardlinkpaths[task][path][path1]=task1

	return hardlinkpaths

#delete smartassess scan data 
def smartassess_fs_linux_delete(forceparam):
	smartassessdictcopy = copy.deepcopy(smartassessdict)
	for smartassessjob in smartassessdict:
		src = smartassessdictcopy[smartassessjob]['src']
		if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
			force = forceparam
			if not force: force = query_yes_no("delete job for source:"+src,'no')
			if force:
				logging.info("delete smartassess job for source:"+src) 
				#delete smartassess jobs 
				delete_job_by_prefix(smartassessjob)

				jobcachedir = os.path.join(cachedir,'job_'+smartassessjob)
				if os.path.exists(jobcachedir):
					logging.debug("delete smartassess cache dir:"+jobcachedir)
					try:
						rmout = shutil.rmtree(jobcachedir) 
					except Exception as e:
						logging.error("could not delete smartassess cache dir:"+jobcachedir)

				jobcachedir = os.path.join(cachedir,'job_'+smartassessjob+'_hardlink_scan')
				if os.path.exists(jobcachedir):
					logging.debug("delete smartassess cache dir:"+jobcachedir)
					try:
						rmout = shutil.rmtree(jobcachedir) 
					except Exception as e:
						logging.error("could not delete smartassess cache dir:"+jobcachedir)


				#delete entry from smartassessdictcopy
				del smartassessdictcopy[smartassessjob]

	#dumping smartassessdictcopy to json file 
	try:
		with open(smartassessjobdictjson, 'w') as fp:
			json.dump(smartassessdictcopy, fp)
		fp.close()
	except Exception as e:
		logging.error("cannot write job json file:"+smartassessjobdictjson)
		exit(1)												

#show status of the smartassess jobs/create csv file 
def smartassess_fs_linux_status_createcsv(args,createcsv):
	global mininodespertask_minborder, mininodespertask
	global smartassessdict
	global totaljobscreated,totaljobssizek

	dirtree = Tree()

	displaytasks = False
	displaylinks = False

	#used for temp nount points for create csv 
	tempmountpointsrc = '/tmp/src_'+str(os.getpid())
	tempmountpointdst = '/tmp/dst_'+str(os.getpid())
	csv_columns = ["#JOB NAME","SOURCE PATH","DEST PATH","SYNC SCHED","CPU MHz","RAM MB","TOOL","FAILBACKUSER","FAILBACKGROUP","EXCLUDE DIRS"]
	csv_data = []

	try:
		if not createcsv:
			#validate we are ready for status 
			logging.debug("starting smartassess status") 
			displaytasks = args.tasks
			displaylinks = args.hardlinks	
				
		else:
			if not args.destination:
				logging.error("destination is required when creating csv")
				exit(1)	
			#validate we are ready for csv creation
			src = args.source
			dst = args.destination

			logging.debug("starting smartassess createcsv") 	

			if not re.search("\S+\:\/\S+", src):
				logging.error("source format is incorrect: " + src) 
				exit(1)	
			if not re.search("\S+\:\/\S+", src):
				logging.error("destination format is incorrect: " + dst)
				exit(1)		

			if os.path.isfile(args.csvfile):
				logging.warning("csv file:"+args.csvfile+" already exists")
				if not query_yes_no("do you want to overwrite it?", default="no"): exit(0)

			logging.debug("temporary mounts for building destination directory structure will be:"+tempmountpointsrc+" and "+tempmountpointdst)

			logging.debug("validating src:" + src + " and dst:" + dst+ " are mountable")

			if not nfs_mount(src,tempmountpointsrc):
				logging.error("cannot mount src using nfs: " + src)
				exit(1)					
			if not nfs_mount(dst,tempmountpointdst):
				logging.error("cannot mount dst using nfs: " + dst)
				exit(1)

			jobname = args.job
			if jobname == '' or not jobname: jobname = 'smartassess'+str(os.getpid())

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
					

		infofound = False 

		table = PrettyTable()
		table.field_names = ["Path","Scan Status","Scan Start","Scan Time",'Scanned','Errors',"Hardlink Scan","HL Scan Time",'HL Scanned','HL Errors','Total Capacity','# Suggested Tasks','# Cross Task Hardlinks']	

		for smartassessjob in smartassessdict:
			totaljobscreated = 0 
			totaljobssizek = 0 

			src = smartassessdict[smartassessjob]['src']

			if (not createcsv and (srcfilter == '' or fnmatch.fnmatch(src, srcfilter))) or (createcsv and src == args.source):

				results = check_verbose_job_status(smartassessjob)
				if not createcsv:
					resultshardlink = check_verbose_job_status(smartassessjob+'_hardlink_scan')
				else:
					resultshardlink = {}
					resultshardlink['status'] = 'not relevant'

				scantime = '-'
				scanned = '-'
				errors = '-'

				if results['status'] != 'not started':
					#stderr parse
					stderrresults = parse_stats_from_log ('file',results['stderrlog'],'stderr')
					if 'time' in list(stderrresults.keys()): 
						scantime = stderrresults['time']
					if 'scanned' in list(stderrresults.keys()): 
						scanned = stderrresults['scanned']
					if 'errors' in list(stderrresults.keys()): 
						errors = stderrresults['errors']			

				scantimehl = '-'
				scannedhl = '-'
				errorshl = '-'
				crosstaskcount = 0
				if resultshardlink['status'] != 'not started' and resultshardlink['status'] != 'not relevant' :
					#stderr parse
					stderrresults = parse_stats_from_log ('file',resultshardlink['stderrlog'],'stderr')
					if 'time' in list(stderrresults.keys()): 
						scantimehl = stderrresults['time']
					if 'scanned' in list(stderrresults.keys()): 
						scannedhl = stderrresults['scanned']
					if 'errors' in list(stderrresults.keys()): 
						errorshl = stderrresults['errors']	

				#handle completed jobs without log
				if results['status'] == 'completed' and results['stdoutlog'] == '':
					results['status'] = 'failed'

				if results['status'] == 'completed' and (resultshardlink['status'] in ['not started','completed','not relevant']):
					#parsing log to tree
					dirtree = smartassess_parse_log_to_tree(src,results['stdoutlog'])
					dirtree = createtasksfromtree(dirtree, dirtree.get_node(src))

					if resultshardlink['status'] == 'completed':
						if resultshardlink['stdoutlog'] != '':
							hardlinks,crosstaskcount = createhardlinkmatches(dirtree,resultshardlink['stdoutlog'])
						else:
							hardlinks = {}
							crosstaskcount = 0			

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

				#create the CSV file and directory structure for the jobs 
				if createcsv:			
					#create the exclude dir file 
					exludedirlist = ''
					for task in dirtree.filter_nodes(lambda x: x.data.createjob):
						if not task.is_root():
							exludedirlist += task.identifier+'\n'

					for task in dirtree.filter_nodes(lambda x: x.data.createjob):
						nfssrcpath = task.identifier
						nfsdstpath = dst+nfssrcpath[len(src):]
						srcpath = tempmountpointsrc+nfssrcpath[len(src):]
						dstpath = tempmountpointdst+nfssrcpath[len(src):]
						if not task.is_root():
							logging.debug("src path: "+nfssrcpath+" and dst path: "+nfsdstpath+ " will be configured as xcption job")
						else:
							logging.debug("src path: "+nfssrcpath+" and dst path: "+nfsdstpath+ " will be configured as xcption job with exclude dirlist")
							logging.debug("excludedir file content will be:\n"+exludedirlist)

						if not os.path.isdir(srcpath):
							logging.error("cannot find source directory:"+nfssrcpath+" please refresh your smartassess scan")
							unmountdir(tempmountpointsrc)
							unmountdir(tempmountpointdst)
							exit(1)

						if os.path.isdir(dstpath):
							logging.debug("destination directory:"+nfsdstpath+" already exists validating it is not containing files")
							dstdirfiles = os.listdir(dstpath)
							if (len(dstdirfiles)>1 and dstdirfiles[0] != '.snapshot') or (len(dstdirfiles) == 1 and dstdirfiles[0] == '.snapshot'):
								logging.warning("dst:"+nfsdstpath+ " for source path:"+nfssrcpath+" exists and contains files")
								if not query_yes_no("do you want to to continue?", default="no"):
									unmountdir(tempmountpointsrc)
									unmountdir(tempmountpointdst)
									exit(1) 
							else:
								logging.info("destination path:"+nfsdstpath+ " for source path:"+nfssrcpath+" exists and empty")
						else:
							logging.info("destination path:"+nfsdstpath+" does not exist. creating using rsync")
							includedirs = ''
							prevdir = ''
							for d in nfssrcpath[len(src):].split('/'):
								if d == '': 
									includedirs += ' --include "/"'
								else:

									includedirs += ' --include "/'+prevdir+d+'/"'
									prevdir += d+'/'
					
							rsynccmd = 'rsync -av'+includedirs+" --exclude '*' \""+tempmountpointsrc+'/" "'+tempmountpointdst+'/"'
							logging.debug("running the following rsync command to create dst directory:"+rsynccmd+" ("+nfsdstpath+")")
							if os.system(rsynccmd):
								logging.error("creation of dst dir:"+nfsdstpath+" using rsync failed")
								unmountdir(tempmountpointsrc)
								unmountdir(tempmountpointdst)							
								exit(1)

						excludefilename= '' 
						if task.is_root():
							excludefilename = src.replace(':/','-_').replace('/','_').replace(' ','-').replace('\\','_').replace('$','_dollar')+'.exclude'
							excludefilepath = os.path.join(excludedir,excludefilename)
							if not os.path.isdir(excludedir):
								subprocess.call( [ 'mkdir', '-p',excludedir ] )	
							try:
								logging.debug("writing exlude dir to exlude file:"+excludefilepath)
								with open(excludefilepath, 'w') as f:
									f.write(exludedirlist)							
								f.close()
							except Exception as e:
								logging.error("could not write data to exlude file:"+excludefilepath)
								unmountdir(tempmountpointsrc)
								unmountdir(tempmountpointdst)
								exit(1)								

						csv_data.append({"#JOB NAME":jobname,"SOURCE PATH":nfssrcpath,"DEST PATH":nfsdstpath,"SYNC SCHED":defaultjobcron,"CPU MHz":defaultprocessor,"RAM MB":defaultram,"TOOL":'',"FAILBACKUSER":"","FAILBACKGROUP":"","EXCLUDE DIRS":excludefilename})

					#create the csv file
					try:
						with open(args.csvfile, 'w') as c:
							writer = csv.DictWriter(c, fieldnames=csv_columns)
							writer.writeheader()
							for data in csv_data:
								writer.writerow(data)
							logging.info("job csv file:"+args.csvfile+" created")
					except IOError:
						logging.error("could not write data to csv file:"+args.csvfile)
						unmountdir(tempmountpointsrc)
						unmountdir(tempmountpointdst)
						exit(1)						
					

				infofound = True 
				if displaytasks and not createcsv:

					table.border = False
					table.align = 'l'
					print("")
					print(table)	

					if results['status'] == 'completed' and (resultshardlink['status'] == 'not started' or resultshardlink['status'] == 'completed'):
						table = PrettyTable()
						table.field_names = ["Path","Scan Status","Scan Start","Scan Time",'Scanned','Errors',"Hardlink Scan","HL Scan Time",'HL Scanned','HL Errors','Total Capacity','# Suggested Tasks','# Cross Task Hardlinks']	

						print("")
						print("   Suggested tasks:")
						print("")
						tasktable = PrettyTable()
						tasktable.field_names = ["Path","Total Capacity","Inodes","Root Task","Cross Task Hardlinks"]	
						
						for task in dirtree.filter_nodes(lambda x: x.data.createjob):
							
							taskhardlinksinothertasks = 0
							if crosstaskcount > 0:
								hardlinklist = gethardlinklistpertask(hardlinks,task.identifier)
								
								if task.identifier in list(hardlinklist.keys()):
									taskhardlinksinothertasks = len(hardlinklist[task.identifier])

							tasktable.add_row([task.identifier,task.data.size_hr,task.data.inodes_hr,task.is_root(),taskhardlinksinothertasks])
							if taskhardlinksinothertasks > 0 and displaylinks:

								tasktable.border = False
								tasktable.align = 'l'
								tasktable.padding_width = 5
								print(tasktable)
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
								print("")
								print(hardlinktable)				
								print("")


						tasktable.border = False
						tasktable.align = 'l'
						tasktable.padding_width = 5
						#tasktable.sortby = 'Path'
						print(tasktable)								

					else:
						print('     vebose information not yet avaialable. it will be available when scan will be completed')
						table = PrettyTable()
						table.field_names = ["Path","Scan Status","Scan Start","Scan Time",'Scanned','Errors',"Hardlink Scan","HL Scan Time",'HL Scanned','HL Errors','Total Capacity','# Suggested Tasks','# Cross Task Hardlinks']							
		
		if not displaytasks and infofound and not createcsv:
			table.border = False
			table.align = 'l'

			print("")
			print(table)			

		if not infofound:
			print("     no info found")
	except KeyboardInterrupt:
		print("")
		print("aborted")
	nfs_unmount(tempmountpointsrc)
	nfs_unmount(tempmountpointdst)


def smartassess_parse_log_to_tree (basepath, inputfile):
	
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
		logging.warning("log file:"+inputfile+" does not exists")
		exit(1)

	with open(inputfile) as f:
	    content = f.readlines()

	content = [x.strip() for x in content] 
	for line in content:
		matchObj = re.search("^([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) (\SiB) ([0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?\S?) inode. ("+basepath+".+$)", line)
		if matchObj:
			size = float(matchObj.group(1).replace(',',''))
			sizeq = matchObj.group(4)
			inodesstr = matchObj.group(5).replace(',','')
			if 'M' in inodesstr:
				inodesstr = float(re.findall("\d+\.\d+", inodesstr)[0])*1000000

			inodes = int(inodesstr)
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


#smart assessment for linux based on capacity and inode count. this will initiate a scan 
def smartassess_fs_linux_start(src,depth,locate_cross_task_hardlink):
	global smartassessdict

	logging.debug("starting smartassess jobs for src:"+src) 

	smartassess_job_name = 'smartassess_'+src.replace(':/','-_')
	smartassess_job_name = smartassess_job_name.replace('/','_')
	smartassess_job_name = smartassess_job_name.replace(' ','-')
	smartassess_job_name = smartassess_job_name.replace('\\','_')
	smartassess_job_name = smartassess_job_name.replace('$','_dollar')	

	if smartassess_job_name in list(smartassessdict.keys()):
		logging.error("smartassess job already exists for src:"+src+', to run again please delete exisiting task 1st') 
		exit(1)	

	if not re.search("^\S+\:\/\S+", src):
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

	#create smartassess job

	#loading job ginga2 templates 
	templates_dir = ginga2templatedir
	env = Environment(loader=FileSystemLoader(templates_dir) )
	
	try:
		smartassess_template = env.get_template('nomad_smartassses.txt')
	except Exception as e:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_smartassses.txt'))
		exit(1)

	jobdir = os.path.join(smartassessdir,smartassess_job_name)
	if not os.path.exists(jobdir):
		logging.debug("creating job dir:"+jobdir)
		try:
			os.makedirs(jobdir)
		except Exception as e:
			logging.error("could not create job dir:"+jobdir)
			exit(1)		

	srchost,srcpath = src.split(":")

	#creating smaetassess job 
	smartassessjob_file = os.path.join(jobdir,smartassess_job_name+'.hcl')	
	logging.debug("creating smartassess job file: " + smartassessjob_file)				
		
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

	with open(smartassessjob_file, 'w') as fh:
		fh.write(smartassess_template.render(
			dcname=dcname,
			os=ostype,
			smartassess_job_name=smartassess_job_name,
			xcppath=xcpbinpath,
			args=cmdargs,
			memory=defaultram,
			cpu=defaultprocessor
		))

	logging.info("starting smartassess scan for src:"+src)
	if not start_nomad_job_from_hcl(smartassessjob_file, smartassess_job_name):
		logging.error("failed to create nomad job:"+smartassess_job_name)
		exit(1)
	response = requests.post(nomadapiurl+'job/'+smartassess_job_name+'/periodic/force')	
	if not response.ok:
		logging.error("job:"+smartassess_job_name+" force start failed") 
		exit(1)		

	#creating hadlink scan smaetassess job 
	smartassess_hardlink_job_name = smartassess_job_name+'_hardlink_scan'
	hardlinksmartassessjob_file = os.path.join(jobdir,smartassess_hardlink_job_name+'.hcl')	
	logging.debug("creating hardlink smartassess job file: " + hardlinksmartassessjob_file)			

	cmdargs = "scan\",\"-noid\",\"-match\",\"type == f and nlinks > 1\",\"-fmt\",\"'{},{}'.format(x,fileid)\",\""+src
	with open(hardlinksmartassessjob_file, 'w') as fh:
		fh.write(smartassess_template.render(
			dcname=dcname,
			os=ostype,
			smartassess_job_name=smartassess_hardlink_job_name,
			xcppath=xcpbinpath,
			args=cmdargs,
			memory=defaultram,
			cpu=defaultprocessor
		))

	if locate_cross_task_hardlink:
		logging.info("starting smartassess hardlink scan:"+smartassess_hardlink_job_name)
		if not start_nomad_job_from_hcl(hardlinksmartassessjob_file, smartassess_hardlink_job_name):
			logging.error("failed to create nomad job:"+smartassess_hardlink_job_name)
			exit(1)
		response = requests.post(nomadapiurl+'job/'+smartassess_hardlink_job_name+'/periodic/force')	
		if not response.ok:
			logging.error("job:"+smartassess_hardlink_job_name+" force start failed") 
			exit(1)		

	#fill dict with info
	smartassessdict[smartassess_job_name] = {}
	smartassessdict[smartassess_job_name]['src'] = src
	smartassessdict[smartassess_job_name]['src'] = src
	smartassessdict[smartassess_job_name]['cpu'] = defaultprocessor
	smartassessdict[smartassess_job_name]['memory'] = defaultram
	smartassessdict[smartassess_job_name]['ostype'] = ostype
	smartassessdict[smartassess_job_name]['depth'] = depth
	smartassessdict[smartassess_job_name]['locate_cross_task_hardlink'] = locate_cross_task_hardlink
	smartassessdict[smartassess_job_name]['dcname'] = dcname

	#dumping jobsdict to json file 
	try:
		with open(smartassessjobdictjson, 'w') as fp:
			json.dump(smartassessdict, fp)
		fp.close()
	except Exception as e:
		logging.error("cannot write smart assess job json file:"+smartassessjobdictjson)
		exit(1)


#assessment of filesystem and creation of csv file out of it 
def assess_fs_linux(csvfile,src,dst,depth,acl,jobname):
	logging.debug("starting to assess src:" + src + " dst:" + dst) 

	if not re.search("^\S+\:\/.*", src):
		logging.error("source format is incorrect: " + src) 
		exit(1)	
	if not re.search("^\S+\:\/.*", dst):
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
	csv_columns = ["#JOB NAME","SOURCE PATH","DEST PATH","SYNC SCHED","CPU MHz","RAM MB","TOOL","FAILBACKUSER","FAILBACKGROUP","EXCLUDE DIRS","ACL COPY"]
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
		taskcounter = 0 
		for o in srcdirstructure:

			path = o[0]
			dircount = o[1]
			filecount = o[2]

			currentdepth = path.count(os.path.sep) + 1
			if path == './': currentdepth = 1

			#print path,depth,currentdepth
			
			nfssrcpath = src+path.lstrip('.')
			nfsdstpath = dst+path.lstrip('.')

			dstpath = tempmountpointdst+path.lstrip('.')

			
			#if filecount > 0 and (currentdepth < depth or (currentdepth == depth and dircount > 0)):
			if (filecount > 0 and dircount > 0 and currentdepth < depth):
				logging.warning("source directory: "+nfssrcpath+" contains "+str(filecount)+" files. those files will not be included in the xcption jobs and need to be copied externaly")
	
				warning=True 
			else:
				if os.path.exists(dstpath):
					dstdirfiles = os.listdir(dstpath)
					if (len(dstdirfiles)>1 and dstdirfiles[0] != '.snapshot') or (len(dstdirfiles) == 1 and dstdirfiles[0] != '.snapshot'):
						logging.error("destination dir: "+nfsdstpath+ " for source dir: "+nfssrcpath+" contains files")
						unmountdir(tempmountpointsrc)
						unmountdir(tempmountpointdst)
						exit(1)
					else:
						logging.info("destination dir: "+nfsdstpath+ " for source dir: "+nfssrcpath+" already exists and empty")

			#check if destination directory exists/contains files
			if taskcounter > 50:
				logging.warning("the amount of created jobs is above 50, this will create extensive amount of xcption jobs")
				warning=True  
				taskcounter = -1

			#create xcption job entry
			#print depth,currentdepth,dircount,nfssrcpath,path
			#if (currentdepth < depth-1 and dircount == 0) or (currentdepth == depth-1 and currentdepth > 0) or (depth == 1):
			if (currentdepth < depth and dircount == 0) or (currentdepth == depth) or (depth == 1):
				if nfssrcpath == src+"/" and nfsdstpath == dst+"/": 
					nfssrcpath = src
					nfsdstpath = dst

				logging.debug("src path: "+nfssrcpath+" and dst path: "+nfsdstpath+ " will be configured as xcp job")
				#append data to csv 
				csv_data.append({"#JOB NAME":jobname,"SOURCE PATH":nfssrcpath,"DEST PATH":nfsdstpath,"SYNC SCHED":defaultjobcron,"CPU MHz":defaultprocessor,"RAM MB":defaultram,"TOOL":'',"FAILBACKUSER":"","FAILBACKGROUP":"","EXCLUDE DIRS":"","ACL COPY":acl})
				if taskcounter != -1: taskcounter += 1


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
				#use xcp to build the directory structure of the dest filesystem 
				#xcpcmd = xcplocation + ' copy -noID -match "(type==d and depth=='+str(depth)+') or (type==f and depth<'+str(depth)+')" '+ src  + ' ' + dst
				# logging.info("xcp can be used to create the destination initial directory structure for xcption jobs")
				# logging.info("xcp command to sync directory structure for the required depth will be:")				
				# logging.info(xcpcmd)
				# if query_yes_no("do you want to run xcp copy to build the directory structure in the dest ?", default="no"): 
				#  	end=False 
				#  	logging.info("=================================================================")
				#  	logging.info("========================Starting xcp=============================")
				#  	logging.info("=================================================================")
				#  	#run xcp and check if failed 
				#  	if os.system(xcpcmd):
				#  		logging.error("xcp copy failed")
				#  		exit(1)
				#  	logging.info("=================================================================")
				#  	logging.info("=====================xcp ended successfully======================")
				#  	logging.info("=================================================================")
				
				#use rsync to build the directory structure of the dest filesystem 
				depthrsync = ''
				for x in range(depth):
					depthrsync += '/*'
				rsynccmd = 'rsync -av --exclude ".snapshot" --exclude="'+depthrsync+ '" -f"+ */" -f"- *"  "'+tempmountpointsrc+'/" "'+tempmountpointdst+'/"'
				logging.info("rsync command to sync directory structure for the required depth will be:")
				logging.info("rsync can be used to create the destination initial directory structure for xcption jobs")
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
		print("")
		print("aborted")
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
				logging.error("\n\n"+results['stderr'].decode('utf-8'))
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
				if not path in list(dirs.keys()):
					dirs[path]={}
					dirs[path]["filecount"] = 0
					dirs[path]["dircount"] = 0

				if basedir != '':
					if basedir in list(dirs.keys()):
						dirs[basedir]["dircount"] += 1
					else:
						dirs[basedir]={}
						dirs[basedir]["filecount"] = 0
						dirs[basedir]["dircount"] = 1						

			elif pathtype == "f":
				if basedir in list(dirs.keys()):
					dirs[basedir]["filecount"] += 1
				else:
					dirs[basedir]={}
					dirs[basedir]["filecount"] = 1
					dirs[basedir]["dircount"] = 0

	return dirs

#assessment of filesystem and creation of csv file out of it 
def assess_fs_windows(csvfile,src,dst,depth,jobname):
	logging.debug("trying to assess src:" + src + " dst:" + dst) 

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

	logging.info("validating src:" + src + " and dst:" + dst+ " cifs paths are available from one of the windows servers") 
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
	csv_columns = ["#JOB NAME","SOURCE PATH","DEST PATH","SYNC SCHED","CPU MHz","RAM MB","TOOL","FAILBACKUSER","FAILBACKGROUP","EXCLUDE DIRS"]
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

		if path in list(dstdirstructure.keys()):
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
			csv_data.append({"#JOB NAME":jobname,"SOURCE PATH":srcpath,"DEST PATH":dstpath,"SYNC SCHED":defaultjobcron,"CPU MHz":defaultprocessor,"RAM MB":defaultram,"TOOL":tool,"FAILBACKUSER":failbackuser,"FAILBACKGROUP":failbackgroup,"EXCLUDE DIRS":""})

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

			pscmd1 = robocopywinpathassess+" /E /NP /COPY:DATSO /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:"+str(depth)+" \""+src+"\" \""+dst+"\" /XF *"
			pscmd2 = robocopywinpathassess+" /E /NP /COPY:DATSO /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:"+str(depth-1)+" \""+src+"\" \""+dst+"\""+excludedir

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
						logging.error("errorlog:\n"+results['stderr'].decode('utf-8'))	
					if results['stdout']:
						logging.error("errorlog:\n"+results['stdout'].decode('utf-8'))						
					exit(1)		

				print(results['stdout'])

				results = run_powershell_cmd_on_windows_agent(pscmd2,True)
				if results['status'] != 'complete':
					logging.error("robocopy failed")
					if results['stderr']:
						logging.error("errorlog:\n"+results['stderr'].decode('utf-8'))	
					if results['stdout']:
						logging.error("errorlog:\n"+results['stdout'].decode('utf-8'))							
					exit(1)							
				print(results['stdout'])

				logging.info("=================================================================")
				logging.info("=================robocopy ended successfully=====================")
				logging.info("=================================================================")

			logging.info("csv file:"+csvfile+ " is ready to be loaded into xcption")

#move job 
def modify_tasks(args,forceparam):

	tojob = args.tojob
	tocron = args.cron
	tocpu = args.cpu
	toram = args.ram
	
	global jobsdict

	chnaged = False 

	jobsdictcopy = copy.deepcopy(jobsdict)
	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:			
			for src in jobsdict[jobname]:
				if srcfilter == '' or fnmatch.fnmatch(src, srcfilter):
					jobdetails = jobsdict[jobname][src]
					force = forceparam
					if not force: force = query_yes_no("are you sure you want to modify task properties for source:"+src,'no')

					if force:
						

						if tocron:
							logging.info("src:"+src+" cron changed to:"+tocron)
							jobsdictcopy[jobname][src]['cron'] = tocron
						if tocpu:
							logging.info("src:"+src+" cpu changed to:"+str(tocpu))
							jobsdictcopy[jobname][src]['cpu'] = tocpu
						if toram:
							logging.info("src:"+src+" ram changed to:"+str(toram))
							jobsdictcopy[jobname][src]['memory'] = toram					
						if tojob:
							if jobname == tojob:
								logging.info("src:"+src+" is already in job:"+tojob+",skipping")
							else: 
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
									except Exception as e:
										logging.error("could not create new job dir:" + dstjobdir)
										exit (1)

								#moving files 
								try:
									logging.debug("tring to move:"+os.path.join(srcjobdir,baseline_job_file)+" to:"+os.path.join(dstjobdir,baseline_job_file))
									shutil.copy(os.path.join(srcjobdir,baseline_job_file),os.path.join(dstjobdir,baseline_job_file))
								except Exception as e:
									logging.error("could not move file:"+os.path.join(srcjobdir,baseline_job_file)+" to:"+os.path.join(dstjobdir,baseline_job_file))
									exit (1)						

								try:
									logging.debug("tring to move:"+os.path.join(srcjobdir,sync_job_file)+" to:"+os.path.join(dstjobdir,sync_job_file))
									shutil.copy(os.path.join(srcjobdir,sync_job_file),os.path.join(dstjobdir,sync_job_file))
								except Exception as e:
									logging.error("could not move file:"+os.path.join(srcjobdir,sync_job_file)+" to:"+os.path.join(dstjobdir,sync_job_file))
									exit (1)	

								try:
									logging.debug("tring to move:"+os.path.join(srcjobdir,verify_job_file)+" to:"+os.path.join(dstjobdir,verify_job_file))
									shutil.copy(os.path.join(srcjobdir,verify_job_file),os.path.join(dstjobdir,verify_job_file))
								except Exception as e:
									logging.error("could not move file:"+os.path.join(srcjobdir,verify_job_file)+" to:"+os.path.join(dstjobdir,verify_job_file))
									exit (1)	
						#set to true to recreate hcl files 
						chnaged = True

						logging.debug("dumping modified information to jsonfile"+jobdictjson)
						try:
							with open(jobdictjson, 'w') as fp:
								json.dump(jobsdictcopy, fp)
							fp.close()
						except Exception as e:
							logging.error("cannot write job json file:"+jobdictjson)
							exit(1)	
	
	if chnaged and (toram or tocpu or tocron):
		logging.debug("recreating HCL files from updated json")
		jobsdict = {}
		jobsdict = copy.deepcopy(jobsdictcopy)
		create_nomad_jobs()
		logging.info("please run sync for relevant tasks to activate modified cpu/ram/scheudle")

#abort jobs 
def abort_jobs(jobtype, forceparam):

	for jobname in jobsdict:
		if jobfilter == '' or jobfilter == jobname:
			jobdir = os.path.join(jobsdir,jobname)

			#check if job dir exists
			if not os.path.exists(jobdir):
				logging.warning("job config directory:" + jobdir + " not exists") 
			
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
										logging.debug("running the command:"+xcplocation+' diag -rmid '+xcpindexname)
										DEVNULL = open(os.devnull, 'wb')
										if subprocess.call( [ xcplocation, 'diag', '-rmid', xcpindexname ],stdout=DEVNULL,stderr=DEVNULL):
											logging.debug("failed to delete xcp index:"+xcpindexname)
									if tool=='cloudsync':
										logging.info("aborting cloudsync job (expect 1-2 minutes until the cloudsync job will be aborted)")
										cloudsync_cmd = [cloudsyncscript,'abort','-s',src,'-d',dst]
										cloudsyncrel = {}
										try:
											validatejson = subprocess.check_output(cloudsync_cmd,stderr=subprocess.STDOUT)
										except Exception as e:
											logging.error("cannot abort cloudsync relationship src:"+src+" dst:"+dst)
											exit(1)											

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
										except Exception as e:
											logging.warning("could not delete dir:"+jobcachedir)

									jobaborted = True									
								else:
									logging.debug("job status us is:"+jobstatus+', skipping')
								

							if not jobaborted:
								logging.info("no running/pending jobs found")

#export csv file 
def export_csv(csvfile):

	if os.path.isfile(csvfile):
		if not query_yes_no("csv file:"+csvfile+" already exists, overwrite ?",'no'):
			exit(0)

	try: 
		with open(csvfile, 'w') as file:
			writer = csv.writer(file)
			writer.writerow(["#JOB NAME","SOURCE PATH","DEST PATH","SYNC SCHED","CPU MHz","RAM MB","TOOL","FAILBACKUSER","FAILBACKGROUP","EXCLUDE DIRS"])

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
							jobcron           = jobdetails['cron']
							cpu    			  = jobdetails['cpu']
							memory            = jobdetails['memory']
							ostype			  = jobdetails['ostype']
							tool              = jobdetails['tool']
							failbackuser      = jobdetails['failbackuser']
							failbackgroup     = jobdetails['failbackgroup']
							excludedirfile    = jobdetails['excludedirfile']
							
							logging.info("exporting src:"+src+" to dst:"+dst+" info")
							writer.writerow([jobname,src,dst,jobcron,cpu,memory,tool,failbackuser,failbackgroup,excludedirfile])
	except Exception as e:
		logging.error("error exporting to csv file:"+csvfile)
		exit(1)

#remove logs from dict 
def normalizedict (jsondict):
	jsondictnormalized = copy.deepcopy(jsondict)
	for job in jsondictnormalized:
		for src in jsondictnormalized[job]:		
			for phase in jsondictnormalized[job][src]['phases']:
				#if 'stderrlogcontent' in phase: del phase['stderrlogcontent']
				#if 'stdoutlogcontent' in phase: del phase['stdoutlogcontent']
				#if 'stdoutlogpath' in phase: del phase['stdoutlogpath']
				#if 'stderrlogpath' in phase: del phase['stderrlogpath']
				#if 'stdoutlogexists' in phase: del phase['stdoutlogexists']
				#if 'stderrlogexists' in phase: del phase['stderrlogexists']

				for key in phase:
					#if key in ['errors','deleted','modified','reviewed','scanned','copied']:
					if key in ['deleted','modified','reviewed','copied']:
						
						phase[key] = str(phase[key]).replace(',','')
						if phase[key] in ['-','']: phase[key] = 0

						try:
							if 'M' in str(phase[key]): phase[key] = int(phase[key].replace('M',''))*1000000
							phase[key] = int(phase[key])
						except Exception as e:
							phase[key] = 0 
					if key == 'duration':
						matchObj = re.match("((\d+)h)?((\d+)m)?(\d+)s",phase[key])
						if matchObj:
							durationsec = 0
							if matchObj.group(2) > 0: durationsec += int(matchObj.group(2))*3600 
							if matchObj.group(4) > 0: durationsec += int(matchObj.group(4))*60
							if matchObj.group(5) > 0: durationsec += int(matchObj.group(5))
						else:
							durationsec = 0

				phase['durationsec'] = durationsec

	return jsondictnormalized

#def start web server using flask
def start_flask(tcpport):
	from flask import Flask,render_template, send_file, send_from_directory, request, Markup

	#disable flask logging
	cli = sys.modules['flask.cli']
	cli.show_server_banner = lambda *x: None

	app = Flask(__name__, static_url_path=webtemplatedir, template_folder=webtemplatedir)
	app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
	env = app.jinja_env
	env.add_extension('jinja2.ext.do')
	env.add_extension('jinja2.ext.autoescape')

	_js_escapes = {
        '\\': '\\u005C',
        '\'': '\\u0027',
        '"': '\\u0022',
        '>': '\\u003E',
        '<': '\\u003C',
        '&': '\\u0026',
        '=': '\\u003D',
        '-': '\\u002D',
        ';': '\\u003B',
        u'\u2028': '\\u2028',
        u'\u2029': '\\u2029'
	}
	# Escape every ASCII character with a value less than 32.
	_js_escapes.update(('%c' % z, '\\u%04X' % z) for z in range(32))

	def escapejs(value):
		return Markup("".join(_js_escapes.get(l, l) for l in value))

	app.jinja_env.filters['escapejs'] = escapejs

	@app.route("/")
	@app.route("/index.html")
	def tableindex():

		parse_nomad_jobs_to_files(False)
		global srcfilter 
		global phasefilter
		global jobfilter 

		jobfilter = ''; srcfilter = ''; phasefilter = ''

		#include jobfilter in http
		if request.args.get('jobfilter') != None: jobfilter = request.args.get('jobfilter')
		if jobfilter == 'all_jobs': jobfilter = ''
		
		#include srcfilter in http
		if request.args.get('srcfilter') != None: srcfilter = request.args.get('srcfilter')
		if srcfilter != '' and not '*' in srcfilter:
			srcfilter = '*'+srcfilter+'*'

		#include phase filter in http
		if request.args.get('phasefilter') != None: phasefilter = request.args.get('phasefilter')

		#include verbose in httm		
		statustype = 'general'
		if request.args.get('verbose') == 'true': statustype = 'verbose'

		#include logs in httm
		showlogs = False
		if request.args.get('logs') == 'true' and request.args.get('verbose') == 'true': showlogs = True

		#declare global dicts 
		global jobsdict
		global jsondict 
		global jsongeneraldict

		#zero global hash from previous content 
		jobsdict = {}; jsondict = {}; jsongeneraldict = {}
	
		load_jobs_from_json(jobdictjson)
		parse_nomad_jobs_to_files(False)
		jsondict,jsongeneraldict = create_status(statustype,False,'silent')
		#normalizedjsondict = normalizedict (jsondict)
		return render_template('index.html', jsongeneraldict=jsongeneraldict, jsondict=jsondict, jobs=list(jobsdict.keys()), statustype=statustype, showlogs=showlogs)


	#return all other files up to 3 level deep (css,js)
	@app.route("/<path>")
	def table(path):
		return send_from_directory(webtemplatedir,path)
	@app.route("/<path>/<path1>")
	def table1(path,path1):
		return send_from_directory(webtemplatedir,os.path.join(path,path1))

	@app.route("/<path>/<path1>/<path2>")
	def table2(path,path1,path2):
		return send_from_directory(webtemplatedir,os.path.join(path,path1,path2))

	hostname = socket.gethostname()    
	ip = socket.gethostbyname(hostname)  
	app.run(host='0.0.0.0',port=tcpport)

def upload_file (path, linuxpath, windowspath):
	if not os.path.isfile(path):
		logging.error("cannot find source file to upload:"+path)
		exit(1)
	if path.endswith('/license') and not linuxpath:
		linuxpath = '/opt/NetApp/xFiles/xcp/license'

	if path.endswith('/license') and not windowspath:
		windowspath = 'C:\\NetApp\\XCP\\license'

	if not linuxpath and not windowspath:
		logging.error("linux and/or windows destination path should be provided.")
		exit(1)	

	#get list of nodes in the cluster
	try:
		nodes = n.nodes.get_nodes()
	except Exception as e:
		logging.error('cannot get node list')
		exit(1)

	
	response = requests.get(nomadapiurl+'agent/members')
	try:
		if response.ok:
			agentinfo = json.loads(response.content)
			nomadserver = agentinfo['Members'][0]['Addr']
	except Exception as e:
		nomadserver = ''
	if nomadserver == '':
		logging.error("cannot find nomad server ip")
		exit(1)

	#prepare file for upload 
	if not os.path.isdir(uploaddir):
		os.mkdir(uploaddir)

	logging.debug("copy file:"+path+" to path:"+os.path.join(uploaddir,os.path.basename(path)))
	shutil.copyfile(path,os.path.join(uploaddir,os.path.basename(path)))

	url = 'http://'+nomadserver+':'+str(defaulthttpport)+'/upload/'+os.path.basename(path)
	logging.debug("upload url is:"+url)

	#check if web server already started and start if it is not 
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	socketresult = sock.connect_ex((nomadserver,defaulthttpport))
	if socketresult != 0:
		os.system(os.path.join(root,'xcption.py')+" web &")
		time.sleep(5)

	#will keep task status on nodes
	nodestaskstatus = {}
	for node in nodes:
		nodestaskstatus[node['Name']] = 'not started'

	#loading job ginga2 templates 
	templates_dir = ginga2templatedir
	env = Environment(loader=FileSystemLoader(templates_dir) )

	for ostype in ['linux','windows']:
		allcomp = False
		if linuxpath and ostype == 'linux':	
			try:
				job_template = env.get_template('nomad_linux_all_hosts.txt')
			except Exception as e:
				logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_linux_all_hosts.txt'))
				exit(1)	
			
			#command to run on all linux hosts
			cmd = os.path.join(root,'system','xcption_get_file.sh')
			args = '"'+url+'","'+linuxpath+'"'

			#upload job name
			jobname = 'linuxupload'+str(os.getpid())

			ospath = linuxpath

		if windowspath and ostype == 'windows':	
			try:
				job_template = env.get_template('nomad_windows_all_hosts.txt')
			except Exception as e:
				logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_windows_all_hosts.txt'))
				exit(1)	
			
			#command to run on all windows hosts
			cmd = escapestr(winpath+'\\xcption_get_file.ps1')
			args = '"'+url+'","'+escapestr(windowspath)+'"'

			#upload job name
			jobname = 'windowsupload'+str(os.getpid())

			ospath = windowspath

		if (linuxpath and ostype == 'linux') or (windowspath and ostype == 'windows'):
			#creating job hcl file 
			upload_jobfile = os.path.join('/tmp',jobname+'.hcl')	
			logging.debug("creating job file: " + upload_jobfile)				
			with open(upload_jobfile, 'w') as fh:
				fh.write(job_template.render(
					jobname=jobname,
					cmd=cmd,
					args=args
				))			
			#start job and monitor status
			uploadstatus = 'not started'
			if start_nomad_job_from_hcl(upload_jobfile, jobname):
				retrycount = 50
				while retrycount > 0:
					results = check_job_status(jobname,True)
					retrycount -=  1

					#validate all allocation are completed (failed)
					allcomp = True
					for alloc in results['allocations']:
						nodename = ''
						for node in nodes:
							if alloc['NodeID'] == node['ID']: nodename = node['Name']
						if alloc['ClientStatus'] != 'failed' and alloc['ClientStatus'] != 'complete':
							allcomp = False
							logging.info("upload job to node:"+nodename+" still running")
							nodestaskstatus[nodename] = alloc['ClientStatus']
						else:
							#if the job completed validate the exist code, 9998 will be used a a default value if the task not yet completed
							try:
								exitcode = int(alloc['TaskStates'][ostype+'upload']['Events'][3]['Details']['exit_code'])
							except Exception as e:
								exitcode = 9998
							#upload job completed 
							if exitcode == 0 and nodestaskstatus[nodename] != 'succesfull':
								logging.info(path+" successfully uploaded to:"+nodename+":"+ospath)
								nodestaskstatus[nodename] = 'succesfull'
							if exitcode == 1 and nodestaskstatus[nodename] != 'failed':
								logging.info("upload of file:"+ospath+" to node:"+nodename+" failed, validate destination path on the node exists and no communication issues to the node")
								nodestaskstatus[nodename] = 'failed'

					if allcomp: 
						retrycount = 0
					else:
						time.sleep(2)

				if not allcomp:
					logging.info("some of the "+ostype+" upload job did not complete")
			
			#delete job hcl file 
			if os.path.isfile(upload_jobfile):
				logging.debug("delete job hcl file:"+upload_jobfile)
				os.remove(upload_jobfile)
			#delete job if exists 
			logging.debug("delete job:"+jobname)
			response = requests.delete(nomadapiurl+'job/'+jobname+'?purge=true')				
			if not response.ok:
				logging.debug("can't delete job:"+psjobname) 
				
	if os.path.isfile(os.path.join(uploaddir,os.path.basename(path))):
		logging.debug("delete temp upload file:"+os.path.join(uploaddir,os.path.basename(path)))
		os.remove(os.path.join(uploaddir,os.path.basename(path)))	 


#delete syncs from cache exceding the number provided 
def rotate_sync_count_in_cache(maxsyncsperjob):
	if maxsyncsperjob<1: return
	for fileprefix in ['periodic','alloc']:
		cmd = "find "+cachedir+"/job_sync_* -type d | awk '{system(\"find \"$1\"/"+fileprefix+"* -printf "+'\\"%T@ %p\\n\\" | sort -r | tail -n +'+str(maxsyncsperjob+1)+'")}'+"' | awk '{system(\"rm -rf \"$2)}'"
		logging.debug("removing old syncs exceeding "+str(maxsyncsperjob)+" from cache using the cmd:"+cmd)
		filelist = os.system(cmd)

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def monitored_copy(src,dst,nfs4acl):
	xcption_script = os.path.abspath(__file__)

	#validate provided paths are unix based 
	if not re.search("^\S+\:\/\S+", src):
		logging.error("source format is incorrect: " + src) 
		exit(1)	
	if not re.search("^\S+\:\/\S+", dst):
		logging.error("destination format is incorrect: " + src) 
		exit(1)	

	xcption_job = 'monitored_copy_'+str(os.getpid())
	xcption_csv = '/tmp/'+xcption_job+".csv"
	if os.path.isfile(xcption_csv):
		logging.debug("monitored copy csv file already exists, removing:"+xcption_csv)
		os.remove(xcption_csv)

	#running assess to create xcption job csv file
	if nfs4acl:
		xcption_cmd = [xcption_script,'assess','-s',src, '-d',dst,'-l','1','-c',xcption_csv,'-j',xcption_job,'-a','nfs4-acl']
	else:	
		xcption_cmd = [xcption_script,'assess','-s',src, '-d',dst,'-l','1','-c',xcption_csv,'-j',xcption_job]
	if subprocess.call(xcption_cmd,stderr=subprocess.STDOUT):
		logging.error("cannot validate source/destination paths")
		exit(1)		

	xcption_cmd = [xcption_script,'status','-s','*'+src,'-o','json']
	json_status=subprocess.check_output(xcption_cmd)
	statusdict = json.loads(json_status)
	for job in statusdict:
		jobdst = statusdict[job][src]['dst']
		if dst != jobdst:
			logging.error('job for src already exists for diffrent destination, job:'+job+" src:"+src+' dst:'+jobdst)
		else:
			logging.error('job for src already exists, job:'+job+" src:"+src+' dst:'+jobdst)
		logging.error("please use the following command to delete it if not required:"+xcption_script+' delete -f -j '+job+' -s "*'+src+'"')
		exit(1)
			
				
	try:
		#running load to load the created xcption job csv file
		xcption_cmd = [xcption_script,'load','-s',"*"+src, '-c',xcption_csv]
		if subprocess.call(xcption_cmd,stderr=subprocess.STDOUT):
			logging.error("cannot create xcption job")
			assert False 
		#remove csv file 
		os.remove(xcption_csv)

		#running baseline to copy dqtq
		xcption_cmd = [xcption_script,'baseline','-s',src, '-j',xcption_job]
		if subprocess.call(xcption_cmd,stderr=subprocess.STDOUT):
			logging.error("cannot start copy for xcption job")
			assert False
		
		#running status
		cont = True
		counter = 0 
		failed = False
		while cont:
			#update nomad cache
			parse_nomad_jobs_to_files()

			xcption_cmd = [xcption_script,'status','-s',src,'-p','baseline','-j',xcption_job,'-o','json']
			json_status=subprocess.check_output(xcption_cmd)
			statusdict = json.loads(json_status)
			
			status = statusdict[xcption_job][src]['phases'][0]['status']
			status = re.sub('\(.+\)','', status.rstrip())
			scanned = statusdict[xcption_job][src]['phases'][0]['scanned']
			copied = statusdict[xcption_job][src]['phases'][0]['copied']
			sent = statusdict[xcption_job][src]['phases'][0]['sent']
			duration = statusdict[xcption_job][src]['phases'][0]['duration']
			errors = statusdict[xcption_job][src]['phases'][0]['errors']
			nodename = statusdict[xcption_job][src]['phases'][0]['nodename']
			stderrlogpath = statusdict[xcption_job][src]['phases'][0]['stderrlogpath']
			
			if not counter  or counter%10==0:
				print(('-' * 120))
				print(('{:<15s}{:<15s}{:<15s}{:<15s}{:<10s}{:<30s}{:<20s}'.format('status','scanned','copied','errors','duration','sent','nodename')))
				print(('-' * 120))
			
			if status in ['complete','failed','aborted']: 
				cont = False
				print(('-' * 120))
			else:
				time.sleep(5)
			print(('{:<15s}{:<15s}{:<15s}{:<15s}{:<10s}{:<30s}{:<20s}'.format(status,scanned,copied,errors,duration,sent,nodename)))


			if status in ['failed','aborted']: 
				failed = True
				cont = False  
			
			if status == 'pending' and counter > 500:
				logging.error("job is pending too much time please check cluster reesources, aborting")
				failed = True 
				cont = False 

			#in case of errors 
			if errors != '-' and is_number(errors):
				if int(errors) > 0 and not cont:
					failed = True 
			
			if not cont:
				errlogpath, errlogfile = os.path.split(stderrlogpath)
				logfilecopy = os.path.join(logdirpath,errlogfile)
				
				if os.path.isfile(stderrlogpath) and os.path.isdir(logdirpath):
					try:
						shutil.copyfile(stderrlogpath, logfilecopy)
					except:
						logging.error("could not copy log file from:"+stderrlogpath+' to:'+logfilecopy)
						exit(1)
				if failed:
					logging.error("job completed with some errors, please check the log file:"+logfilecopy)
					assert False
				else:
					logging.info("job completed successfuly, please check the log file:"+logfilecopy) 
			counter+=1

		#running delete job to copy dqtq
		xcption_cmd = [xcption_script,'delete','-f','-s',src, '-j',xcption_job]
		subprocess.check_output(xcption_cmd,stderr=subprocess.STDOUT)	
		exit(1)
	except KeyboardInterrupt:
		#in case of canclation job will be delete 
		logging.error("job canceled by user, deleting")
		xcption_cmd = [xcption_script,'delete','-f','-s',src, '-j',xcption_job]
		subprocess.check_output(xcption_cmd,stderr=subprocess.STDOUT)
		exit(1)	
	except Exception as e:
		#in case of error job will be delete 
		logging.debug("deleting job due to error")
		xcption_cmd = [xcption_script,'delete','-f','-s',src, '-j',xcption_job]
		subprocess.check_output(xcption_cmd,stderr=subprocess.STDOUT)	
		exit(1)

#start monitored delete job 
def monitored_delete (src,force):
	#validate provided paths are unix based 
	if not re.search("^\S+\:\/\S+", src):
		logging.error("source format is incorrect: " + src) 
		exit(1)	    

	if not force:
		if not query_yes_no("are you sure you want to delete all data from:"+src,'no'):
			logging.info("delete aborted by user")
			exit(1)

    #check if src can be mounted
	tempmountpointsrc = '/tmp/src_'+str(os.getpid())
	DEVNULL = open(os.devnull, 'wb')
	if os.path.exists(tempmountpointsrc):
        #clearing possiable previous mounts 
		subprocess.call( [ 'umount', tempmountpointsrc ], stdout=DEVNULL, stderr=DEVNULL)
	else:	
		os.mkdir(tempmountpointsrc)
		logging.debug("validating src:"+src+" is mountable")
	
	if subprocess.call( ['mount','-t','nfs','-o','vers=3',src, tempmountpointsrc],stderr=subprocess.STDOUT):
		logging.error("cannot mount src using nfs:" + src)
		exit(1)
	subprocess.call( ['umount',tempmountpointsrc],stderr=subprocess.STDOUT)
	os.rmdir(tempmountpointsrc) 

	logging.debug("starting xcp delete job for src:"+src) 
	xcp_delete_job_name = 'xcpdelete_'+src.replace(':/','-_')
	xcp_delete_job_name = xcp_delete_job_name.replace('/','_')
	xcp_delete_job_name = xcp_delete_job_name.replace(' ','-')
	xcp_delete_job_name = xcp_delete_job_name.replace('\\','_')
	xcp_delete_job_name = xcp_delete_job_name.replace('$','_dollar')	

	xcp_delete_job = getnomadjobdetails(xcp_delete_job_name)
	if xcp_delete_job:
		if not force:
			if not query_yes_no("delete-data job for src:"+src+' already exists, do you want to restart','no'):
				exit(1)
		delete_job_by_prefix(xcp_delete_job_name)
		jobcachedir = os.path.join(cachedir,'job_'+xcp_delete_job_name)
		if os.path.exists(jobcachedir):
			logging.debug("delete cache dir:"+jobcachedir)
			try:
				rmout = shutil.rmtree(jobcachedir) 
			except Exception as e:
				logging.error("could not delete cache dir:"+jobcachedir)


	#loading job ginga2 templates
	templates_dir = ginga2templatedir
	env = Environment(loader=FileSystemLoader(templates_dir) )
	try:
		xcp_delete_template = env.get_template('nomad_delete.txt')
	except Exception as e:
		logging.error("could not find template file: " + os.path.join(templates_dir,'nomad_smartassses.txt'))
		exit(1)
	
	#creating delete job hcl file
	delete_job_file = os.path.join('/tmp',xcp_delete_job_name+'.hcl')	
	logging.debug("creating delete job file:" + delete_job_file)

	defaultprocessor = defaultcpu
	defaultram = defaultmemory
	ostype = 'linux'	
	if ostype == 'linux': xcpbinpath = xcppath
	cmdargs = "delete\",\"-force\",\""+src

	with open(delete_job_file, 'w') as fh:
		fh.write(xcp_delete_template.render(
			dcname=dcname,
			os=ostype,
			delete_job_name=xcp_delete_job_name,
			xcppath=xcpbinpath,
			args=cmdargs,
			memory=defaultram,
			cpu=defaultprocessor
		))

	logging.info("starting delete data for src:"+src)
	if not start_nomad_job_from_hcl(delete_job_file, xcp_delete_job_name):
		logging.error("failed to create nomad job:"+xcp_delete_job_name)
		exit(1)

	response = requests.post(nomadapiurl+'job/'+xcp_delete_job_name+'/periodic/force')	
	if not response.ok:
		logging.error("failed to start delete job:"+xcp_delete_job_name)
		exit(1)

	#monitor delete progress 
	try:
		cont = True
		counter = 0 
		failed = False
		while cont:
			parse_nomad_jobs_to_files()
			jobresults = check_verbose_job_status(xcp_delete_job_name,'xcpdelete')
			jobstatus = jobresults['status']
			jobstderrlogpath = jobresults['stderrlog']
			scanned = "-"
			errors = "-"
			removes = "-"
			rmdirs = '-'
			duration = '-'
			if os.path.isfile(jobstderrlogpath):
				logstats = parse_stats_from_log('file',jobstderrlogpath,'xcpdelete')	
				if 'scanned'  in logstats: scanned = logstats['scanned']
				if 'removes'  in logstats: removes = logstats['removes']
				if 'rmdirs'   in logstats: rmdirs = logstats['rmdirs']
				if 'errors'   in logstats: rmdirs = logstats['errors']
				if 'time'     in logstats: duration = logstats['time']			

			if not counter or counter%10==0:
				print(('-' * 100))
				print(('{:<15s}{:<15s}{:<15s}{:<15s}{:<15s}{:<10s}'.format('status','scanned','file-delete','dir-delete','errors','duration')))
				print(('-' * 100))
			if jobstatus in ['completed','failed','aborted']: 
				cont = False
				print(('-' * 100))				
			else:
				time.sleep(5)
			
			print(('{:<15s}{:<15s}{:<15s}{:<15s}{:<15s}{:<10s}'.format(jobstatus,scanned,removes,rmdirs,errors,duration)))
			
			if jobstatus in ['failed','aborted']: 
				failed = True
				cont = False  
			if jobstatus == 'pending' and counter > 500:
				logging.error("job is pending too much time please check cluster reesources, aborting")
				failed = True 
				cont = False 			
			#in case of errors 
			if errors != '-' and is_number(errors):
				if int(errors) > 0 and not cont:
					failed = True 				
			if not cont:
				errlogpath, errlogfile = os.path.split(jobstderrlogpath)
				logfilecopy = os.path.join(logdirpath,errlogfile)
				if os.path.isfile(jobstderrlogpath) and os.path.isdir(logdirpath):
					try:
						shutil.copyfile(jobstderrlogpath, logfilecopy)
					except:
						logging.error("could not copy log file from:"+jobstderrlogpath+' to:'+logfilecopy)
						exit(1)
				if failed:
					logging.error("job failed or completed with errors, please check the log file:"+logfilecopy)
					assert False
				else:
					#job completed succcessfuly
					delete_job_by_prefix(xcp_delete_job_name)
					jobcachedir = os.path.join(cachedir,'job_'+xcp_delete_job_name)
					if os.path.exists(jobcachedir):
						logging.info("job completed successfuly, please review the log file:"+logfilecopy) 
						logging.debug("delete cache dir:"+jobcachedir)
						try:
							rmout = shutil.rmtree(jobcachedir) 
						except Exception as e:
							logging.error("could not delete cache dir:"+jobcachedir)					
					
			counter+=1

	except KeyboardInterrupt:
		#if cancled by user
		delete_job_by_prefix(xcp_delete_job_name)
		jobcachedir = os.path.join(cachedir,'job_'+xcp_delete_job_name)
		if os.path.exists(jobcachedir):
			logging.debug("delete cache dir:"+jobcachedir)
			try:
				rmout = shutil.rmtree(jobcachedir) 
			except Exception as e:
				logging.error("could not delete cache dir:"+jobcachedir)
		logging.error("delete job canceled by user")
		exit(1)	
	# except Exception as e:
	# 	#in case of error job will be delete 
	# 	delete_job_by_prefix(xcp_delete_job_name)
	# 	jobcachedir = os.path.join(cachedir,'job_'+xcp_delete_job_name)
	# 	if os.path.exists(jobcachedir):
	# 		logging.debug("delete cache dir:"+jobcachedir)
	# 		try:
	# 			rmout = shutil.rmtree(jobcachedir) 
	# 		except Exception as e:
	# 			logging.error("could not delete cache dir:"+jobcachedir)
	# 	logging.error("delete job canceled due to an error")#
	# 	exit(1)
	

		
		



#####################################################################################################
###################                        MAIN                                        ##############
#####################################################################################################

if not os.path.isdir(cachedir):
	try:
		os.mkdir(cachedir)
	except Exception as e:
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

if args.version: print(("XCPtion version:"+version))

#check nomad avaialbility
check_nomad()

if args.subparser_name == 'nodestatus':
	nomadstatus()
	exit(0)

if args.subparser_name == 'nomad':
	parse_nomad_jobs_to_files()
	rotate_sync_count_in_cache(maxsyncsperjob)
	exit (0)

if args.subparser_name == 'assess':
	if args.cron: 
		try:
			now = datetime.datetime.now()
			cront = croniter.croniter(args.cron, now)
		except Exception as e:
			logging.error('cron format: "'+args.cron+ '" is incorrect')
			exit(1)	
		defaultjobcron = args.cron
					
	if not re.search(r'^(\\\\?([^\\/]*[\\/])*)([^\\/]+)$', args.source):
		if args.acl and not args.acl == 'nfs4-acl':
			logging.error('invalid acl copy option')
			exit(1)
		assess_fs_linux(args.csvfile,args.source,args.destination,args.depth,args.acl,jobfilter)
	else:
		if args.acl and not args.acl == 'no-win-acl':
			logging.error('invalid acl copy option')
			exit(1)		
		assess_fs_windows(args.csvfile,args.source,args.destination,args.depth,jobfilter)

if args.subparser_name == 'copy-data':
	monitored_copy(args.source,args.destination,args.nfs4acl)

if args.subparser_name == 'delete-data':
	monitored_delete(args.source,args.force)

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

if args.subparser_name == 'status':
	#False is passed to skip log parsing and make it faster
	parse_nomad_jobs_to_files(False)
	if not args.verbose:
		create_status('general',args.logs,args.output)
	else:
		create_status('verbose',args.logs,args.output)

if args.subparser_name in ['pause','resume','syncnow']:
	update_nomad_job_status(args.subparser_name)

if args.subparser_name == 'delete':
	delete_jobs(args.force)

if args.subparser_name == 'abort':
	abort_jobs(args.type, args.force)

if args.subparser_name == 'modify':
	if not args.tojob  and not args.cpu and not args.ram and not args.cron:
		logging.error("please provide one or more properties to modify")		
		exit(1)
	if args.cron:
		try:
			now = datetime.datetime.now()
			cront = croniter.croniter(args.cron, now)
		except Exception as e:
			logging.error('cron format: "'+args.cron+ '" is incorrect')
			exit(1)	

	modify_tasks(args,args.force)
	#create_nomad_jobs()
	parse_nomad_jobs_to_files()

if args.subparser_name == 'export':	
	parse_nomad_jobs_to_files()
	export_csv(args.csvfile)

if args.subparser_name == 'web':	
	start_flask(args.port)

if args.subparser_name == 'fileupload':
	upload_file(args.file,args.linuxpath,args.windowspath)

if args.subparser_name == 'smartassess':
	if not args.smartassess_command:
		parser_smartassess.print_help()

	load_smartassess_jobs_from_json(smartassessjobdictjson)

	if args.smartassess_command == 'start':
		smartassess_fs_linux_start(args.source,args.depth,args.locate_cross_task_hardlink)

	if args.smartassess_command in ['status','createcsv']:
		if args.min_capacity:
			matchObj = re.match("^(\d+)(\s*)((K|M|G|T)(i)?B)$",args.min_capacity)
			if matchObj.group(4) == 'K': minsizekfortask_minborder=int(matchObj.group(1))
			if matchObj.group(4) == 'M': minsizekfortask_minborder=int(matchObj.group(1))*1024
			if matchObj.group(4) == 'G': minsizekfortask_minborder=int(matchObj.group(1))*1024*1024
			if matchObj.group(4) == 'T': minsizekfortask_minborder=int(matchObj.group(1))*1024*1024*1024		
		minsizekforjob = minsizekfortask_minborder + 100000

		if args.min_inodes:
			mininodespertask_minborder = args.min_inodes
		mininodespertask = mininodespertask_minborder + 200000
		parse_nomad_jobs_to_files()

	if args.smartassess_command == 'status':
		smartassess_fs_linux_status_createcsv(args,False)

	if args.smartassess_command == 'createcsv':
		smartassess_fs_linux_status_createcsv(args,True)

	if args.smartassess_command == 'delete':	
		smartassess_fs_linux_delete(args.force)
