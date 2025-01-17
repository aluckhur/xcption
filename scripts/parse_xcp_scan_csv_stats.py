#!/usr/bin/env python3

import csv, json, os, sys, re

def parse_xcp_scan(csvpath):
    
    #this will host the parsed output stas 
    stats = {}
    #this will host the phase1 initial parsing 
    phase1_parse = []
    
    with open(csvpath, 'r') as csvfile:
        reader = csv.reader(csvfile)
        for row in enumerate(reader):
            linearr = row[1]
            if len(linearr):
                # if not linearr[0] in stats:
                #     stats[linearr[0]] = {}
                phase1_parse.append(linearr)
    #key values that are in single line
    single_lines = ['Total count','Directories','Regular files','Symbolic links','Special files','Hard links','Multilink files',
                    'Space Saved by Hard links (KB)','Sparse data','Dedupe estimate','Total space used']
    #key values that are in triple line
    triple_lines = ['Accessed','Modified','Changed','Top File Extensions']
    #key values that split to 2 lines 
    dual_lines = ['Maximum Values','Average Values','Top Space Users','Top File Owners',
                       'Number of files','Space used','Directory entries','Depth','Path']
    #key values used for multiple key/value per line 
    total_lines = ['Total space for regular files','Total space for symlinks','Total space for directories']

    count1 = 0
    while count1 < len(phase1_parse):
        linearr = phase1_parse[count1]
        if linearr[0].startswith('scan '):
            stats['path'] = linearr[0].replace('scan ','')
            stats['export'] = stats['path'].split(':')[1]
            stats['nfsserver'] = stats['path'].split(':')[0]
        elif linearr[0].startswith('summary'):
            time = linearr[1].replace('"','').split()[-1].replace(".","")
            matchObj = re.search("(\d+)m(\d+)s",time)
            if matchObj:
                stats['time'] = int(matchObj.group(1))*60+int(matchObj.group(2))
            matchObj = re.search("(\d+)h(\d+)m",time)
            if matchObj:
                stats['time'] = int(matchObj.group(1))*60*60+int(matchObj.group(2))*60                          
            matchObj = re.search("^(\d+)s",time) 
            if matchObj:
                stats['time'] = int(matchObj.group(1))
        elif linearr[0] in dual_lines:
            stats[linearr[0]] = {}
            count2 = 1
            for val in linearr[1:]:
                if not val in stats[linearr[0]]:
                    stats[linearr[0]][val] = phase1_parse[count1+1][count2]
                count2+=1
            count1 += 1
        elif linearr[0] in triple_lines:
            stats[linearr[0]] = {}
            count2 = 1
            for val in linearr[1:]:
                if not val in stats[linearr[0]]:
                    stats[linearr[0]][val] = {} 
                    stats[linearr[0]][val]['count'] = phase1_parse[count1+1][count2]
                    stats[linearr[0]][val]['size'] = phase1_parse[count1+2][count2]
                count2+=1
            count1 += 2            
        elif linearr[0] in single_lines:
            stats[linearr[0]]=linearr[1]
            if not stats[linearr[0]].isnumeric():
                stats[linearr[0]] = None
        elif linearr[0] in total_lines:
            stats[linearr[0]] = {}
            stats[linearr[0]]['size'] = linearr[2]
            stats[linearr[0]]['used'] = linearr[4]

        count1+=1

    return(stats)     
            
#csvpath = '/mnt/c/Temp/XCP'
csvpath = sys.argv[1]

outobj = []

for filename in os.listdir(csvpath):
    csvfile = os.path.join(csvpath, filename)
    outobj.append(parse_xcp_scan(csvfile))

print(json.dumps(outobj))