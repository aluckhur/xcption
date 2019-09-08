#!/usr/bin/python
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

from hurry.filesize import size
from prettytable import PrettyTable
from jinja2 import Environment, FileSystemLoader

pp = pprint.PrettyPrinter(indent=1)

#general settings
dcname = 'DC1'

#default windows tool
defaultwintool = 'xcp'
#xcp path location
xcppath = '/usr/local/bin/xcp'
#xcp windows location
xcpwinpath = 'C:\\NetApp\\XCP\\xcp.exe'

#robocopy windows location
robocopywinpath = 'C:\\NetApp\\XCP\\robocopy_wrapper.cmd'
robocopyargs = ' /COPYALL /MIR /NP /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE'

#location of the script 
root = os.path.dirname(os.path.abspath(__file__))

#xcp repo and cache dir loaction 
xcprepopath = os.path.join(root,'system','xcp_repo')

#xcp indexes path 
xcpindexespath = os.path.join(xcprepopath,'catalog','indexes')

#cache dir for current state 
#cachedir = os.path.join(xcprepopath,'nomadcache')
cachedir = os.path.join(root,'nomadcache')

#file containing loaded jobs 
jobdictjson = os.path.join(cachedir,'jobs.json')
#path to nomad bin 
nomadpath = '/usr/local/bin/nomad'

#location for the jobs dir
jobsdir = os.path.join(xcprepopath,'jobs') 

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
defaultcpu = 3000
defaultmemory = 800


parser = argparse.ArgumentParser()

#parser.add_argument('-c','--csvfile', help="input CSV file with the following columns: Job Name,SRC Path,DST Path,Schedule,CPU,Memory",required=True,type=str)
parser.add_argument('-d','--debug',   help="log debug messages to console", action='store_true')


subparser = parser.add_subparsers(dest='subparser_name', help='sub commands that can be used')

# create the sub commands 
parser_nodestatus   = subparser.add_parser('nodestatus',   help='display cluster nodes status')	
parser_status       = subparser.add_parser('status',   help='display status')	
parser_asses        = subparser.add_parser('asses',    help='asses fielsystem and create csv file')
parser_load         = subparser.add_parser('load',     help='load/update configuration from csv file')
parser_baseline     = subparser.add_parser('baseline', help='start baseline (xcp copy)')
parser_sync         = subparser.add_parser('sync',     help='start schedule updates (xcp sync)')
parser_syncnow      = subparser.add_parser('syncnow',  help='initiate sync now')
parser_pause        = subparser.add_parser('pause',    help='disable sync schedule')
parser_resume       = subparser.add_parser('resume',   help='resume sync schedule')
parser_verify       = subparser.add_parser('verify',   help='start verify to validate consistency between source and destination (xcp verify)')
parser_delete       = subparser.add_parser('delete',   help='delete existing config')
parser_nomad        = subparser.add_parser('nomad',    description='hidden command, usded to backup nomad jobs into files')

parser_status.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_status.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_status.add_argument('-v','--verbose',help="provide detailed information", required=False,action='store_true')
parser_status.add_argument('-p','--phase',help="change the scope of the command to specific phase (baseline,sync#,verify#)", required=False,type=str,metavar='phase')
parser_status.add_argument('-l','--logs',help="display xcp logs", required=False,action='store_true')

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

parser_sync.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_sync.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_syncnow.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_syncnow.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_pause.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_pause.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_resume.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_resume.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')

