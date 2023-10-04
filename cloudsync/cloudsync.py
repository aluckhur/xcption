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

#supportedrelationshiptype 
supportedrelationshiptype = ['cifs','nfs','nfs3','nfs4.0','nfs4.1','nfs4.2','nfs-fsx','local','s3ontap','sgws','s3']

#cloudsync repository location
cloudsyncrepo = os.path.join(root,'system','xcp_repo','cloudsync')
#cloudsync api keys repo 
cloudsyncapikeysfile = os.path.join(cloudsyncrepo,'accounts')
#cloud sync relationship template         
cloudsynccreatetemplatefile = os.path.join(cloudsyncrepo,'create_relationship_template.txt')
#cloudsync credentials file for required protocols)
cloudsynccredentialsfile = os.path.join(cloudsyncrepo,'creds')

#cloudsync api edpoint 
endpoint = 'https://api.cloudsync.netapp.com/api/'
#endpoint = 'https://api.demo.cloudsync.netapp.com/api/'

#dictionary for api accounts
apiaccounts = {}
#dictionary for brokers
brokerhash = {}
#dictionary for groups
grouphash = {}
#dictionary for accounts
accounthash = {}
#dictionary for protocol credentials for
credshash = {}
#token cache 
token = None 
tokencounter = 0


parent_parser = argparse.ArgumentParser(add_help=False)
parser = argparse.ArgumentParser()

parser.add_argument('-d','--debug',   help="log debug messages to console", action='store_true')
subparser = parser.add_subparsers(dest='subparser_name', help='sub commands that can be used')

# create the sub commands 
parser_create       = subparser.add_parser('create',   help='create cloudsync relationship',parents=[parent_parser])
parser_baseline     = subparser.add_parser('baseline', help='create than baseline cloudsync relationship',parents=[parent_parser])
parser_sync         = subparser.add_parser('sync',     help='initiate sync for cloudsync relationship',parents=[parent_parser])
parser_validate     = subparser.add_parser('validate', help='validate cloudsync relationship exists',parents=[parent_parser])
parser_abort        = subparser.add_parser('abort',    help='abort sync for cloudsync relationship',parents=[parent_parser])
parser_export       = subparser.add_parser('export',   help='export existing cloudsync relationships',parents=[parent_parser])
parser_delete       = subparser.add_parser('delete',   help='delete existing cloudsync relationship',parents=[parent_parser])

parser_create.add_argument('-s','--source',help="source path",required=True,type=str)
parser_create.add_argument('-d','--destination',help="destination path",required=True,type=str)

parser_baseline.add_argument('-s','--source',help="source path",required=True,type=str)
parser_baseline.add_argument('-d','--destination',help="destination path",required=True,type=str)
parser_baseline.add_argument('-f','--force',help="force re-baseline", required=False,action='store_true')

parser_delete.add_argument('-s','--source',help="source path",required=True,type=str)
parser_delete.add_argument('-d','--destination',help="destination path",required=True,type=str)
parser_delete.add_argument('-f','--force',help="force delete", required=False,action='store_true')

parser_sync.add_argument('-s','--source',help="source path",required=True,type=str)
parser_sync.add_argument('-d','--destination',help="destination path",required=True,type=str)

parser_abort.add_argument('-s','--source',help="source path",required=True,type=str)
parser_abort.add_argument('-d','--destination',help="destination path",required=True,type=str)

parser_validate.add_argument('-s','--source',help="source path",required=True,type=str)
parser_validate.add_argument('-d','--destination',help="destination path",required=True,type=str)

