#!/usr/bin/python3
import requests
import json 
import pprint
import argparse
import sys,os
import logging

#location of xcption root dir  
root = os.path.dirname(os.path.abspath(__file__))+'/..'

#cloudsync api keys repo 
cloudsyncrepo = os.path.join(root,'system','xcp_repo','cloudsync')
cloudsyncapikeysfile = os.path.join(cloudsyncrepo,'accounts')

#cloudsync api edpoint 
endpoint = 'https://api.cloudsync.netapp.com/api/'

#dictionary for api accounts
apiaccounts = {}

parent_parser = argparse.ArgumentParser(add_help=False)
parser = argparse.ArgumentParser()

parser.add_argument('-d','--debug',   help="log debug messages to console", action='store_true')
subparser = parser.add_subparsers(dest='subparser_name', help='sub commands that can be used')

# create the sub commands 
parser_baseline     = subparser.add_parser('baseline',   help='start baseline of relationships',parents=[parent_parser])

parser_baseline.add_argument('-u','--user',help="cloud central user (api key to be referenced in:"+cloudsyncapikeysfile+')',required=True,type=str)
parser_baseline.add_argument('-a','--account',help="cloud acount account name",required=True,type=str)
parser_baseline.add_argument('-b','--broker',help="cloud sync broker name",required=True,type=str)
parser_baseline.add_argument('-s','--source',help="source path",required=True,type=str)
parser_baseline.add_argument('-d','--destination',help="destination path",required=True,type=str)
parser_baseline.add_argument('-f','--force',help="force re-baseline", required=False,action='store_true')

args = parser.parse_args(args=None if sys.argv[1:] else ['--help'])

#initialize logging 
log = logging.getLogger()
log.setLevel(logging.DEBUG)
logging.getLogger('requests').setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
formatterdebug = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')

# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
if args.debug: ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
log.addHandler(ch)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)

pp = pprint.PrettyPrinter(indent=1)

def parseapifile():
    try:
        logging.debug("loading api refrence file:"+cloudsyncapikeysfile)
        f = open(cloudsyncapikeysfile, 'r')
        lines = f.readlines()
        for line in lines:
            account,apikey = line.split(':')
            apiaccounts[account] = apikey.rstrip()
    except Exception as e:
        logging.error("could not load api refrence file:"+cloudsyncapikeysfile)
        exit(1)

def cloudsyncapicall(user,api,methd='GET',requestheaders={},body={}):
    if not user in apiaccounts:
        logging.error("api key for user:"+user+" could not be found in:"+cloudsyncapikeysfile)
        exit(1)    
    authkey = apiaccounts[user]
    headers = {'authorization': 'Bearer '+authkey,'accept': 'application/json'}
    for requestheader in requestheaders.keys():
        headers[requestheader] =  requestheaders[requestheader]

    out = {}
    out['response'] = requests.get(endpoint+api, headers=headers)

    if out['response'].ok:
        out['body'] = json.loads(out['response'].content)
    else:
        logging.error("api call failed")
    return out

#parse path 
def parsepath(path):
    if path.startswith('\\\\'):
        type = 'cifs'
    elif path.__contains__(':/'):
        type = 'nfs'
    else:
        logging.error('path:'+path+' is in unsupported format')
        exit(1)
    
    if type == 'nfs':
        nfsserver,fullpath=path.split(':')
        dirs = fullpath.split('/')
        export = dirs[1]
        del dirs[1]
        deeppath =''
        if len(dirs) > 2:
            deeppath = '/'.join(dirs)
        res = {'type':type,'path':path,'server':nfsserver,'fullpath':fullpath,'export':export,'deeppath':deeppath}
    if type == 'cifs':
        dirs = path.split('\\')
        if len(dirs) < 4:
            logging.error('cifs path:'+path+' is in unsupported format')
            exit(1)
        server = dirs[2]
        share = dirs[3]
        deeppath = ''
        if len(dirs) > 4:
            del dirs[2:4]
            del dirs[1]
            deeppath = '\\'.join(dirs)
        res = {'type':type,'path':path,'server':server,'share':share,'deeppath':deeppath}    
    
    return(res)