parser_verify.add_argument('-j','--job',help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_verify.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')


parser_delete.add_argument('-j','--job', help="change the scope of the command to specific job", required=False,type=str,metavar='jobname')
parser_delete.add_argument('-s','--source',help="change the scope of the command to specific path", required=False,type=str,metavar='srcpath')
parser_delete.add_argument('-f','--force',help="force delete", required=False,action='store_true')

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

				if (jobfilter == '' or jobfilter == jobname) and (srcfilter == '' or srcfilter in src):
	
					cron    = ''
					if 3 < len(row): cron    = row[3] 
					if cron == '':   cron    = defaultjobcron 


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
					
					logging.debug("parsing entry for job:" + jobname	 + " src:" + src + " dst:" + dst + " ostype:" + ostype + " tool:"+tool+" failbackuser:"+failbackuser+" failback group:"+failbackgroup) 

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

						logging.info("validating src:" + src + " and dst:" + dst+ " cifs paths are avaialble from one of the windows server") 
						
						pscmd = 'if (test-path '+src+') {exit 0} else {exit 1}'
						psstatus = run_powershell_cmd_on_windows_agent(pscmd)['status']
						if  psstatus != 'complete':
							logging.error("cannot validate src:"+src+" using cifs, validation is:"+psstatus)
							exit(1)								
						
						pscmd = 'if (test-path '+dst+') {exit 0} else {exit 1}'
						psstatus = run_powershell_cmd_on_windows_agent(pscmd)['status']

						if  psstatus != 'complete':
							logging.error("cannot validate dst:"+dst+" using cifs, validation status is:"+psstatus)
							exit(1)	
							
						srchost = src.split('\\')[2]
						srcpath = src.replace('\\\\'+srchost,'')
						dsthost = dst.split('\\')[2]
						dstpath = dst.replace('\\\\'+dsthost,'')
						
					#validate no duplicate src and destination 
					if not jobname in jobsdict:
						jobsdict[jobname]={}
					if src in jobsdict[jobname] and dst != jobsdict[jobname][src]['dst']:
						logging.error("cannot load diffrent dst to existing src:" + src+"->"+dst)
						exit(1)
					if dst in dstdict:
						logging.error("duplicate dst path: " + dst)
						exit(1)
							
					
					baseline_job_name = 'baseline_'+jobname+'_'+srcbase
					sync_job_name     = 'sync_'+jobname+'_'+srcbase
					verify_job_name     = 'verify_'+jobname+'_'+srcbase
					
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
		retrycount = 20
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
				if srcfilter == '' or srcfilter in src:
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

					if ostype == 'linux': xcpbinpath = xcppath
					if ostype == 'windows': xcpbinpath = 'powershell'
					
					#creating baseline job 
					baseline_job_file = os.path.join(jobdir,baseline_job_name+'.hcl')	
					logging.info("creating/updating relationship configs for src:"+src)
					logging.debug("creating baseline job file: " + baseline_job_file)				
					
					if ostype == 'linux':  cmdargs = "copy\",\"-newid\",\""+xcpindexname+"\",\""+src+"\",\""+dst
					if ostype == 'windows' and tool == 'xcp': 
						cmdargs = escapestr(xcpwinpath+" copy -preserve-atime -acl -fallback-user "+failbackuser+" -fallback-group "+failbackgroup+" \""+src+"\" \""+dst+"\"")
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
					
					if ostype == 'linux':  cmdargs = "sync\",\"-id\",\""+xcpindexname
					if ostype == 'windows' and tool == 'xcp': 
						cmdargs = escapestr(xcpwinpath+" sync -preserve-atime -acl -fallback-user "+failbackuser+" -fallback-group "+failbackgroup+" \""+src+"\" \""+dst+"\"")
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
					
					if ostype == 'linux':  cmdargs = "verify\",\"-v\",\"-noid\",\"-nodata\",\""+src+"\",\""+dst
					if ostype == 'windows': cmdargs = escapestr(xcpwinpath+" verify -v -l -preserve-atime "+src+" "+dst)								
					
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
				if srcfilter == '' or srcfilter in src:
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
							logging.warning("log file"+jobfile+" for job:"+nomadjobname+" could not be found, please load first") 
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
								if baselinestatus != 'Baseline Is Complete':
									logging.warning(action+" will be paused:"+baselinestatus.lower())									
									nomadjobdict["Job"]["Stop"] = True
								else:
									logging.debug("baseline is completed, can start "+action)

							#if sync job and baseline was not started disable schedule for sync 
							if action == 'verify' or action == 'verify':
								if baselinestatus != 'Baseline Is Complete':
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
							if action == 'baseline' or (action == 'verify' and baselinestatus == 'Baseline Is Complete'):
								response = requests.post(nomadapiurl+'job/'+nomadjobname+'/periodic/force')	
								if not response.ok:
									logging.error("job:"+nomadjobname+" force start failed") 
									exit(1)
					elif action == 'baseline' and job:
						logging.warning("baseline job already exists and cannot be updated") 


#parse stats from xcp logs, logs can be retrived from api or file in the repo
def parse_stats_from_log (type,name,logtype,task='none'):
#def parse_stats_from_log (type,name,task='none',jobstatus='unknow'):
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
					#lastline = lines[-1]
					results['content'] = content
		except:
			logging.error("cannot read log file:"+logfilepath)	

#future optimization for status 
#		logjsonfile = re.sub('\.log$', '.json', logfilepath)
#		if jobstatus == 'complete' and os.path.isfile(logjsonfile):
#			logging.debug("reading data from json file:"+logjsonfile)								
#			try:
#				with open(logjsonfile, 'r') as f:
#					results = json.load(f)
#    				return results
#			except:
#				logging.debug("reading data from json file:"+logjsonfile+" failed")								


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

		#for robocopy logs 
		matchObj = re.search("Robust File Copy for Windows", results['content'], re.M|re.I)
		if matchObj: 
			matchObj = re.search("Times\s+\:\s+(\d+)\:(\d+)\:(\d+)", results['content'], re.M|re.I)
			if matchObj:
				results['time'] = '';
				if int( matchObj.group(1)) > 0: results['time'] += matchObj.group(1)+"h"
				if int( matchObj.group(2)) > 0: results['time'] += matchObj.group(2)+"m"
				results['time'] += matchObj.group(3)+"s"

			matchObj = re.search("Files\s+\:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", results['content'], re.M|re.I)
			if matchObj:
				results['scanned'] = int(matchObj.group(1))
				results['copied'] = int(matchObj.group(2))
				results['errors'] = int(matchObj.group(5))

			matchObj = re.search(r"Bytes\s+\:\s+(\d+([\,]\d+)*([\.]\d+)?)\s+([g|m|k|t])?", results['content'], re.M|re.I)
			if matchObj:
				results['bwout'] = str(round(float(matchObj.group(1)),2))
				quantifier = ''
				if not matchObj.group(4): quantifier= ' B'
				elif matchObj.group(4) == 'k': quantifier= ' KiB'
				elif matchObj.group(4) == 'm': quantifier= ' MiB'
				elif matchObj.group(4) == 'g': quantifier= ' GiB'
				elif matchObj.group(4) == 't': quantifier= ' TiB'
				results['bwout'] += quantifier

			matchObj = re.search("Files\s+\:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", results['content'], re.M|re.I)
			if matchObj:
				results['scanned'] += int(matchObj.group(1))				
				results['copied'] += int(matchObj.group(2))				
				results['errors'] = int(matchObj.group(5))

			matchObj = re.search("Times \:\s+(\d+)\:(\d+)\:(\d+)", results['content'], re.M|re.I)	

			return results
			#results['scanned'] = matchObj.group(1)		

		# for xcp logs
		matchObj = re.finditer("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S? [scanned|reviewed].+)$",results['content'],re.M|re.I)
		if matchObj:
			for matchNum, match in enumerate(matchObj, start=1):
				lastline = match.group()
			results['lastline'] = lastline

	#for xcp logs 	
	if lastline:
		matchObj = re.search("\s+(\S*\d+[s|m])(\.)?$", lastline, re.M|re.I)
		if matchObj: 
			results['time'] = matchObj.group(1)
				#reviewed in xcp linux, compared xcp windows
                matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) [reviewed|compared]", lastline, re.M|re.I)
                if matchObj:
                        results['reviewed'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) scanned", lastline, re.M|re.I)
		if matchObj: 
			results['scanned'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) copied", lastline, re.M|re.I)
		if matchObj: 
			results['copied'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) indexed", lastline, re.M|re.I)
		if matchObj: 
			results['indexed'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) gone", lastline, re.M|re.I)
		if matchObj: 
			results['gone'] = matchObj.group(1)	
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) modification", lastline, re.M|re.I)
		if matchObj: 
			results['modification'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) error", lastline, re.M|re.I)
		if matchObj: 
			results['errors'] = matchObj.group(1)

		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) file.gone", lastline, re.M|re.I)
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
		matchObj = re.search("(\d+\%?) found \((\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) have data\)", lastline, re.M|re.I)
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

		matchObj = re.search("(\d+) different attr", lastline, re.M|re.I)
		if matchObj:
			results['diffattr'] = matchObj.group(1)

		matchObj = re.search("(\d+) different mod time", lastline, re.M|re.I)
		if matchObj:
			results['diffmodtime'] = matchObj.group(1)

		#xcp verify for windows 
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) compared", lastline, re.M|re.I)
		if matchObj:
			results['scanned'] = matchObj.group(1)
		matchObj = re.search("(\d*\.?\d+|\d{1,3}(,\d{3})*(\.\d+)?\S?) same", lastline, re.M|re.I)
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
				if srcfilter == '' or srcfilter in src:
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
								if 'time' in statsresults.keys(): 
									synctime = statsresults['time']
								if 'bwout' in statsresults.keys(): 
									syncsent = statsresults['bwout']								
								if not syncjobsstructure.has_key('logs'):
									syncjobsstructure['logs'] = {}
								syncjobsstructure['logs'][logallocid] = {}										
								syncjobsstructure['logs'][logallocid] = statsresults

					if not syncjobfound: syncsched = '-'
			
					if alloclastdetails: 
						logging.debug("sync job name:"+sync_job_name+" lastjobid:"+joblastdetails['ID']+' allocjobid:'+alloclastdetails['ID'])

						synclogcachefile = os.path.join(synccachedir,logtype+'log_'+alloclastdetails['ID']+'.log')
						statsresults = parse_stats_from_log('file',synclogcachefile,logtype)
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
						try:
							#linux
							if verifystatus == 'failed' and (verifystatsresults['found'] != verifystatsresults['scanned']): verifystatus =  'diff'
							#windows
							if ostype == 'windows' and (verifystatsresults['found'] != verifystatsresults['scanned']): verifystatus =  'diff'

							if verifystatus == 'complete': verifystatus = 'idle'
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
							except:
								baselinestatus = '-'
							if baselinestatus == 'running': endtime = '-' 



							if not phasefilter or task.startswith(phasefilter):
				 				verbosetable.add_row([task,starttime,endtime,duration,scanned,reviewed,copied,modified,deleted,errors,sent,nodename,baselinestatus])
				 				if displaylogs:
									verbosetable.border = False
									verbosetable.align = 'l'
									print verbosetable
									print ""
									try:
										print baselinestatsresults['content']
									except:										
										print "log is not avaialble"
									print ""
									print ""
									verbosetable = PrettyTable()
									verbosetable.field_names = ['Phase','Start Time','End Time','Duration','Scanned','Reviewed','Copied','Modified','Deleted','Errors','Data Sent','Node','Status']

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

					 	#for each periodic 					 	synccounter = 1
					 	verifycounter = 1
					 	if 'periodics' in jobstructure.keys():
						 	for periodic in sorted(jobstructure['periodics'].keys()):
						 		currentperiodic = jobstructure['periodics'][periodic]
						 		for allocid in jobstructure['allocs']:
						 			if jobstructure['allocs'][allocid]['JobID'] == periodic:
						 				currentalloc = jobstructure['allocs'][allocid]
						 				currentlog = {}
						 				if allocid in jobstructure['logs'].keys():
						 					currentlog = jobstructure['logs'][allocid]

						 				tasktype = ''
						 				if periodic.startswith('sync'):   
						 					task = 'sync' + str(synccounter)
						 					tasktype = 'sync'
						 					synccounter+=1
						 				if periodic.startswith('verify'): 
						 					task = 'verify'+str(verifycounter)
						 					verifycounter+=1
						 					tasktype = 'verify'

						 				

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
												if jobstatus == 'complete': jobstatus = 'idle'
												#windows

												if ostype == 'windows' and (currentlog['found'] != currentlog['scanned']): jobstatus =  'diff'

												if jobstatus == 'idle' and (currentlog['found'] == currentlog['scanned']): jobstatus =  'equal'										
										except:
											jobstatus = '-'


										if jobstatus == 'running':
											endtime = '-' 
										
										if not phasefilter or task.startswith(phasefilter):
						 					verbosetable.add_row([task,starttime,endtime,duration,scanned,reviewed,copied,modified,deleted,errors,sent,nodename,jobstatus])
							 				if displaylogs:
												verbosetable.border = False
												verbosetable.align = 'l'
												print verbosetable.get_string(sortby="Start Time")
												print ""
												try:
													print currentlog['content']
												except:
													print "log is not avaialble"
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
				if srcfilter == '' or srcfilter in src:
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
							if baselinestatus != 'Baseline Is Complete':
								logging.warning("cannot syncnow since baseline status for:"+nomadjobname+' is:'+baselinestatus)
							else:
								logging.info("starting sync src:"+src+" dst:"+dst) 
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
				if srcfilter == '' or srcfilter in src:
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
		table.field_names = ["Name","IP","Status","OS","Reserved/Total CPU MHz","Reserved/Total RAM MB","# Running Jobs"]		
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
				ostype = nodedetails['Attributes']['os.name']
				ip = nodedetails['Attributes']['unique.network.ip-address']
				totalcpu = nodedetails['Resources']['CPU']
				totalram = nodedetails['Resources']['MemoryMB']

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
			table.add_row([name,ip,status,ostype,cpuinfo,raminfo,alloccounter])
		
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

		if not (job['ID'].startswith('baseline') or job['ID'].startswith('sync') or job['ID'].startswith('verify')):
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
		
		if len(job['ID'].split('/')) > 1:
			jobjsonfile = os.path.join(jobdir,job['ID'].split('/')[1])

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

				#get stderr logs
				logtype = '&type=stderr'
				#try to get the log file using api
				response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+logtype+'&plain=true')
				if response.ok and re.search("\d", response.content, re.M|re.I):
					logging.debug("stderr log for job:"+alloc['ID']+" is avaialble using api")
					alloclogfile = os.path.join(jobdir,'stderrlog_'+alloc['ID']+'.log')
					try:
						with open(alloclogfile, 'w') as fp:
							fp.write(response.content)
							logging.debug("dumping log to log file:"+alloclogfile)		
					except:
						logging.error("cannot create file:"+alloclogfile)
						exit(1)

				#get stderr logs
				logtype = '&type=stdout'
				#try to get the log file using api
				response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+logtype+'&plain=true')
				if response.ok and re.search("\d", response.content, re.M|re.I):
					logging.debug("stdout log for job:"+alloc['ID']+" is avaialble using api")
					alloclogfile = os.path.join(jobdir,'stdoutlog_'+alloc['ID']+'.log')
					try:
						with open(alloclogfile, 'w') as fp:
							fp.write(response.content)
							logging.debug("dumping log to log file:"+alloclogfile)		
					except:
						logging.error("cannot create file:"+alloclogfile)
						exit(1)						

				if alloc['TaskGroup'].startswith('verify'): 
					#get stderr logs for verify
					logtype = '&type=stdout'						
					#try to get the log file using api
					response = requests.get(nomadapiurl+'client/fs/logs/'+alloc['ID']+'?task='+task+logtype+'&plain=true')
					if response.ok and re.search("\d", response.content, re.M|re.I):
						logging.debug("log for job:"+alloc['ID']+" is avaialble using api")
						alloclogfile = os.path.join(jobdir,'log_'+alloc['ID']+'.log')
						try:
							with open(alloclogfile, 'a+') as fp:
								fp.write(response.content)
								logging.debug("appending log to log file:"+alloclogfile)		
						except:
							logging.error("cannot create file:"+alloclogfile)
							exit(1)

				logging.debug("caching alloc:"+alloc['ID'])

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

