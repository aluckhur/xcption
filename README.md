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
    delete              delete existing config

optional arguments:
  -h, --help            show this help message and exit
  -d, --debug           log debug messages to console

```
#There are 2 options to create xcption jobs: 
1.  manual csv creation 
2.  automatic assessment of existing filesystem 

**manual CSV creation**

a CSV file with the jobs should be created with the following columns:

`JOB NAME` - A name for the JOB, later on actions and output can be filtered by this name

`SOURCE PATH` - Source NFSv3 path. The source should be mountable as root from all instances in the cluster

`DEST PATH` - Destination NFSv3 path. The source should be mountable as root from all instances in the cluster

`SYNC SCHED` (optional) - sync schedule in [cron](http://www.nncron.ru/help/EN/working/cron-format.htm) format (DEFAULT is daily @ midnight:`0 0 * * * *`)

`CPU MHz` (optional) - The allocated CPU frequency for the job (DEFAULT:3000)

`RAM MB` (optional) - The allocated RAM for the job (DEFAULT:800)

**assessment of existing filesystem**
Automatic assessment of the source file, preperation of the destination filesytem and creation of the csv file can be achived using the `assess` command.

for example if our source volume directory structure 

├── folder1
│   ├── subfolder1
│   ├── subfolder2
│   └── subfolder3
├── folder2
│   ├── subfolder1
│   ├── subfolder2
│   └── subfolder3
└── folder3
    ├── subfolder1
    └── subfolder2


**example for the CSV file:**


```
#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB
test1,192.168.100.2:/xcp/src1,192.168.100.3:/xcp/dst1,*/3 * * * *,100,800
test2,192.168.100.2:/xcp/src2,192.168.100.4:/xcp/dst2,*/4 * * * *,100,800
test2,192.168.100.2:/xcp/src3,192.168.100.4:/xcp/dst3,*/5 * * * *,100,800
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

**To see the job status use the `status` command**

```
user@master:~/xcption# sudo ./xcption.py status
 Job    Source Path              Dest Path                Baseline Status  Baseline Time  Sync Status  Next Sync  Sync Time  Node    Sync #
 test1  192.168.100.2:/xcp/src1  192.168.100.3:/xcp/dst1  complete         1s             idle         00:01:34   1s         slave2  32
 test2  192.168.100.2:/xcp/src2  192.168.100.4:/xcp/dst2  complete         2s             failed       00:03:34   1s         slave2  24
 test2  192.168.100.2:/xcp/src3  192.168.100.4:/xcp/dst3  complete         2s             idle         00:00:34   2s         slave2  19

```
verbose output for specific job

