#!/usr/bin/env python3

import json, os, sys, re, csv

def parse_xcp_status_shares(path):
    
    #this will host the parsed output stas 
    out = {}
    #this will host the phase1 initial parsing 
    phase1_parse = []

    file1 = open(file, 'r')
    lines = file1.readlines()    

    count1 = 0
    
    #used to flag start of general share information 
    share_start = path_start = share_end = 0 
    #used to flag start of share attributes 
    start_attributes = False 
    #used to flag start share acl 
    start_acl = False 
    current_share = ""

    shares_info_keys = dict()

    all_shares = []
    while count1 < len(lines):
        line = lines[count1]
        if "Shares  Errors  Server" in line: 
            count1 += 1
            matchObj = re.search("(\d+)\s+(\d+)\s+(\S+)",lines[count1])
            if matchObj:
                out['shares'] = matchObj.group(1) 
                out['errors'] = matchObj.group(2) 
                out['server'] = matchObj.group(3) 
        
        #get share names
        if re.search(r"Free\s+Used\s+Connections\s+Share Path\s+Folder Path",lines[count1]):
            share_start = line.find("Share Path ")
            path_start = line.find("Folder Path")
            share_end = path_start-1
            count1 += 1
        
        if all(val > 0 for val in [share_start,path_start,share_end]):
            if not re.search("^\s*$",lines[count1]):
                free_space = re.split(r'\s+',lines[count1])[1]
                used_space = re.split(r'\s+',lines[count1])[2]
                
                share_path_name = lines[count1][share_start:share_end].rstrip() 
                share_path_prefix = "\\\\"+out['server']+"\\"
                share_name = share_path_name[len(share_path_prefix):]
                share_folder_path = lines[count1][path_start:].rstrip() 
                # for debug
                # print(lines[count1])
                # print(json.dumps({"name": share_name, "share_folder_path": share_folder_path, "free_space":free_space, "used_space": used_space}))
                # exit(1)
                all_shares.append(share_name)

                if not 'shares_info' in out:
                    out['shares_info'] = {}
                if share_name.upper() != 'IPC$':
                    out['shares_info'][share_name] = {"share_folder_path": share_folder_path, "free_space":free_space, "used_space": used_space}
            else:
                share_start = path_start = share_end = 0 
        
        if re.search(r"^\s*Share\s+Types\s+Remark",lines[count1]):
            start_attributes = True
            count1 += 1
        
        if start_attributes:
            if not shares_info_keys:
                shares_info_keys = out['shares_info'].keys()

            if not re.search("^\s*$",lines[count1]):
                for share_name in shares_info_keys:
                    matchObj = re.search(f"{re.escape(share_name)}\s+(DISKTREE|SPECIAL)\s*(.*)$",lines[count1])
                    if matchObj:
                       out['shares_info'][share_name]['type'] = matchObj.group(1)
                       out['shares_info'][share_name]['comment'] = matchObj.group(2).rstrip()
            else:
                start_attributes = False

        
        if re.search(r"^\s*Share\s+Entity\s+Type",lines[count1]):
            start_acl = True
            count1 += 1        
        
        if start_acl and len(lines) != count1:
            #print(lines[count1])
            if re.search(r"^\s\S+\s+.+$",lines[count1].rstrip()):
                for share_name in out['shares_info'].keys():
                    matchObj = re.search(f"\s{re.escape(share_name)}\s+(.+)\s+(\S+\/.+)",lines[count1])
                    if matchObj:
                        if not 'acl' in out['shares_info'][share_name]:
                            out['shares_info'][share_name]['acl'] = []
                        out['shares_info'][share_name]['acl'].append({"user": matchObj.group(1).rstrip(), 
                                                                      "action": matchObj.group(2).rstrip().split('/')[0], 
                                                                      "permission": matchObj.group(2).rstrip().split('/')[1]
                                                                     })
                        current_share = share_name
            elif re.search("\s+(.+)\s+(\S+\/.+)",lines[count1].rstrip()) and current_share:  
                matchObj = re.search("\s+(.+)\s+(\S+\/.+)",lines[count1].rstrip())
                out['shares_info'][current_share]['acl'].append({"user": matchObj.group(1).rstrip(), 
                                                                "action": matchObj.group(2).rstrip().split('/')[0], 
                                                                "permission": matchObj.group(2).rstrip().split('/')[1]
                                                                })
           

        #go to next line
        count1+=1

    return(out)

def print_csv(obj):

    f = open('/tmp/out.csv', 'w')
    writer = csv.writer(f)

    header = ['server','share','folder','comment','acl user','action action','acl permission','free_space','used_space']
    writer.writerow(header)

    for fileserver in obj:
        if not 'server' in fileserver:
            continue
        server = fileserver['server']
        for share in fileserver['shares_info']:
            share_name = share 
            share_folder_path = fileserver['shares_info'][share_name]['share_folder_path']
            if 'comment' in fileserver['shares_info'][share_name]:
                comment = fileserver['shares_info'][share_name]['comment']
            else:
                comment = ''
            if 'acl' in fileserver['shares_info'][share_name]: 
                for acl in fileserver['shares_info'][share_name]['acl']:
                    raw = [server,share_name,share_folder_path,comment,acl['user'],acl['action'],acl['permission'],fileserver['shares_info'][share_name]['free_space'],fileserver['shares_info'][share_name]['used_space']]
                    writer.writerow(raw)
            else:
                raw = [server,share_name,share_folder_path,comment,'','','',fileserver['shares_info'][share_name]['free_space'],fileserver['shares_info'][share_name]['used_space']]
                writer.writerow(raw)
            


path = sys.argv[1]
output_format = 'json'
if len(sys.argv) > 2:
    output_format = sys.argv[2]

outobj = []

for filename in os.listdir(path):
    file = os.path.join(path, filename)
    outobj.append(parse_xcp_status_shares(file))
if output_format == 'csv':
    print_csv(outobj)
else:
    print(json.dumps(outobj))
