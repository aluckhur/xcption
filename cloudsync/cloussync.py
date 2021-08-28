#!/usr/bin/python3
import requests
import json 
import pprint
import argparse
import sys,os
import logging
import copy

#location of xcption root dir  
root = os.path.dirname(os.path.abspath(__file__))+'/..'

#cloudsync api keys repo 
cloudsyncrepo = os.path.join(root,'system','xcp_repo','cloudsync')
cloudsyncapikeysfile = os.path.join(cloudsyncrepo,'accounts')


#cloudsync api edpoint 
endpoint = 'https://api.cloudsync.netapp.com/api/'

#dictionary for api accounts
apiaccounts = {}
#dictionary for brokers
brokerhash = {}
#dictionary for accounts
accounthash = {}

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

def cloudsyncapicall(user,api,method='GET',requestheaders={},body={}):
    if not user in apiaccounts:
        logging.error("api key for user:"+user+" could not be found in:"+cloudsyncapikeysfile)
        exit(1)    
    authkey = apiaccounts[user]
    headers = {'authorization': 'Bearer '+authkey,'accept': 'application/json'}
    for requestheader in requestheaders.keys():
        headers[requestheader] =  requestheaders[requestheader]

    logging.debug("issuing cloudsync api call:"+method+' '+endpoint+api)
    out = {}
    out['response'] = requests.request(method,endpoint+api, headers=headers, json=body)

    try:
        out['body'] = json.loads(out['response'].content)
    except:
        out['body'] = {}

    if not out['response'].ok:
        logging.error("cloudsync api call:"+method+' '+endpoint+api+' failed:'+out['response'].content.decode('utf-8'))
        exit(1)
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
        if len(dirs) > 1:
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

#get broker info 
def getbrokerinfo(user,broker):
    global brokerhash 
    if not user+broker in brokerhash:
        brokers = cloudsyncapicall(user,'data-brokers')['body']
        found = False
        for brk in brokers:
            brokerhash[user+brk['name']] = brk
        if not user+broker in brokerhash:
            return({})

    if brokerhash[user+broker]['status'] != 'COMPLETE':
        logging.error("broker:"+broker+' status is:'+brokerhash[user+broker]['status'])
        exit(1)

    return(brokerhash[user+broker])

def getaccountid(user,account):
    global accounthash 
    if account in accounthash:
        return accounthash[account]
    else:
        accounts = cloudsyncapicall(user,'accounts')['body']
        for acc in accounts:
            accounthash[acc['name']] = acc['accountId']
        if not account in accounthash:
            return({})
        else:
            return accounthash[account]

#get relationship data
def getcloudsyncrelationship (user,account,broker,src,dst):
    #validate src 
    srcdetails = parsepath(src)
    #validate dst 
    dstdetails = parsepath(dst)

    #validate broker
    if not getbrokerinfo(user,broker):
        logging.error("broker:"+broker+" is not availble for user:"+user)
        exit(1)

    accountid = getaccountid(user,account)
    if not accountid:
        logging.error("account:"+account+" is not availble for user:"+user)
        exit(1)

    #get relationship info 
    rels = cloudsyncapicall(user,'relationships-v2','GET',{'x-account-id':accountid})['body']           
    
    for rel in rels:
        found = True
        if not srcdetails['type'] in rel['source']:
            found = False   
        if srcdetails['type'] == 'nfs' and 'nfs' in rel['source']:
            if rel['source']['nfs']['host'] != srcdetails['server']:
                found = False
            elif rel['source']['nfs']['export'] != '/'+srcdetails['export']:
                found = False
                
            elif rel['source']['nfs']['path'] != srcdetails['deeppath']:
                found = False
          
        if not dstdetails['type'] in rel['target']:
            found = False
        if dstdetails['type'] == 'nfs' and 'nfs' in rel['target']:
            if rel['target']['nfs']['host'] != dstdetails['server']:
                found = False
                
            elif rel['target']['nfs']['export'] != '/'+dstdetails['export']:
                found = False
        
            elif rel['target']['nfs']['path'] != dstdetails['deeppath']:
                found = False   

        if found: 
            logging.debug('existing cloudsync relationship from src:'+src+' to dst:'+dst+' was found')
            return(rel)

    logging.debug('existing cloudsync relationship from src:'+src+' to dst:'+dst+' could not be found')
    return({})

def deletecloudsyncrelationship(user,account,broker,src,dst):
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst)
    if relinfo:
        relid = relinfo['relationshipId']
        accountid = getaccountid(user,account)
        delresult = cloudsyncapicall(user,'relationships/'+relid,'DELETE',{'x-account-id':accountid})


