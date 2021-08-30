#!/usr/bin/python3
import requests
import json 
import pprint
import argparse
import sys,os
import logging
import time,datetime
import locale
locale.setlocale(locale.LC_ALL, '')

#location of xcption root dir  
root = os.path.dirname(os.path.abspath(__file__))+'/..'

#cloudsync api keys repo 
cloudsyncrepo = os.path.join(root,'system','xcp_repo','cloudsync')
cloudsyncapikeysfile = os.path.join(cloudsyncrepo,'accounts')


#cloudsync api edpoint 
endpoint = 'https://api.cloudsync.netapp.com/api/'
#endpoint = 'https://api.demo.cloudsync.netapp.com/api/'

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
parser_baseline     = subparser.add_parser('baseline', help='create and baseline cloudsync relationships',parents=[parent_parser])
parser_sync         = subparser.add_parser('sync',     help='initiate sync for cloudsync relationships',parents=[parent_parser])
parser_validate     = subparser.add_parser('validate', help='validate cloudsync relationship exists',parents=[parent_parser])
parser_export       = subparser.add_parser('export',   help='export existing cloudsync relationships',parents=[parent_parser])

parser_baseline.add_argument('-s','--source',help="source path",required=True,type=str)
parser_baseline.add_argument('-d','--destination',help="destination path",required=True,type=str)
parser_baseline.add_argument('-f','--force',help="force re-baseline", required=False,action='store_true')

parser_sync.add_argument('-s','--source',help="source path",required=True,type=str)
parser_sync.add_argument('-d','--destination',help="destination path",required=True,type=str)

parser_validate.add_argument('-s','--source',help="source path",required=True,type=str)
parser_validate.add_argument('-d','--destination',help="destination path",required=True,type=str)

parser_export.add_argument('-u','--user',help="cloud central user (api key to be referenced in:"+cloudsyncapikeysfile+')',required=True,type=str)
parser_export.add_argument('-a','--account',help="cloud acount account name",required=True,type=str)
parser_export.add_argument('-b','--broker',help="cloud sync broker name",required=False,type=str)
parser_export.add_argument('-s','--source-type',help="source type",choices=['nfs','cifs'],required=False,type=str,metavar='sourcetype')
parser_export.add_argument('-d','--destination-type',help="source type",choices=['nfs','cifs'],required=False,type=str,metavar='tdestinationtype')

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
            user,apikey = line.split(':')
            apiaccounts[user] = apikey.rstrip()
    except Exception as e:
        logging.error("could not load api refrence file:"+cloudsyncapikeysfile)
        exit(1)

def cloudsyncapicall(user,account,api,method='GET',requestheaders={},body={}):
    
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

#validate fullpath
def validatefullpath(path):
    if path.count('@') != 3:
        logging.error('path:'+path+' is in unsupported format')
        exit(1)
    path,broker,account,user = path.split('@')
    if not user in apiaccounts:
        logging.error("api key for user:"+user+" could not be found in:"+cloudsyncapikeysfile)
        exit(1)         
    return path,broker,account,user


#validate full path
def validaterelationship(src,dst):
    srcpath,srcbroker,srcaccount,srcuser = validatefullpath(src)
    dstpath,dstbroker,dstaccount,dstuser = validatefullpath(dst)

    if srcaccount != dstaccount:
        logging.error('src account: '+srcaccount+' and dst account: '+dstaccount+' must be the same')
        exit(1)  
    if srcuser != dstuser:
        logging.error('src user: '+srcuser+' and dst user: '+dstuser+' must be the same')
        exit(1)  

    parsepath(srcpath)
    parsepath(dstpath)

    return({'srcpath':srcpath,'broker':srcbroker,'account':srcaccount,'dstpath':dstpath,'user':srcuser})