#get relationship data
def getcloudsyncrelationship (user,account,broker,src,dst):
    #validate src 
    srcdetails = parsepath(src)
    #validate dst 
    dstdetails = parsepath(dst)

    #validate broker
    brokers = cloudsyncapicall(user,'data-brokers')['body']
    found = False
    for brk in brokers:
        if brk['name'] == broker:
            brokerinfo = brk
            found = True
    if not found:
        logging.error("broker:"+broker+" is not availble for user:"+user)
        exit(1)
    try:
        logging.debug("broker:"+broker+' type:'+brokerinfo['type'].lower()+' hostname:'+brokerinfo['placement']['hostname']+'('+brokerinfo['placement']['privateIp']+')')
    except Exception as e:
        logging.error("broker:"+broker+' metadata is not complete')
        exit(1)

    #validate accounts
    accounts = cloudsyncapicall(user,'accounts')['body']
    found = False
    for acc in accounts:
        if acc['name'] == account:
            accountid = acc['accountId']
            accinfo = cloudsyncapicall(user,'accounts/info?noCreate=true','GET',{'x-account-id':accountid})['body']           
            found = True
    if not found:
        logging.error("account:"+account+" is not availble for user:"+user)
        exit(1)
    try:
        logging.debug("account:"+account+' type:'+accinfo['subscriptionType'].lower())
    except Exception as e:
        logging.debug("account:"+account+' metadata is not complete')
        exit(1)

    #get relationship info 
    rels = cloudsyncapicall(user,'relationships-v2','GET',{'x-account-id':accountid})['body']           
    
    for rel in rels:
        found = True
        if not srcdetails['type'] in rel['source']:
            found = False
        if srcdetails['type'] == 'nfs':
            if rel['source']['nfs']['host'] != srcdetails['server']:
                found = False
                
            elif rel['source']['nfs']['export'] != '/'+srcdetails['export']:
                found = False
                
            elif rel['source']['nfs']['path'] != srcdetails['deeppath']:
                found = False
                
        if not dstdetails['type'] in rel['target']:
            found = False
        if dstdetails['type'] == 'nfs':
            if rel['target']['nfs']['host'] != dstdetails['server']:
                found = False
                
            elif rel['target']['nfs']['export'] != '/'+dstdetails['export']:
                found = False
                
            elif rel['target']['nfs']['path'] != dstdetails['deeppath']:
                found = False   
                print('aa'+rel['target']['nfs']['path']+'aa')     

        if found: 
            logging.debug('existing cloudsync relationship from src:'+src+' to dst:'+dst+' was found')
            return(rel)

        logging.debug('existing cloudsync relationship from src:'+src+' to dst:'+dst+' could not be found')
        return({})


def  baseline_relation (user,account,broker,src,dst,force=False):
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst)
    if relinfo and not force:
        logging.error('cloudsync relationship from src:'+src+' to dst:'+dst+'already exists. use --force to force new baseline') 
        exit(1)
    elif relinfo and force:
        logging.info('using existing cloudsync relationship from src:'+src+' to dst:'+dst)
    else:
        logging.info('creating new cloudsync relationship from src:'+src+' to dst:'+dst)

#################################################################
## Main
#################################################################
if not os.path.isfile(cloudsyncapikeysfile):  
    logging.error("api refrence file:"+cloudsyncapikeysfile+" doesn't exists")
    exit(1)

parseapifile()

if args.subparser_name == 'baseline':
    baseline_relation(args.user,args.account,args.broker,args.source,args.destination,args.force)
    user = args.user
    

#broker:nfs:nfsserver:/unixsrc@accountt@user