def createcloudsyncrelationship(user,account,broker,src,dst):
    brkinfo = getbrokerinfo(user,broker)
    if not brkinfo:
        logging.error("broker:"+broker+" is not availble for user:"+user)
        exit(1)

    #validate src 
    srcdetails = parsepath(src)
    #validate dst 
    dstdetails = parsepath(dst)

    #load template         
    cloudsynccreatetemplatefile = os.path.join(root,'cloudsync','create_relationship.txt')
    if not os.path.isfile(cloudsynccreatetemplatefile):
        logging.error("create relationship template file:"+cloudsynccreatetemplatefile+" could not be found")
        exit(1)       
    with open(cloudsynccreatetemplatefile) as f:
        cloudsynccreate = json.load(f)
        f.close()
    
    #preperation of required structure for relationship 
    cloudsynccreate["dataBrokerId"] = brkinfo['id']
    del cloudsynccreate["groupId"]

    cloudsynccreate["source"]["protocol"] = srcdetails['type']
    protocols = list(cloudsynccreate["source"].keys())
    for protocol in protocols:
        if protocol != 'protocol' and protocol != srcdetails['type']: del cloudsynccreate["source"][protocol]
    
    protocols = list(cloudsynccreate["sourceCredentials"].keys())
    for protocol in protocols:
        if protocol != srcdetails['type']: del cloudsynccreate["sourceCredentials"][protocol]
    if not cloudsynccreate["sourceCredentials"]: del cloudsynccreate["sourceCredentials"]

    cloudsynccreate["target"]["protocol"] = dstdetails['type']
    protocols = list(cloudsynccreate["target"].keys())
    for protocol in protocols:
        if protocol != 'protocol' and protocol != dstdetails['type']: del cloudsynccreate["target"][protocol]

    protocols = list(cloudsynccreate["targetCredentials"].keys())
    for protocol in protocols:
        if protocol != dstdetails['type']: del cloudsynccreate["targetCredentials"][protocol]
    if not cloudsynccreate["targetCredentials"]: del cloudsynccreate["targetCredentials"]

    del cloudsynccreate['settings']["schedule"]['nextTime']
    cloudsynccreate['settings']["schedule"]['syncWhenCreated'] = False 
    cloudsynccreate['settings']["schedule"]['isEnabled'] = False 

    if srcdetails['type'] == 'nfs': 
        del cloudsynccreate["source"]['nfs']['workingEnvironmentId']
        del cloudsynccreate["source"]['nfs']['accessPoint']
        cloudsynccreate["source"]['nfs']['host'] = srcdetails['server']
        cloudsynccreate["source"]['nfs']['export'] = '/'+srcdetails['export']
        cloudsynccreate["source"]['nfs']['path'] = srcdetails['deeppath']
        cloudsynccreate["source"]['nfs']['version'] = '3'
    if dstdetails['type'] == 'nfs':
        del cloudsynccreate["settings"]['objectTagging']
        del cloudsynccreate['encryption']
        
        if cloudsynccreate["settings"]['files']["excludeExtensions"][0] == "string": del cloudsynccreate["settings"]['files']["excludeExtensions"]

        if cloudsynccreate["settings"]['files']["minDate"] == "string": del cloudsynccreate["settings"]['files']["minDate"]
        if cloudsynccreate["settings"]['files']["maxDate"] == "string": del cloudsynccreate["settings"]['files']["maxDate"]
        
        del cloudsynccreate["target"]['nfs']['workingEnvironmentId']
        del cloudsynccreate["target"]['nfs']['accessPoint']
        cloudsynccreate["target"]['nfs']['host'] = dstdetails['server']
        cloudsynccreate["target"]['nfs']['export'] = '/'+dstdetails['export']
        cloudsynccreate["target"]['nfs']['path'] = dstdetails['deeppath']
        cloudsynccreate["target"]['nfs']['version'] = '3'

    #create the relationship 
    accountid = getaccountid(user,account)
    delresult = cloudsyncapicall(user,'relationships-v2','POST',{'x-account-id':accountid},cloudsynccreate)


    



def  baselinerelation (user,account,broker,src,dst,force=False):
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst)
    if relinfo and not force:
        logging.error('cloudsync relationship from src:'+src+' to dst:'+dst+' already exists. use --force to force new baseline') 
        exit(1)
    elif relinfo and force:
        logging.info('deleting existing cloudsync relationship from src:'+src+' to dst:'+dst)
        deletecloudsyncrelationship(user,account,broker,src,dst)
        logging.info('creating new cloudsync relationship from src:'+src+' to dst:'+dst)
        createcloudsyncrelationship(user,account,broker,src,dst)
    else:
        logging.info('creating new cloudsync relationship from src:'+src+' to dst:'+dst)
        createcloudsyncrelationship(user,account,broker,src,dst)

#################################################################
## Main
#################################################################
if not os.path.isfile(cloudsyncapikeysfile):  
    logging.error("api refrence file:"+cloudsyncapikeysfile+" doesn't exists")
    exit(1)

parseapifile()

if args.subparser_name == 'baseline':
    baselinerelation(args.user,args.account,args.broker,args.source,args.destination,args.force)
    user = args.user
    

#broker:nfs:nfsserver:/unixsrc@accountt@user