#parse path 
def parsepath(path):

    if path.count('://') != 1:
        logging.error('path:'+path+' is in unsupported format')
        exit(1)        
    type,allpath = path.split('://')
    if not type or type not in ['cifs','nfs','nfs3','nfs4.0','nfs4.1','nfs4.2']:
        logging.error('path:'+path+' is in unsupported format')
        exit(1)        
    
    if type in ['nfs','nfs3','nfs4.0','nfs4.1','nfs4.2']:
        if allpath.count(':') != 1:
            logging.error('path:'+path+' is in unsupported format')
            exit(1)            
        nfsserver,fullpath=allpath.split(':')
        dirs = fullpath.split('/')
        export = dirs[1]
        del dirs[1]
        deeppath =''
        if len(dirs) > 1:
            deeppath = '/'.join(dirs)
        if type in ['nfs','nfs3']:
            version = '3'
        elif type in ['nfs4.0']:
            version = '4'
        elif type in ['nfs4.1']:
            version = '4.1'
        elif type in ['nfs4.2']:
            version = '4.2'

        res = {'type':type,'path':allpath,'server':nfsserver,'fullpath':fullpath,'export':export,'deeppath':deeppath,'version':version}
    if type == 'cifs':
        dirs = allpath.split('\\')
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
        res = {'type':type,'path':allpath,'server':server,'share':share,'deeppath':deeppath}    
    
    return(res)

#get broker info 
def getbrokerinfo(user,account,broker,refresh=False):
    global brokerhash 
    if not user+broker in brokerhash or refresh:
        accountid = getaccountid(user,account)
        brokers = cloudsyncapicall(user,account,'data-brokers','GET',{'x-account-id':accountid})['body']
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
        accounts = cloudsyncapicall(user,account,'accounts')['body']
        for acc in accounts:
            accounthash[acc['name']] = acc['accountId']
        if not account in accounthash:
            return({})
        else:
            return accounthash[account]

#get relationship data
def getcloudsyncrelationship (user,account,broker,src,dst,relid=0,filter=False):
    if not filter:
        #validate src 
        srcdetails = parsepath(src)
        #validate dst 
        dstdetails = parsepath(dst)
    
    #validate broker
    if broker:
        brkinfo = getbrokerinfo(user,account,broker,True)
        if not brkinfo:
            logging.error("broker:"+broker+" is not availble for user:"+user)
            exit(1)
        brkid = brkinfo['id']

    accountid = getaccountid(user,account)
    if not accountid:
        logging.error("account:"+account+" is not availble for user:"+user)
        exit(1)
          
    if relid and not filter:
        #get specific relationship info 
        rel = cloudsyncapicall(user,account,'relationships-v2/'+relid,'GET',{'x-account-id':accountid})['body'] 
        if rel:
            logging.debug('existing cloudsync relationship from src: '+src+' to dst: '+dst+' was found')
            return(rel) 
        else:
            return({})
    #filter only specific rels 
    elif filter:
        rels = cloudsyncapicall(user,account,'relationships-v2','GET',{'x-account-id':accountid})['body'] 
        relfilter = []
        for rel in rels:
            found = True
            if broker:
                if rel['dataBroker'] != brkid:
                    found = False
            if src: 
                if not src in rel['source']:
                    found = False
            if dst:
                if not dst in rel['target']:
                    found = False
            if found:
                relfilter.append(rel)                
        return(relfilter)
    #filter specific rel from all 
    else:         
        #get relationship info 
        rels = cloudsyncapicall(user,account,'relationships-v2','GET',{'x-account-id':accountid})['body'] 
        
        #with open('fullrels.json', 'w') as fp:
        #    json.dump(rels, fp) 
        #exit(1)    
        
        for rel in rels:
            found = True
            if rel['dataBroker'] != brkid:
                found = False
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
                logging.debug('existing cloudsync relationship from src: '+src+' to dst: '+dst+' was found')
                return(rel)

        logging.debug('existing cloudsync relationship from src: '+src+' to dst: '+dst+' could not be found')
        return({})