#assesment of filesystem and creation of csv file out of it 
def asses_fs_linux(csvfile,src,dst,depth,jobname):
	logging.debug("trying to asses src:" + src + " dst:" + dst) 

	if not re.search("\S+\:\/\S+", src):
		logging.error("source format is incorrect: " + src) 
		exit(1)	
	if not re.search("\S+\:\/\S+", dst):
		logging.error("destination format is incorrect: " + dst)
		exit(1)	

	if args.cpu: 
		defaultcpu = args.cpu 
		if defaultcpu < 0 or defaultcpu > 20000:
			logging.error("cpu allocation is illegal:"+defaultcpu)
			exit(1)	
	if args.ram: 
		defaultmemory = args.ram
		if defaultmemory < 0 or defaultmemory > 20000:
			logging.error("cpu allocation is illegal:"+defaultmemory)
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
				logging.debug("src path: "+nfssrcpath+" and dst path: "+nfsdstpath+ " will be configured as xcp job")
				#append data to csv 
				csv_data.append({"#JOB NAME":jobname,"SOURCE PATH":nfssrcpath,"DEST PATH":nfsdstpath,"SYNC SCHED":defaultjobcron,"CPU MHz":defaultcpu,"RAM MB":defaultmemory})


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

	pscmd = xcpwinpath+' scan -l -depth '+str(depth)+' '+startpath
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


			matchObj = re.search(r"(.+)\\.*$", path, re.M|re.I)
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

	if args.cpu: 
		defaultcpu = args.cpu 
		if defaultcpu < 0 or defaultcpu > 20000:
			logging.error("cpu allocation is illegal:"+defaultcpu)
			exit(1)	
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
	pscmd = 'if (test-path '+src+') {exit 0} else {exit 1}'
	psstatus = run_powershell_cmd_on_windows_agent(pscmd)['status']
	if  psstatus != 'complete':
		logging.error("cannot validate src:"+src+" using cifs, validation is:"+psstatus)
		exit(1)								
	pscmd = 'if (test-path '+dst+') {exit 0} else {exit 1}'
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

	srcdirstructure = list_dirs_windows(src,depth)
	dstdirstructure = list_dirs_windows(dst,depth+1)

	excludedir = ''

	for path in srcdirstructure:
		currentdepth = len(path.split("\\"))-1
		#print path, currentdepth

		dircount = srcdirstructure[path]['dircount']
		filecount = srcdirstructure[path]['filecount']

		srcpath = src+path.replace('.','',1)
		dstpath = dst+path.replace('.','',1)

		if filecount > 0 and currentdepth < depth and dircount > 0:
			logging.warning("source path: "+srcpath+" contains "+str(filecount)+" files. those files will not be included in the xcption jobs and need to be copied externaly")

			warning=True 
		else:
			if path in dstdirstructure.keys():
				if (dstdirstructure[path]['filecount']  > 0 or dstdirstructure[path]['dircount'] >0) and ((currentdepth < depth and dstdirstructure[path]['dircount'] == 0)
						or (currentdepth == depth and (dstdirstructure[path]['dircount'] > 0 or dstdirstructure[path]['filecount'] >0))):
					logging.error("destination path: "+dstpath+ " for source dir: "+srcpath+" exists and contains files")
					exit(1)
				else:
					logging.info("destination path: "+dstpath+ " for source dir: "+srcpath+" exists but empty")

		#check if destination have tomuch directories 
		if dircount > 20:
			logging.warning("the amount of directories under: "+dstpath+" is above 20, this will create extensive amount of xcption jobs")
			warning=True  

		#create xcption job entry
		
		if (currentdepth < depth and dircount == 0) or (currentdepth == depth and currentdepth > 0) or (depth == 0):
			logging.debug("src path: "+srcpath+" and dst path: "+dstpath+ "will be configured as xcp job")

			#append data to csv 
			csv_data.append({"#JOB NAME":jobname,"SOURCE PATH":srcpath,"DEST PATH":dstpath,"SYNC SCHED":defaultjobcron,"CPU MHz":defaultcpu,"RAM MB":defaultmemory,"TOOL":tool,"FAILBACKUSER":failbackuser,"FAILBACKGROUP":failbackgroup})

			#exlude copy of files in this dir 
			if currentdepth < depth:
				if excludedir == '': excludedir = " /XD "
				excludedir += "\""+srcpath+"\" "

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
			exit(1)	

		if depth > 0:
			depthxcpcopy = ''

			pscmd1 = robocopywinpath+robocopyargs+" /LEV:"+str(depth+1)+" \""+src+"\" \""+dst+"\" /XF *"
			pscmd2 = robocopywinpath+robocopyargs+" /LEV:"+str(depth)+" \""+src+"\" \""+dst+"\""+excludedir

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
	start_nomad_jobs('baseline')

if args.subparser_name == 'sync':
	start_nomad_jobs('sync')

if args.subparser_name == 'verify':
	start_nomad_jobs('verify')

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