parser_export.add_argument('-u','--user',help="cloud central user (api key to be referenced in:"+cloudsyncapikeysfile+')',required=True,type=str)
parser_export.add_argument('-a','--account',help="cloud acount account name",required=True,type=str)
parser_export.add_argument('-b','--group',help="cloud sync broker group name",required=False,type=str)
parser_export.add_argument('-s','--source-type',help="source type:["+' '.join(supportedrelationshiptype)+']',choices=supportedrelationshiptype,required=False,type=str,metavar='sourcetype')
parser_export.add_argument('-d','--destination-type',help="destination type:["+' '.join(supportedrelationshiptype)+']',choices=supportedrelationshiptype,required=False,type=str,metavar='tdestinationtype')

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
        if not os.path.isfile(cloudsyncapikeysfile):  
            logging.error("api refrence file:"+cloudsyncapikeysfile+" doesn't exists, please create it based on the template in:"+os.path.join(root,'cloudsync','acoounts'))
            exit(1)
        logging.debug("loading api refrence file:"+cloudsyncapikeysfile)
        f = open(cloudsyncapikeysfile, 'r')
        lines = f.readlines()
        for line in lines:
            if line.startswith('#'): continue
            user,apikey = line.split(':')
            apiaccounts[user] = apikey.rstrip()
    except Exception as e:
        logging.error("could not load api refrence file:"+cloudsyncapikeysfile)
        print(e)
        exit(1)

def getcredsfromfile(type,key):
    global credshash

    if not credshash: 
        try:
            if not os.path.isfile(cloudsynccredentialsfile):  
                logging.debug("credentials file:"+cloudsynccredentialsfile+" doesn't exists, please create it based on the template in:"+os.path.join(root,'cloudsync','creds'))
                exit(1)
            logging.debug("loading cred file:"+cloudsynccredentialsfile)
            f = open(cloudsynccredentialsfile, 'r')
            lines = f.readlines()
            for num,line in enumerate(lines):
                line = line.rstrip()
                if line.startswith('#'): continue
                details = line.split(':')
                if len(details)<4 or len(details)>5: 
                    logging.debug("cannot parse creds file line:"+str(num+1))
                    continue
                if not details[0] in ['cifs','sgws','s3ontap','s3']:
                    logging.debug("cannot parse creds file line:"+str(num+1)+' unsupported protocol')
                    continue
                
                if details[0] == 'cifs':
                    credshash[details[0]+details[1]] = {}
                    credshash[details[0]+details[1]]['domain'] = ''
                    if len(details) == 5:
                        credshash[details[0]+details[1]]['domain'] = details[4]
                    credshash[details[0]+details[1]]['username'] = details[2]
                    credshash[details[0]+details[1]]['password'] = details[3]
                    logging.debug("loaded creds for type:cifs server/bucket:"+details[0]+details[1])
                    
                if details[0] in ['s3','sgws','s3ontap']:
                    credshash[details[0]+details[1]] = {}
                    credshash[details[0]+details[1]]['accessKey'] = details[2]
                    credshash[details[0]+details[1]]['secretKey'] = details[3]
                    logging.debug("loaded creds for type:"+details[0]+" server/bucket:"+details[0]+details[1])

        except Exception as e:
            logging.error("could not load creds file:"+cloudsynccredentialsfile)
            print(e)
            exit(1)                

    if type+key in credshash: 
        return(credshash[type+key])
    else:
        return{}
    

def cloudsyncapicall(user,account,api,method='GET',requestheaders={},body={}):

    if not user in apiaccounts:
        logging.error("api key for user:"+user+" could not be found in:"+cloudsyncapikeysfile)
        exit(1)    
    authkey = apiaccounts[user]

    #get global token variables 
    global token
    global tokencounter 

    #refresh api token when 
    if not token and tokencounter > 10:
        tokencounter = 0
        logging.debug("generating cloudsync token from oauth")    
        tokenoutput = requests.request('POST','https://netapp-cloud-account.auth0.com/oauth/token', 
                                    headers={'Content-Type': 'application/json'}, 
                                    json={"grant_type": "refresh_token","refresh_token": authkey, "client_id": "Mu0V1ywgYteI6w1MbD15fKfVIUrNXGWC"})
        try :
            token = json.loads(tokenoutput.content)['access_token']
        except:
            logging.error("cloudsync authentication token could not be created")
            exit(1)      

    #increase token counter by 10, when it will be 10 the token will be refreshed 
    tokencounter += 1                              
    
    headers = {'authorization': 'Bearer '+token,'accept': 'application/json'}
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
        logging.error('path:'+path+' is in unsupported format (cloudsync relationshipt should be type://path@broker_group@cloudsync_account@cloudsync_user')
        exit(1)
    path,group,account,user = path.split('@')
    if not user in apiaccounts:
        logging.error("api key for user:"+user+" could not be found in:"+cloudsyncapikeysfile)
        exit(1)         
    return path,group,account,user