```
user@master:~/xcption#sudo ./xcption.py status -v -s 192.168.100.2:/xcp/src2
JOB:test2
SRC:192.168.100.2:/xcp/src2
DST:192.168.100.4:/xcp/dst2
SYNC CRON:*/4 * * * *
NEXT SYNC:00:02:21
 Phase     Start Time           End Time             Duration  Scanned  Copied  Modified  Deleted  Errors  Node    Status
 baseline  2019-03-24 09:49:26  2019-03-24 09:49:28  2s        1,108    1,107   0         0        0       slave2  complete
 sync1     2019-03-24 09:50:15  2019-03-24 09:50:16  1s        1,211    202     0         1,006    0       slave2  complete
 sync2     2019-03-24 09:52:00  2019-03-24 09:52:00  0s        507      202     0         303      0       slave2  complete
 sync3     2019-03-24 09:56:00  2019-03-24 09:56:01  1s        559      353     0         202      0       slave2  complete
 sync4     2019-03-24 10:00:00  2019-03-24 10:00:01  1s        557      202     0         353      0       slave2  complete
 sync5     2019-03-24 10:04:00  2019-03-24 10:04:00  0s        406      202     0         202      0       slave2  complete
 sync6     2019-03-24 10:08:00  2019-03-24 10:08:01  1s        1,321    1,108   0         202      0       slave2  complete
 sync7     2019-03-24 10:12:00  2019-03-24 10:12:01  1s        1,617    504     0         1,108    0       slave2  complete
 sync8     2019-03-24 12:04:26  2019-03-24 12:04:28  1s        1,326    813     0         504      0       slave2  complete
 sync9     2019-03-24 12:08:00  2019-03-24 12:08:01  1s        1,783    968     0         606      0       slave2  complete
 sync10    2019-03-24 12:12:00  2019-03-24 12:12:01  1s        1,592    1,006   0         570      0       slave2  complete
 sync11    2019-03-24 17:16:01  2019-03-24 17:16:02  -         0        0       0         0        0       slave2  failed
 sync12    2019-03-25 06:16:38  2019-03-25 06:16:39  -         0        0       0         0        0       slave2  failed
 sync13    2019-03-25 06:20:00  2019-03-25 06:20:00  -         0        0       0         0        0       slave2  failed
 sync14    2019-03-25 06:24:00  2019-03-25 06:24:00  -         0        0       0         0        0       slave2  failed
 sync15    2019-03-25 06:28:00  2019-03-25 06:28:00  -         0        0       0         0        0       slave2  failed
 sync16    2019-03-25 06:32:00  2019-03-25 06:32:00  -         0        0       0         0        0       slave2  failed
 sync17    2019-03-25 06:36:00  2019-03-25 06:36:00  -         0        0       0         0        0       slave2  failed
 sync18    2019-03-25 06:40:00  2019-03-25 06:40:00  -         0        0       0         0        0       slave2  failed
 sync19    2019-03-25 06:44:00  2019-03-25 06:44:00  -         0        0       0         0        0       slave2  failed
 sync20    2019-03-25 06:48:00  2019-03-25 06:48:00  -         0        0       0         0        0       slave2  failed
 sync21    2019-03-25 06:52:00  2019-03-25 06:52:00  -         0        0       0         0        0       slave2  failed
 sync22    2019-03-25 06:56:00  2019-03-25 06:56:01  -         0        0       0         0        0       slave2  failed
 sync23    2019-03-25 07:00:00  2019-03-25 07:00:00  -         0        0       0         0        0       slave2  failed
 sync24    2019-03-25 07:04:00  2019-03-25 07:04:00  -         0        0       0         0        0       slave2  failed

```

*To see xcp logs for specific phase of a job use th -p <phase> flag**

```
user@master:~/xcption# sudo ./xcption.py status -v -s 192.168.100.2:/xcp/src2 -l -p sync11
JOB:test2
SRC:192.168.100.2:/xcp/src2
DST:192.168.100.4:/xcp/dst2
SYNC CRON:*/4 * * * *
NEXT SYNC:00:01:11
 Phase   Start Time           End Time             Duration  Scanned  Copied  Modified  Deleted  Errors  Node    Status
 sync11  2019-03-24 17:16:01  2019-03-24 17:16:02  -         0        0       0         0        0       slave2  failed

XCP 1.4-17914d6; (c) 2019 NetApp, Inc.; Licensed to haim marko [NetApp Inc] until Sat Jun  1 00:44:36 2019

xcp: WARNING: CPU count is only 2!
xcp: Index: {source: 192.168.100.2:/xcp/src2, target: 192.168.100.4:/xcp/dst2}


xcp: mount '192.168.100.2:/xcp/src2': WARNING: This NFS server only supports 1-second timestamp granularity. This may cause sync to fail because changes will often be undetectable.
xcp: mount '192.168.100.4:/xcp/dst2': WARNING: This NFS server only supports 1-second timestamp granularity. This may cause sync to fail because changes will often be undetectable.
xcp: diff '192.168.100.2-_xcp_src2-192.168.100.4-_xcp_dst2': Found 5 completed directories and 5 in progress
xcp: sync '192.168.100.2-_xcp_src2-192.168.100.4-_xcp_dst2': 410 reviewed, 1 checked at source, 409 gone, 9 dir.gone, 400 file.gone, 1 modification, 132 KiB in (358 KiB/s), 57.9 KiB out (158 KiB/s), 0s.
xcp: sync '192.168.100.2-_xcp_src2-192.168.100.4-_xcp_dst2': Starting search pass for 6 modified/in-progress directories...
xcp: sync phase 2: Rereading the 1 modified/in-progress directory...
xcp: rd '192.168.100.4:/xcp/dst2' fileid 514531: WARNING: nfs3 READDIRPLUS '192.168.100.4:/xcp/dst2' cookie 0 maxcount 65536: nfs3 error 70: stale filehandle
xcp: ERROR: nfs3 READDIRPLUS '192.168.100.4:/xcp/dst2' cookie 0 maxcount 65536: nfs3 error 70: stale filehandle

```