def deletecloudsyncrelationship(user,account,broker,src,dst):
    logging.info('deleting existing cloudsync relationship from src: '+src+' to dst: '+dst)
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst)
    if relinfo:
        relid = relinfo['relationshipId']
        accountid = getaccountid(user,account)
        delresult = cloudsyncapicall(user,account,'relationships/'+relid,'DELETE',{'x-account-id':accountid})

def getnfsexports(user,account,broker,host):
    #validate broker
    logging.debug('getting list of exports from broker: '+broker+' for host: '+host)
    if broker:
        brkinfo = getbrokerinfo(user,account,broker,True)
        if not brkinfo:
            logging.error("broker:"+broker+" is not availble for user:"+user)
            exit(1)
        brkid = brkinfo['id']
    accountid = getaccountid(user,account)
    if not accountid:
        logging.error("account:"+account+" is not availble for user:"+user)
        exit(1)
    
    exports = cloudsyncapicall(user,account,'data-brokers/'+brkid+'/list-nfs-exports?host='+host,'GET',{'x-account-id':accountid})['body']

def createcloudsyncrelationship(user,account,broker,src,dst):
    logging.info('creating new cloudsync relationship from src: '+src+' to dst: '+dst)
    brkinfo = getbrokerinfo(user,account,broker)
    if not brkinfo:
        logging.error("broker:"+broker+" is not availble for user:"+user)
        exit(1)

    #validate src 
    srcdetails = parsepath(src)
    #validate dst 
    dstdetails = parsepath(dst)

#   API ISSUES for listing 
#    if srcdetails['type']=='nfs':
#        exports = getnfsexports(user,account,broker,srcdetails['server'])
    

    #load template         
    cloudsynccreatetemplatefile = os.path.join(root,'cloudsync','create_relationship_template.txt')
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
        cloudsynccreate["source"]['nfs']['version'] = srcdetails['version']
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
        cloudsynccreate["target"]['nfs']['version'] = dstdetails['version']

    #create the relationship 
    accountid = getaccountid(user,account)
    delresult = cloudsyncapicall(user,account,'relationships-v2','POST',{'x-account-id':accountid},cloudsynccreate)