#validate full path
def validaterelationship(src,dst):
    
    srcpath,srcgroup,srcaccount,srcuser = validatefullpath(src)
    dstpath,srcgroup,dstaccount,dstuser = validatefullpath(dst)

    if srcaccount != dstaccount:
        logging.error('src account: '+srcaccount+' and dst account: '+dstaccount+' must be the same')
        exit(1)  
    if srcuser != dstuser:
        logging.error('src user: '+srcuser+' and dst user: '+dstuser+' must be the same')
        exit(1)  

    parsepath(srcpath)
    parsepath(dstpath)

    return({'srcpath':srcpath,'group':srcgroup,'account':srcaccount,'dstpath':dstpath,'user':srcuser})

#parse path 
def parsepath(path, validatecreds=False):
    global supportedrelationshiptype
    if path.count('://') != 1:
        logging.error('path:'+path+' is in unsupported format (type could not be extracted)')
        exit(1) 

    type,allpath = path.split('://')

    if not type or type not in supportedrelationshiptype:
        logging.error('path:'+path+' is not from the supported list:'+' '.join(supportedrelationshiptype))
        exit(1)        
    
    if 'nfs' in type:
        if allpath.count(':') > 2 or allpath.count(':') < 1:
            logging.error('path:'+path+' is in unsupported format ('+type+'://server:/export[:folder])')
            exit(1)            
        elif allpath.count(':') == 1:
            nfsserver,export,deeppath=(allpath+":").split(':')
        elif allpath.count(':') == 2:
            nfsserver,export,deeppath=allpath.split(':')         
        #remove trailing /
        export = export[1:]
        
        fullpath = export
        if deeppath:
            fullpath = export + "/" + deeppath 
        # dirs = fullpath.split('/')
        # export = dirs[1]
        # del dirs[1]
        # deeppath =''
        # if len(dirs) > 1:
        #     deeppath = '/'.join(dirs)

        
        version = '3'
        if type in ['nfs','nfs3']:
            version = '3'
        elif type in ['nfs4.0']:
            version = '4'
        elif type in ['nfs4.1']:
            version = '4.1'
        elif type in ['nfs4.2']:
            version = '4.2'
        
        type = 'nfs'
        provider = 'nfs'

        if type == 'nfs-fsx': 
            provider = 'fsx'

        res = {'type':type,'path':allpath,'server':nfsserver,'fullpath':fullpath,'export':export,'deeppath':deeppath,'version':version, 'provider':provider}

    if type == 'cifs':
        if allpath.count(':') != 1:
            logging.error('path:'+path+' is in unsupported format (cifs://host:/share/..)')
            exit(1)            
        server,fullpath=allpath.split(':')
        dirs = fullpath.split('/')
        share = dirs[1]
        del dirs[1]
        deeppath =''
        if len(dirs) > 1:
            deeppath = '/'.join(dirs)
        version = '2.1'
        creds = getcredsfromfile(type,server)

        res = {'type':type,'path':allpath,'server':server,'fullpath':fullpath,'share':share,'deeppath':deeppath,'version':version, 'credentials':creds}

    if type in ['local']:
        if not allpath.startswith('/'):
            logging.error('path:'+path+' is in unsupported format (local:///data)')
            exit(1)            
        res = {'type':type,'path':allpath}
    
    if type in ['s3ontap','sgws','s3']:
        if 1 > allpath.count(':') > 2 and type != 's3': 
            logging.error('path:'+path+' is in unsupported format ('+type+'://host:bucket:[port])')
            exit(1)
        if allpath.count(':') != 1 and type == 's3': 
            logging.error('path:'+path+' is in unsupported format (s3://region:bucket)')
            exit(1)

        if type == 's3ontap': provider = 'ontap'
        if type == 'sgws': provider = 'sgws'
        if type == 's3': provider = 's3'

        if provider != 's3':
            if allpath.count(':') == 1: 
                host,bucket=allpath.split(':')
                port= ''
            else:
                host,bucket,port=allpath.split(':')
                port = str(port)

            creds = getcredsfromfile(type,bucket+'@'+host)
    
            res = {'type':'s3','bucket':bucket,'host':host,'port':port,'credentials':creds,'provider':provider}

        elif provider == 's3':
            region,bucket=allpath.split(':')

            creds = getcredsfromfile(provider,bucket+'@'+region)                
            res = {'type':'s3','bucket':bucket,'credentials':creds,'provider':provider,'region':region}

    return(res)

