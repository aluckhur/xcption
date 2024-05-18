#!/usr/bin/env python3

import json, os, sys, re, csv

def parse_xcp_status_exports(path):
    
    #this will host the parsed output stas 
    out = {}
    #this will host the phase1 initial parsing 
    phase1_parse = []

    file1 = open(file, 'r')
    lines = file1.readlines()    

    count1 = 0
    
    #used to flag start of general export information 
    export_start = False

    all_exports = []
    while count1 < len(lines):
        line = lines[count1]
        if "Mounts  Errors  Server" in line: 
            count1 += 1
            matchObj = re.search("(\d+)\s+(\d+)\s+(\S+)",lines[count1])
            if matchObj:
                out['mounts'] = matchObj.group(1) 
                out['errors'] = matchObj.group(2) 
                out['server'] = matchObj.group(3) 
        
        #get export names
        if re.search(r"Free\s+Free\s+Used\s+Used Export",lines[count1]):
            export_start = True 


        if export_start:
            matchObj = re.search("^\s+([+-]?([0-9]+([.][0-9]*)?|[.][0-9]+))\s+(.iB).+\s+(\S+)\:\/?(\S+)\s*$",lines[count1])
            
            if matchObj:
                details = lines[count1].split()
                free_space = f"{details[0]}{details[1]}"
                used_space = f"{details[3]}{details[4]}"
                free_files = details[2]
                used_files = details[5]
                if matchObj.group(6) == '/':
                    export = matchObj.group(5)+':/'
                else:
                    export = matchObj.group(5)+':/'+matchObj.group(6)

                if not 'exports_info' in out:
                    out['exports_info'] = {}    
                out['exports_info'][export] = {"free_space":free_space, "used_space": used_space, "free_files": free_files, "used_files": used_files}
        
        #go to next line
        count1+=1

    return(out)

def print_csv(obj):

    f = open('/tmp/out.csv', 'w')
    writer = csv.writer(f)

    header = ['server','export','free_space','used_space','free_files','used_files']
    writer.writerow(header)

    for fileserver in obj:
        if not 'server' in fileserver:
            continue
        server = fileserver['server']
        for export in fileserver['exports_info']:
            export_name = export 
            row = [server,export_name,fileserver['exports_info'][export_name]['free_space'],fileserver['exports_info'][export_name]['used_space'],fileserver['exports_info'][export_name]['free_files'],fileserver['exports_info'][export_name]['used_files']]
            writer.writerow(row)
            


path = sys.argv[1]
output_format = 'json'
if len(sys.argv) > 2:
    output_format = sys.argv[2]

outobj = []

for filename in os.listdir(path):
    file = os.path.join(path, filename)
    outobj.append(parse_xcp_status_exports(file))
if output_format == 'csv':
    print_csv(outobj)
else:
    print(json.dumps(outobj))