def synccloudsyncrelationship(user,account,broker,src,dst):
    logging.info('issue sync fo cloudsync relationship from src: '+src+' to dst: '+dst)
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst)
    
    if relinfo:
        relid = relinfo['relationshipId']
        if relinfo['activity']['status'] == 'RUNNING':
            logging.error('sync already running for src: '+src+' to dst: '+dst)
            exit(1)
        accountid = getaccountid(user,account)
        starttime = time.time()
        syncresult = cloudsyncapicall(user,account,'relationships/'+relid+'/sync','PUT',{'x-account-id':accountid}) 

        #check sync status 
        count = 0
        prevbytes = 0 
        while True:
            count+=1
            relinfo = getcloudsyncrelationship (user,account,broker,src,dst,relid)
            currenttime = time.time()
            timespan = currenttime-starttime

            hours,timespan = divmod(timespan, 3600)
            minutes,timespan = divmod(timespan, 60)
            seconds = timespan
            if seconds < 1: seconds=1
            timestr = str(int(hours))+'h'+str(int(minutes))+'m'+str(int(seconds))+'s'  

            
            #with open('relstatus'+str(count)+'.json', 'w') as fp:
            #    json.dump(relinfo, fp)             

            scanned = relinfo['activity']['filesScanned']
            scanned += relinfo['activity']['dirsScanned']
            copied = relinfo['activity']['filesCopied']
            copied += relinfo['activity']['dirsCopied']
            #modified = relinfo['activity']['filesMarkedForCopy']
            #modified += relinfo['activity']['dirsMarkedForCopy']
            modified = 0
            errors = relinfo['activity']['filesFailed']
            errors += relinfo['activity']['dirsFailed'] 
            filesremove = relinfo['activity']['filesRemoved']
            dirsremove = relinfo['activity']['dirsRemoved']
            bytescopied = relinfo['activity']['bytesCopied']

            newbytes = bytescopied-prevbytes
            bw = round(newbytes/1024/1024,2)
            bwqunatifier = 'MiB'
            bws = round(bw/timespan,2)
            bwsquantifier = 'MiB/s'

            if bw >= 1000 and bw<1000000:
                bw = round(bw/1024,2)
                bwqunatifier = 'GiB' 
            elif bw>=1000000:
                bw = round(bw,2)
                bwqunatifier = 'TiB'

            if bws >= 1000 and bws<1000000:
                bws = round(bws/1024,2)
                bwsquantifier = 'GiB/s' 
            elif bws>=1000000:
                bws = round(bws,2)
                bwsquantifier = 'TiB/s'                  

            prevbytes = bytescopied

            logging.info(f"{scanned:,} scanned, {copied:,} copied, {modified:,} modification, {errors:,} errors, {filesremove:,} file.gone, {dirsremove:,} dir.gone, {bw}{bwqunatifier}({bws}{bwsquantifier}), {timestr}")

            if not relinfo['activity']['status'] == 'RUNNING': break
            time.sleep(10)
        
        if relinfo['activity']['filesFailed'] > 0 or relinfo['activity']['dirsFailed'] > 0:
            print("")
            print(f"encountered {errors} errors during sync")
            print("top 5 errors during sync operation (detailed logs can be downloaded from cloudsync portal):")
            for err in relinfo['activity']['topFiveMostCommonRelationshipErrors']:
                desc = ''
                if 'description' in err: desc = err['description']
                print(f"count: {err['counter']} step: {err['step']} errorCode: {err['errorCode']} description: {desc}")
            print("")
            
        if relinfo['activity']['status'] == 'FAILED':
            errormsg = relinfo['activity']['failureMessage']
            logging.error('cloudsync sync failed for:'+src+' to dst: '+dst+' with error:'+errormsg)
            exit(1)
    else:
        logging.error('could not find cloudsync relationship for:'+src+' to dst: '+dst)

def baselinerelation (user,account,broker,src,dst,force=False):
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst)
    if relinfo and not force:
        logging.error('cloudsync relationship from src: '+src+' to dst: '+dst+' already exists. use --force to recreate') 
        exit(1)
    elif relinfo and force:
        deletecloudsyncrelationship(user,account,broker,src,dst)
        createcloudsyncrelationship(user,account,broker,src,dst)
    else:
        createcloudsyncrelationship(user,account,broker,src,dst)
        synccloudsyncrelationship(user,account,broker,src,dst)

def exportcloudsyncrelationship (user,account,broker,src,dst):
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst,False,True)
    print(json.dumps(relinfo,indent=4))

def validatecloudsyncrelationship (user,account,broker,src,dst):
    relinfo = getcloudsyncrelationship (user,account,broker,src,dst)
    print(json.dumps(relinfo,indent=4))


#################################################################
## Main
#################################################################
if not os.path.isfile(cloudsyncapikeysfile):  
    logging.error("api refrence file:"+cloudsyncapikeysfile+" doesn't exists")
    exit(1)

parseapifile()

if args.subparser_name == 'baseline':
    relinfo = validaterelationship(args.source,args.destination)
    baselinerelation(relinfo['user'],relinfo['account'],relinfo['broker'],relinfo['srcpath'],relinfo['dstpath'],args.force)
if args.subparser_name == 'sync':
    relinfo = validaterelationship(args.source,args.destination)
    synccloudsyncrelationship(relinfo['user'],relinfo['account'],relinfo['broker'],relinfo['srcpath'],relinfo['dstpath'])
if args.subparser_name == 'validate':
    relinfo = validaterelationship(args.source,args.destination)
    validatecloudsyncrelationship(relinfo['user'],relinfo['account'],relinfo['broker'],relinfo['srcpath'],relinfo['dstpath'])
if args.subparser_name == 'export':
    exportcloudsyncrelationship(args.user,args.account,args.broker,args.source_type,args.destination_type)
    