#get group info 
def getgroupinfo(user,account,group,refresh=False):
    global grouphash
    if not user+group in grouphash or refresh:
        accountid = getaccountid(user,account)
        groups = cloudsyncapicall(user,account,'groups','GET',{'x-account-id':accountid})['body']
        found = False
        for grp in groups:
            grouphash[user+grp['name']] = grp

    if not user+group in grouphash:
        return({})

    if 'dataBrokers' in grouphash[user+group]:
        alloffline = True 
        for databroker in grouphash[user+group]['dataBrokers']:
            if databroker['status'] == 'COMPLETE':
                alloffline = False
        if alloffline:
            logging.error("none of the brokers in group:"+group+' is online')
            exit(1)
    else:
        logging.warning("no data brokers in group:"+group)

    return(grouphash[user+group])

#get broker info 
def getbrokernamebyid(user,account,brkid):
    global brokerhash 
    if not user+brkid in brokerhash:
        accountid = getaccountid(user,account)
        brokers = cloudsyncapicall(user,account,'data-brokers','GET',{'x-account-id':accountid})['body']
        found = False
        for brk in brokers:
            brokerhash[user+brk['id']] = brk['name']
    
    if not user+brkid in brokerhash:
        return('unknown')
    
    return(brokerhash[user+brkid])

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
def getcloudsyncrelationship (user,account,group,src,dst,relid=0,filter=False):
    if not filter:
        #validate src 
        srcdetails = parsepath(src)
        #validate dst 
        dstdetails = parsepath(dst)
    
    #validate group group
    if group:
        grpinfo = getgroupinfo(user,account,group,True)
        if not grpinfo:
            logging.error("group:"+group+" is not availble for user:"+user)
            exit(1)
        grpid = grpinfo['id']

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
            if group:
                if rel['group'] != grpid:
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
            if rel['group'] != grpid:
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

def deletecloudsyncrelationship(user,account,group,src,dst):
    logging.info('deleting existing cloudsync relationship from src: '+src+' to dst: '+dst)
    relinfo = getcloudsyncrelationship (user,account,group,src,dst)
    if relinfo:
        relid = relinfo['relationshipId']
        accountid = getaccountid(user,account)
        delresult = cloudsyncapicall(user,account,'relationships/'+relid,'DELETE',{'x-account-id':accountid})

def getnfsexports(user,account,group,host,export,deeppath):
    return()
    #validate group
    logging.debug('getting list of exports from group: '+group+' for host: '+host)
    if group:
        grpinfo = getgroupinfo(user,account,group,True)
        if not brkinfo:
            logging.error("group:"+group+" is not availble for user:"+user)
            exit(1)
        grpid = grpinfo['id']
    accountid = getaccountid(user,account)
    if not accountid:
        logging.error("account:"+account+" is not availble for user:"+user)
        exit(1)

    listnfs = cloudsyncapicall(user,account,'group/'+brkid+'/list-nfs-exports?host='+host,'GET',{'x-account-id':accountid})
    #print(listnfs)
    try:
        while True:
            jobinfo = cloudsyncapicall(user,account,'messages/client','GET',{'x-account-id':accountid})['body']
            jobid = jobinfo[0]['id']
            print(jobinfo)
            joboutput = cloudsyncapicall(user,account,'messages/client?last='+str(jobid),'GET',{'x-account-id':accountid})['body']
            print(joboutput)
    except Exception as e:
        logging.error("could not get information from group:"+group)
        print(e)

