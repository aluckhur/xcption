# xcption

## What is XCPtion?

XCPtion is a wrapper utility for [NetApp XCP](https://xcp.netapp.com/) NFS file copy/migration utility
XCPtion will be able to run and manage multiple XCP jobs parallelly in a distributed fashion by using underlying services from Hashi Corp [Nomad](https://www.nomadproject.io/) distributed scheduler.

## Where do I get XCPtion?

XCPtion is currently available at [GitLab Repository](https://gitlab.com/haim.marko/xcption)
You will need to apply for XCP license from: [XCP License Site](https://xcp.netapp.com/) and download the XCP binary from: [NetApp Support Site](https://mysupport.netapp.com/tools/info/ECMLP2357425I.html?productID=62115&pcfContentID=ECMLP2357425)

## Installation

XCPtion can be installed directly on internet connected Ubunto/CentOS/RedHat server by pulling the reposoity files using the command:

*ALL instances should be pulled to the same path on all of the servers !!!*

`git pull https://gitlab.com/haim.marko/xcption.git`

Before starting the setup, NFS accessed volume with root access should be prepared for the XCP repository. The volume should be exported to all servers that are going to be part of the migration cluster. The size is dependent on the number of files (good practice will be to allocate ~50G for the repository)

Deployment on the 1st host in the cluster should be done using the command (-r should point to the preconfigured repository)

`sudo ./xcption/system/xcption_deploy.sh -r x.x.x.x:/vol/folder -t server`

Deployment of the next hosts in the cluster should be done using the command (pointing to the server IP address):

`sudo ./xcption/system/xcption_deploy.sh -r x.x.x.x:/vol/folder -t client -s <Server IP>`

Following the installation **on all hosts** the xcp license file should be copied to the following location:

`/opt/NetApp/xFiles/xcp/license`

Updates to the xcp binary can be done by replacing the existing file in the following location **on all hosts**
`/usr/local/bin/xcp`


## How To Use

The interaction is done using the following python CLI command (need root access)

```
usage: xcption.py [-h] [-d]
                  {status,load,baseline,sync,syncnow,pause,resume,delete} ...

positional arguments:
  {status,asess,load,baseline,sync,syncnow,pause,resume,delete}
                        sub commands that can be used
    status              display status
    assess              assess fielsystem and create csv file
    load                load/update configuration from csv file
    baseline            start baseline (xcp copy)
    sync                start schedule updates (xcp sync)
    syncnow             initiate sync now
    pause               disable sync schedule
    resume              resume sync schedule
    verify              start verify to validate consistancy between source
                        and destination (xcp verify)    
    delete              delete existing config

optional arguments:
  -h, --help            show this help message and exit
  -d, --debug           log debug messages to console

```

**There are 2 options to create xcption jobs:**

**1.  manual CSV creation**

a CSV file with the jobs should be created with the following columns:

`JOB NAME` - A name for the JOB, later on actions and output can be filtered by this name  
`SOURCE PATH` - Source NFSv3 path. The source should be mountable as root from all instances in the cluster  
`DEST PATH` - Destination NFSv3 path. The source should be mountable as root from all instances in the cluster  
`SYNC SCHED` (optional) - sync schedule in [cron](http://www.nncron.ru/help/EN/working/cron-format.htm) format (DEFAULT is daily @ midnight:`0 0 * * * *`)  
`CPU MHz` (optional) - The allocated CPU frequency for the job (DEFAULT:3000)  
`RAM MB` (optional) - The allocated RAM for the job (DEFAULT:800)  

CSV file example:
```
#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB
test1,192.168.100.2:/xcp/src1,192.168.100.3:/xcp/dst1,*/3 * * * *,100,800
test2,192.168.100.2:/xcp/src2,192.168.100.4:/xcp/dst2,*/4 * * * *,100,800
test2,192.168.100.2:/xcp/src3,192.168.100.4:/xcp/dst3,*/5 * * * *,100,800
```

**2. assessment of existing filesystem**

Automatic assessment of the source file, preperation of the destination filesytem and creation of the csv file can be achived using the `assess` command.

for example if our source file system directory structure upto depth of 2 look as follows (bellow the subfolders we have many other file adn directorye). 

```
 ├── folder1  
 │   ├── subfolder1  
 │   ├── subfolder2  
 │   └── subfolder3  
 ├── folder2  
 │   ├── subfolder1  
 │   ├── subfolder2  
 │   └── subfolder3  
 └── folder3  
     ├── subfolder1  
     └── subfolder2  
```
we can use the `assess` command to build this initial directory structure on the destination volume and automaticaly create the xcption csv file for us.
xcption will analyse the source file system, will validate destination filesystem is not already contains the same paths as the source and will create the initial filesystem on the destination (using rsync).
**directory structure created using rsync will not be updated to the destination if new files/directories are created bellow the paths manged by xcption jobs 
for example if a file is created under /src/folder1/ it should be manualy updqted to the destination**

```
user@master:~/xcption$ sudo ./xcption.py assess -h
usage: xcption.py assess [-h] -s SOURCE -d DESTINATION -l DEPTH -c CSVFILE [-j jobname]

optional arguments:
  -h, --help                                  show this help message and exit
  -s SOURCE, --source SOURCE                  source nfs path (nfssrv:/mount)
  -d DESTINATION, --destination DESTINATION   destintion nfs path (nfssrv:/mount)
  -l DEPTH, --depth DEPTH                     filesystem depth to create jobs, range of 1-12
  -c CSVFILE, --csvfile CSVFILE               output CSV file
  -j jobname, --job jobname                   xcption job name
```

Example of running asses for the above filesystem:

```
user@master:~/xcption$ sudo ./xcption.py assess -s 192.168.100.2:/xcp/src -d 192.168.100.2:/xcp/dst -l 2 -c example/src.csv -j src_job
2019-04-12 10:26:12,044 - INFO - destination dir: 192.168.100.2:/xcp/dst/ for source dir: 192.168.100.2:/xcp/src/ already exists but empty
2019-04-12 10:26:12,049 - INFO - job csv file:example/src.csv created
2019-04-12 10:26:12,049 - INFO - rsync can be used to create the destination initial directory structure for xcption jobs
2019-04-12 10:26:12,049 - INFO - rsync command to sync directory structure for the required depth will be:
2019-04-12 10:26:12,049 - INFO - rsync -av --stats --exclude="/*/*/*" "/tmp/src_15693/" "/tmp/dst_15693/"
2019-04-12 10:26:12,050 - INFO - (192.168.100.2:/xcp/src is mounted on:/tmp/src_15693 and 192.168.100.2:/xcp/dst is mounted on:/tmp/dst_15693)
do you want to run rsync ? [y/N] y
2019-04-12 10:26:13,674 - INFO - =================================================================
2019-04-12 10:26:13,674 - INFO - ========================Starting rsync===========================
2019-04-12 10:26:13,675 - INFO - =================================================================
sending incremental file list
./
folder1/
folder1/subfolder1/
folder1/subfolder2/
folder1/subfolder3/
folder2/
folder2/subfolder1/
folder2/subfolder2/
folder2/subfolder3/
folder3/
folder3/subfolder1/
folder3/subfolder2/

Number of files: 12 (dir: 12)
Number of created files: 11 (dir: 11)
Number of deleted files: 0
Number of regular files transferred: 0
Total file size: 0 bytes
Total transferred file size: 0 bytes
Literal data: 0 bytes
Matched data: 0 bytes
File list size: 0
File list generation time: 0.001 seconds
File list transfer time: 0.000 seconds
Total bytes sent: 361
Total bytes received: 63

sent 361 bytes  received 63 bytes  848.00 bytes/sec
total size is 0  speedup is 0.00
2019-04-12 10:26:13,707 - INFO - =================================================================
2019-04-12 10:26:13,708 - INFO - ===================rsync ended successfully======================
2019-04-12 10:26:13,708 - INFO - =================================================================
2019-04-12 10:26:13,708 - INFO - csv file:example/src.csv is ready to be loaded into xcption
```


**example for the CSV file created by the assess command:**

```
#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB
src_job,192.168.100.2:/xcp/src/folder2/subfolder2,192.168.100.2:/xcp/dst/folder2/subfolder2,0 0 * * * *,3000,800
src_job,192.168.100.2:/xcp/src/folder2/subfolder3,192.168.100.2:/xcp/dst/folder2/subfolder3,0 0 * * * *,3000,800
src_job,192.168.100.2:/xcp/src/folder2/subfolder1,192.168.100.2:/xcp/dst/folder2/subfolder1,0 0 * * * *,3000,800
src_job,192.168.100.2:/xcp/src/folder1/subfolder2,192.168.100.2:/xcp/dst/folder1/subfolder2,0 0 * * * *,3000,800
src_job,192.168.100.2:/xcp/src/folder1/subfolder3,192.168.100.2:/xcp/dst/folder1/subfolder3,0 0 * * * *,3000,800
src_job,192.168.100.2:/xcp/src/folder1/subfolder1,192.168.100.2:/xcp/dst/folder1/subfolder1,0 0 * * * *,3000,800
src_job,192.168.100.2:/xcp/src/folder3/subfolder2,192.168.100.2:/xcp/dst/folder3/subfolder2,0 0 * * * *,3000,800
src_job,192.168.100.2:/xcp/src/folder3/subfolder1,192.168.100.2:/xcp/dst/folder3/subfolder1,0 0 * * * *,3000,800
```


**Following the creation of the csv file, the file should be loaded and validated using the `load` command:**

```
usage: xcption.py load [-h] -c CSVFILE [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -c CSVFILE, --csvfile CSVFILE
                        input CSV file with the following columns: Job
                        Name,SRC Path,DST Path,Schedule,CPU,Memory
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```



Example:
```
sudo user@master:~/xcption# ./xcption.py load -c example/test.csv
2019-03-25 07:02:03,217 - INFO - validating src:192.168.100.2:/xcp/src1 and dst:192.168.100.3:/xcp/dst1 are mountable
2019-03-25 07:02:03,813 - INFO - validating src:192.168.100.2:/xcp/src2 and dst:192.168.100.4:/xcp/dst2 are mountable
2019-03-25 07:02:04,459 - INFO - validating src:192.168.100.2:/xcp/src3 and dst:192.168.100.4:/xcp/dst3 are mountable
2019-03-25 07:02:05,116 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src1
2019-03-25 07:02:05,119 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src2
2019-03-25 07:02:05,121 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src3

```

**To run the baseline (xcp copy) the `baseline` command should be used**


```
usage: xcption.py baseline [-h] [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```


Example:
```
user@master:~/xcption# sudo ./xcption.py baseline 
2019-03-26 21:18:13,519 - INFO - starting/updating job:baseline_test1_192.168.100.2-_xcp_src1
2019-03-26 21:18:13,578 - INFO - starting/updating job:baseline_test2_192.168.100.2-_xcp_src2
2019-03-26 21:18:13,627 - INFO - starting/updating job:baseline_test2_192.168.100.2-_xcp_src3
```

**To schedule the incremantal updates (xcp sync) the `sync` command should be used (sync is possiable only when baseline is complete)**

```
usage: xcption.py sync [-h] [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```

Example:
```
user@master:~/xcption# sudo ./xcption.py sync -s 192.168.100.2:/xcp/src10
2019-03-14 15:07:18,663 - INFO - starting/updating job:sync_job1_192.168.100.2-_xcp_src10
```

**verification using xcp verify can be start if a job finished baseline 

```
user@master:~/xcption$ sudo ./xcption.py verify
2019-04-15 07:27:23,691 - INFO - starting/updating job:verify_job29786_192.168.100.2-_xcp_src1_f3
2019-04-15 07:27:23,763 - INFO - starting/updating job:verify_job29786_192.168.100.2-_xcp_src1_f2
2019-04-15 07:27:23,826 - INFO - starting/updating job:verify_job29786_192.168.100.2-_xcp_src1_f1

```

**To see the job status use the `status` command**

```


user@master:~/xcption# sudo ./xcption.py status

BL=Baseline CY=Sync VR=Verifya

Job       Source Path                 Dest Path              BL Status  BL Time  BL Sent   SY Status  Next SY   SY Time  SY Sent   SY#  VR Status  VR Start             VR Ratio  VR#
job29786  192.168.100.2:/xcp/src1/f3  192.168.100.2:/xcp/f3  complete   1s       1023 KiB  idle       16:32:31  0s       54.5 KiB  1    equal      2019-04-15 07:27:23  217/217   2
job29786  192.168.100.2:/xcp/src1/f2  192.168.100.2:/xcp/f2  complete   1s       60.2 KiB  idle       16:32:31  0s       19.2 KiB  1    equal      2019-04-15 07:27:23  4/4       2
job29786  192.168.100.2:/xcp/src1/f1  192.168.100.2:/xcp/f1  complete   4s       309 MiB   idle       16:32:31  0s       22.0 KiB  1    diff       2019-04-15 07:27:24  29/30     2


```

verbose output. can be filtered by specific job (-j), source (-s) and phase (-p)


```
user@master:~/xcption$ sudo ./xcption.py status -v
JOB: job29786
SRC: 192.168.100.2:/xcp/src1/f3
DST: 192.168.100.2:/xcp/f3
SYNC CRON: 0 0 * * * * (NEXT RUN 16:32:21)
XCP INDEX NAME: 192.168.100.2-_xcp_src1_f3-192.168.100.2-_xcp_f3

Phase     Start Time           End Time             Duration  Scanned  Copied  Modified  Deleted  Errors  Data Sent             Node    Status
baseline  2019-04-15 07:25:48  2019-04-15 07:25:49  1s        217      216     0         0        0       1023 KiB(901 KiB/s)   slave2  complete
sync1     2019-04-15 07:26:14  2019-04-15 07:26:15  0s        0        0       0         0        0       54.5 KiB(101 KiB/s)   slave2  complete
verify1   2019-04-15 07:26:56  2019-04-15 07:26:57  1s        217/217  0       0         0        0       31.5 KiB(31.0 KiB/s)  slave2  complete
verify2   2019-04-15 07:27:23  2019-04-15 07:27:24  0s        217/217  0       0         0        0       31.5 KiB(94.9 KiB/s)  slave2  complete


JOB: job29786
SRC: 192.168.100.2:/xcp/src1/f2
DST: 192.168.100.2:/xcp/f2
SYNC CRON: 0 0 * * * * (NEXT RUN 16:32:21)
XCP INDEX NAME: 192.168.100.2-_xcp_src1_f2-192.168.100.2-_xcp_f2

Phase     Start Time           End Time             Duration  Scanned  Copied  Modified  Deleted  Errors  Data Sent             Node    Status
baseline  2019-04-15 07:25:48  2019-04-15 07:25:49  1s        4        3       0         0        0       60.2 KiB(55.6 KiB/s)  master  complete
sync1     2019-04-15 07:26:14  2019-04-15 07:26:15  0s        0        0       0         0        0       19.2 KiB(43.0 KiB/s)  master  complete
verify1   2019-04-15 07:26:56  2019-04-15 07:26:56  0s        4/4      0       0         0        0       2.62 KiB(2.77 KiB/s)  master  complete
verify2   2019-04-15 07:27:23  2019-04-15 07:27:24  0s        4/4      0       0         0        0       2.62 KiB(9.86 KiB/s)  master  complete


JOB: job29786
SRC: 192.168.100.2:/xcp/src1/f1
DST: 192.168.100.2:/xcp/f1
SYNC CRON: 0 0 * * * * (NEXT RUN 16:32:21)
XCP INDEX NAME: 192.168.100.2-_xcp_src1_f1-192.168.100.2-_xcp_f1

Phase     Start Time           End Time             Duration  Scanned  Copied  Modified  Deleted  Errors             Data Sent             Node    Status
baseline  2019-04-15 07:25:48  2019-04-15 07:25:52  4s        29       28      0         0        0                  309 MiB(67.4 MiB/s)   slave1  complete
sync1     2019-04-15 07:26:15  2019-04-15 07:26:15  0s        0        0       0         0        0                  22.0 KiB(45.3 KiB/s)  slave1  complete
verify1   2019-04-15 07:26:56  2019-04-15 07:26:57  0s        29/29    0       0         0        0                  7.98 KiB(46.9 KiB/s)  slave1  complete
verify2   2019-04-15 07:27:24  2019-04-15 07:27:24  0s        29/30    0       0         0        1 (attr:0 time:1)  8.10 KiB(19.5 KiB/s)  slave1  diff

```

*To see xcp logs for specific phase of a job use th -p <phase> flag**

```
user@master:~/xcption# sudo ./xcption.py status -v -s 192.168.100.2:/xcp/src1/f1 -p verify2 -l
JOB: job29786
SRC: 192.168.100.2:/xcp/src1/f1
DST: 192.168.100.2:/xcp/f1
SYNC CRON: 0 0 * * * * (NEXT RUN 16:31:56)
XCP INDEX NAME: 192.168.100.2-_xcp_src1_f1-192.168.100.2-_xcp_f1

Phase    Start Time           End Time             Duration  Scanned  Copied  Modified  Deleted  Errors             Data Sent             Node    Status
verify2  2019-04-15 07:27:24  2019-04-15 07:27:24  0s        29/30    0       0         0        1 (attr:0 time:1)  8.10 KiB(19.5 KiB/s)  slave1  diff

XCP 1.4-17914d6; (c) 2019 NetApp, Inc.; Licensed to haim marko [NetApp Inc] until Sat Jun  1 00:44:36 2019

xcp: WARNING: CPU count is only 2!
xcp: mount '192.168.100.2:/xcp/src1/f1': WARNING: This NFS server only supports 1-second timestamp granularity. This may cause sync to fail because changes will often be undetectable.
xcp: mount '192.168.100.2:/xcp/f1': WARNING: This NFS server only supports 1-second timestamp granularity. This may cause sync to fail because changes will often be undetectable.
xcp: compare1 'file': WARNING: (error) source file not found on target: nfs3 LOOKUP 'file' in '192.168.100.2:/xcp/f1/f2': nfs3 error 2: no such file or directory
30 scanned, 29 found (3 have data), 1 different mod time, 1 error, 22.0 KiB in (53.0 KiB/s), 8.10 KiB out (19.5 KiB/s), 0s.