def createcloudsyncrelationship(user,account,group,src,dst,validate=False):
    logging.debug('creating new cloudsync relationship from src: '+src+' to dst: '+dst)
    relinfo = getcloudsyncrelationship (user,account,group,src,dst)
    if relinfo:
        logging.error('cloudsync relationship from src: '+src+' to dst: '+dst+' already exists') 
        exit()
    grpinfo = getgroupinfo(user,account,group)
    if not grpinfo:
        logging.error("group:"+group+" is not availble for user:"+user)
        exit(1)

    #validate src 
    srcdetails = parsepath(src,True)
    #validate dst 
    dstdetails = parsepath(dst,True)

    #if srcdetails['type']=='nfs':
    #    exports = getnfsexports(user,account,group,srcdetails['server'],srcdetails['export'],srcdetails['deeppath'])
    
    if not os.path.isfile(cloudsynccreatetemplatefile):
        logging.error("create relationship template file:"+cloudsynccreatetemplatefile+" could not be found")
        exit(1)       
    with open(cloudsynccreatetemplatefile) as f:
        cloudsynccreate = json.load(f)
        f.close()
    
    #preperation of required structure for relationship 
    cloudsynccreate["groupId"]=grpinfo['id']
    del cloudsynccreate["dataBrokerId"]

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

    #type is nfs
    if srcdetails['type'] == 'nfs': 
        del cloudsynccreate["source"]['nfs']['workingEnvironmentId']
        del cloudsynccreate["source"]['nfs']['accessPoint']
        cloudsynccreate["source"]['nfs']['host'] = srcdetails['server']
        cloudsynccreate["source"]['nfs']['export'] = '/'+srcdetails['export']
        cloudsynccreate["source"]['nfs']['path'] = srcdetails['deeppath']
        cloudsynccreate["source"]['nfs']['version'] = srcdetails['version']
        cloudsynccreate["source"]['nfs']['provider'] = srcdetails['provider']

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
        cloudsynccreate["target"]['nfs']['provider'] = dstdetails['provider']

    #type is cifs
    if srcdetails['type'] == 'cifs': 
        del cloudsynccreate["source"]['cifs']['workingEnvironmentId']
    
        cloudsynccreate["source"]['cifs']['host'] = srcdetails['server']
        cloudsynccreate["source"]['cifs']['share'] = '/'+srcdetails['share']
        cloudsynccreate["source"]['cifs']['path'] = srcdetails['deeppath']
        cloudsynccreate["source"]['cifs']['version'] = srcdetails['version']
        cloudsynccreate["source"]['cifs']['credentials'] = srcdetails['credentials']

        if not srcdetails['credentials']:
            logging.error('no credentials found for src: '+src+' please add entry to:'+cloudsynccredentialsfile)        
            exit(1)
            
        cloudsynccreate['sourceCredentials']['cifs'] = srcdetails['credentials']
    if dstdetails['type'] == 'cifs':
        del cloudsynccreate["settings"]['objectTagging']
        del cloudsynccreate['encryption']
        
        if cloudsynccreate["settings"]['files']["excludeExtensions"][0] == "string": del cloudsynccreate["settings"]['files']["excludeExtensions"]

        if cloudsynccreate["settings"]['files']["minDate"] == "string": del cloudsynccreate["settings"]['files']["minDate"]
        if cloudsynccreate["settings"]['files']["maxDate"] == "string": del cloudsynccreate["settings"]['files']["maxDate"]
        
        del cloudsynccreate["target"]['cifs']['workingEnvironmentId']

        cloudsynccreate["target"]['cifs']['host'] = dstdetails['server']
        cloudsynccreate["target"]['cifs']['share'] = '/'+dstdetails['share']
        cloudsynccreate["target"]['cifs']['path'] = dstdetails['deeppath']
        cloudsynccreate["target"]['cifs']['version'] = dstdetails['version']
        if not dstdetails['credentials']:
            logging.error('no credentials found for dst: '+dst+' please add entry to:'+cloudsynccredentialsfile)  
            exit(1)        
        cloudsynccreate["target"]['cifs']['credentials'] = dstdetails['credentials']
        cloudsynccreate['targetCredentials']['cifs'] = dstdetails['credentials']

    if srcdetails['type'] == 'local': 
        cloudsynccreate["source"]['local']['path'] = srcdetails['path']
    if dstdetails['type'] == 'local': 
        cloudsynccreate["target"]['local']['path'] = dstdetails['path']

    #create relationship with s3 
    if srcdetails['type'] == 's3': 
        del cloudsynccreate["source"]['s3']
        cloudsynccreate["source"]['s3'] = {}
        cloudsynccreate["source"]['s3'] = srcdetails
        
        if not srcdetails['credentials']:
            logging.error('no keys found for src:'+src+' please add entry to:'+cloudsynccredentialsfile)           
            exit(1)
        cloudsynccreate['sourceCredentials']['s3'] = srcdetails['credentials']

    if dstdetails['type'] == 's3': 
        del cloudsynccreate["target"]['s3']
        cloudsynccreate["target"]['s3'] = {}
        cloudsynccreate["target"]['s3'] = dstdetails
        cloudsynccreate['targetCredentials']['s3'] = dstdetails['credentials']
        if not dstdetails['credentials']:
            logging.error('no keys found for dst:'+dst+' please add entry to:'+cloudsynccredentialsfile)           
            exit(1)        

        del cloudsynccreate["settings"]['objectTagging']
        del cloudsynccreate['encryption']
        
        if cloudsynccreate["settings"]['files']["excludeExtensions"][0] == "string": del cloudsynccreate["settings"]['files']["excludeExtensions"]

        if cloudsynccreate["settings"]['files']["minDate"] == "string": del cloudsynccreate["settings"]['files']["minDate"]
        if cloudsynccreate["settings"]['files']["maxDate"] == "string": del cloudsynccreate["settings"]['files']["maxDate"]
        
    #create the relationship 
    accountid = getaccountid(user,account)
    createresult = cloudsyncapicall(user,account,'relationships-v2','POST',{'x-account-id':accountid},cloudsynccreate)

def abortcloudsyncrelationship(user,account,group,src,dst):
    logging.info('abort sync fo cloudsync relationship from src: '+src+' to dst: '+dst)
    relinfo = getcloudsyncrelationship (user,account,group,src,dst)

    if relinfo:
        relid = relinfo['relationshipId']
        if relinfo['activity']['status'] != 'RUNNING':
            logging.info('sync is not currently running for src: '+src+' to dst: '+dst)
            exit(0)
        accountid = getaccountid(user,account)
        abortcresult = cloudsyncapicall(user,account,'relationships/'+relid+'/abort','PUT',{'x-account-id':accountid}) 

def synccloudsyncrelationship(user,account,group,src,dst):
    logging.info('issue sync fo cloudsync relationship from src: '+src+' to dst: '+dst)
    relinfo = getcloudsyncrelationship (user,account,group,src,dst)
    
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
        newbytes = 0
        fatalerror = False
        while True:
            count+=1
            relinfo = getcloudsyncrelationship (user,account,group,src,dst,relid)
            currenttime = time.time()
            timespan = currenttime-starttime

            hours,timespan = divmod(timespan, 3600)
            minutes,timespan = divmod(timespan, 60)
            seconds = timespan
            if seconds < 1: seconds=1
            timestr = str(int(hours))+'h'+str(int(minutes))+'m'+str(int(seconds))+'s'  
            brkname = getbrokernamebyid(user,account,relinfo['dataBroker'])
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
            errors += relinfo['activity']['dirsFailedToScan'] 

            filesremove = relinfo['activity']['filesRemoved']
            dirsremove = relinfo['activity']['dirsRemoved']
            bytescopied = relinfo['activity']['bytesCopied']

            newbytes = bytescopied

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

            logging.info(f"broker:{brkname} {scanned:,} scanned, {copied:,} copied, {modified:,} modification, {errors:,} errors, {filesremove:,} file.gone, {dirsremove:,} dir.gone, {bw} {bwqunatifier} out ({bws} {bwsquantifier}) {timestr}")

            if not relinfo['activity']['status'] == 'RUNNING': break
            time.sleep(10)
        
        if relinfo['activity']['filesFailed'] > 0 or relinfo['activity']['dirsFailed'] > 0 or relinfo['activity']['dirsFailedToScan'] > 0:
            logging.error(f"encountered {errors} errors during sync")
            logging.error("top 5 errors during sync operation (detailed logs can be downloaded from cloudsync portal):")
            for err in relinfo['activity']['topFiveMostCommonRelationshipErrors']:
                desc = ''
                if 'description' in err: desc = err['description']
                if "The specified bucket does not exist" in desc: fatalerror = True
                if "Bucket names cannot contain" in desc: fatalerror = True
                logging.error(f"count: {err['counter']} step: {err['step']} errorCode: {err['errorCode']} description: {desc}")
            
        if relinfo['activity']['status'] == 'FAILED':
            errormsg = relinfo['activity']['failureMessage']
            logging.error('cloudsync sync failed for:'+src+' to dst: '+dst+' with error:'+errormsg)
            exit(1)
        elif fatalerror:
            logging.error('cloudsync sync failed with fatal error for src:'+src+' to dst: '+dst)
            exit(1)
        else:
            logging.info("job completed successfuly")
            
    else:
        logging.error('could not find cloudsync relationship for:'+src+' to dst: '+dst)

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
                        
def deleterelationship (user,account,group,src,dst,force=False):
    logging.warning('deleting cloudsync relationship from src: '+src+' to dst: '+dst)
    relinfo = getcloudsyncrelationship (user,account,group,src,dst)
    
    accountid = getaccountid(user,account)   
    
    if not relinfo:
        logging.warning('cloudsync relationship could not be found') 
    else:
        if relinfo['activity']['status'] == 'RUNNING':
            logging.error('relationship sync is currently running for src: '+src+' to dst: '+dst)
            exit(1)
            
        if not force:
            if not query_yes_no('are you sure you want to delete relationship from src: '+src+' to dst: '+dst+' ?'):
                exit(0)
        relid = relinfo['relationshipId']
        deleteresult = cloudsyncapicall(user,account,'relationships/'+relid,'DELETE',{'x-account-id':accountid}) 

def baselinerelation (user,account,group,src,dst,force=False):
    relinfo = getcloudsyncrelationship (user,account,group,src,dst)
    if relinfo and not force:
        logging.warning('reusing existing cloudsync relationship from src: '+src+' to dst: '+dst) 
        synccloudsyncrelationship(user,account,group,src,dst)
    elif relinfo and force:
        deletecloudsyncrelationship(user,account,group,src,dst)
        createcloudsyncrelationship(user,account,group,src,dst)
        synccloudsyncrelationship(user,account,group,src,dst)
    else:
        createcloudsyncrelationship(user,account,group,src,dst)
        synccloudsyncrelationship(user,account,group,src,dst)

def exportcloudsyncrelationship (user,account,group,src,dst):
    relinfo = getcloudsyncrelationship (user,account,group,src,dst,False,True)
    print(json.dumps(relinfo,indent=4))

def validatecloudsyncrelationship (user,account,group,src,dst):
    relinfo = getcloudsyncrelationship (user,account,group,src,dst)
    print(json.dumps(relinfo,indent=4))


#################################################################
## Main
#################################################################

parseapifile()

if args.subparser_name == 'create':
    relinfo = validaterelationship(args.source,args.destination)
    createcloudsyncrelationship(relinfo['user'],relinfo['account'],relinfo['group'],relinfo['srcpath'],relinfo['dstpath'])
if args.subparser_name == 'baseline':
    relinfo = validaterelationship(args.source,args.destination)
    baselinerelation(relinfo['user'],relinfo['account'],relinfo['group'],relinfo['srcpath'],relinfo['dstpath'],args.force)
if args.subparser_name == 'delete':
    relinfo = validaterelationship(args.source,args.destination)
    deleterelationship(relinfo['user'],relinfo['account'],relinfo['group'],relinfo['srcpath'],relinfo['dstpath'],args.force)
if args.subparser_name == 'sync':
    relinfo = validaterelationship(args.source,args.destination)
    synccloudsyncrelationship(relinfo['user'],relinfo['account'],relinfo['group'],relinfo['srcpath'],relinfo['dstpath'])
if args.subparser_name == 'abort':
    relinfo = validaterelationship(args.source,args.destination)
    abortcloudsyncrelationship(relinfo['user'],relinfo['account'],relinfo['group'],relinfo['srcpath'],relinfo['dstpath'])
if args.subparser_name == 'validate':
    relinfo = validaterelationship(args.source,args.destination)
    validatecloudsyncrelationship(relinfo['user'],relinfo['account'],relinfo['group'],relinfo['srcpath'],relinfo['dstpath'])
if args.subparser_name == 'export':
    exportcloudsyncrelationship(args.user,args.account,args.group,args.source_type,args.destination_type)
    
