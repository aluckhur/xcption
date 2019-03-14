# xcption

## What is XCPtion?

XCPtion is a wrapper utility for [NetApp XCP](https://xcp.netapp.com/) NFS filecopy/migration utility
XCPtion will be able to run and manage multiple XCP jobs paralely in a distributed fasion by using underlying services from Hashi Corp [Nomad](https://www.nomadproject.io/) scheduler.

## Where do I get XCPtion?

XCPtion is currently available at [GitLab Repository](https://gitlab.com/haim.marko/xcption)
You will need to apply for XCP license from: [XCP License Site](https://xcp.netapp.com/) and download the XCP binary from: [NetApp Support Site](https://mysupport.netapp.com/tools/info/ECMLP2357425I.html?productID=62115&pcfContentID=ECMLP2357425)

## Installation

XCPtion can be installed directly on internet connected Ubunto 16.04 or 18.04 versions by pulling the reposoity files using the command:

`git pull https://gitlab.com/haim.marko/xcption.git`

Deployment on the 1st host in the cluster should be done using the command:

`sudo ./xcption/build/xcption_deploy.sh XCP_REPO=x.x.x.x:/vol/folder MODE=server`

Deplyment of the next hosts in the cluster should be done using the command (pointing to the server IP address):

`sudo ./xcption/build/xcption_deploy.sh XCP_REPO=x.x.x.x:/vol/folder MODE=client SERVER=<SERVER_IP_ADDRESS>`

Following the installation **on all hosts** the xcp license file should be copied to the following location:

`/opt/NetApp/xFiles/xcp/license`

Updates to the xcp binary can be done by replacing the existing file in the following location **on all hosts**
`/usr/local/bin/xcp`


## How To Use

The interaction is done using the following CLI python command (need root access)

```
usage: xcption.py [-h] -c CSVFILE [-d]
                  {status,load,baseline,sync,syncnow,pause,resume,delete} ...

positional arguments:
  {status,load,baseline,sync,syncnow,pause,resume,delete}
                        sub commands that can be used
    status              display status
    load                load/update configuration from csv file
    baseline            start baseline
    sync                initiate sync updates (scheuled)
    syncnow             initiate sync now
    pause               disable sync schedule
    resume              resume sync schedule
    delete              delete existing config

optional arguments:
  -h, --help            show this help message and exit
  -c CSVFILE, --csvfile CSVFILE
                        input CSV file with the following columns: Job
                        Name,SRC Path,DST Path,Schedule,CPU,Memory
  -d, --debug           log debug messages to console

```

All sub commands requires a CSV input file (-c/--csvfile) with the following columns: 

**JOB NAME** - A name for the JOB, later on actions and output can be filtered by this name

**SOURCE PATH** - Source NFSv3 path. The source should be mountable as root from all instances in the cluster 

**DEST PATH** - Destination NFSv3 path. The source should be mountable as root from all instances in the cluster 

**SYNC SCHED** (optional) - sync schedule in [cron](http://www.nncron.ru/help/EN/working/cron-format.htm) format (DEFAULT is daily @ midnight:`0 0 * * * *`)

**CPU MHz** (optional) - The allocated CPU frequency for the job (DEFAULT:3000)

**RAM MB** (optional) - The allocated RAM for the job (DEFAULT:800)


Example for the file:

#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB

job1,192.168.100.2:/xcp/src15,192.168.100.3:/xcp/dst15

job1,192.168.100.2:/xcp/src16,192.168.100.3:/xcp/dst16

job2,192.168.100.2:/xcp/src5,192.168.100.4:/xcp/dst5,*/15 * * * *,100,22800

job2,192.168.100.2:/xcp/src6,192.168.100.4:/xcp/dst6,*/20 * * * *,100,24400


**Following the creation of the csv file, the file should be loaded and validted using the command:**

```
usage: xcption.py load [-h] [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```


Example:
```
root@master:~/xcption# sudo ./xcption.py -c example/job.csv load -j job1
2019-03-14 15:04:07,646 - INFO - validating src:192.168.100.2:/xcp/src10 and dst:192.168.100.3:/xcp/dst10 are mountable
2019-03-14 15:04:07,986 - INFO - validating src:192.168.100.2:/xcp/src11 and dst:192.168.100.3:/xcp/dst11 are mountable
2019-03-14 15:04:08,343 - INFO - validating src:192.168.100.2:/xcp/src12 and dst:192.168.100.3:/xcp/dst12 are mountable
2019-03-14 15:04:08,698 - INFO - validating src:192.168.100.2:/xcp/src13 and dst:192.168.100.3:/xcp/dst13 are mountable
2019-03-14 15:04:09,093 - INFO - validating src:192.168.100.2:/xcp/src14 and dst:192.168.100.3:/xcp/dst14 are mountable
2019-03-14 15:04:09,481 - INFO - validating src:192.168.100.2:/xcp/src15 and dst:192.168.100.3:/xcp/dst15 are mountable
2019-03-14 15:04:09,852 - INFO - validating src:192.168.100.2:/xcp/src16 and dst:192.168.100.3:/xcp/dst16 are mountable
2019-03-14 15:04:10,195 - WARNING - job directory:/root/xcption/jobs/job1 - already exists
2019-03-14 15:04:10,195 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src14
2019-03-14 15:04:10,197 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src15
2019-03-14 15:04:10,198 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src16
2019-03-14 15:04:10,198 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src10
2019-03-14 15:04:10,199 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src11
2019-03-14 15:04:10,200 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src12
2019-03-14 15:04:10,201 - INFO - creating/updating relationship configs for src:192.168.100.2:/xcp/src13
```


**to initiate sync (incremental updates) the sync command should be used**

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
user@master:~/xcption# s@master:~/xcption# sudo ./xcption.py -c example/job.csv sync -s 192.168.100.2:/xcp/src10
2019-03-14 15:07:18,663 - INFO - starting/updating job:sync_job1_192.168.100.2-_xcp_src10
```

**to see the job status use the status command**

```
user@master:~/xcption# sudo ./xcption.py -c example/job.csv status
 Job   Source Path               Dest Path                 Baseline Status  Baseline Time  Sync Status  Next Sync  Sync Time  Node    Sync #
 job2  192.168.100.2:/xcp/src2   192.168.100.4:/xcp/dst2   complete         2s             idle         00:00:33   0s         slave1  37
 job2  192.168.100.2:/xcp/src3   192.168.100.4:/xcp/dst3   complete         2s             idle         00:00:33   0s         master  109
 job2  192.168.100.2:/xcp/src1   192.168.100.4:/xcp/dst1   complete         2s             idle         00:11:32   0s         master  7
 job2  192.168.100.2:/xcp/src6   192.168.100.4:/xcp/dst6   complete         2s             idle         00:11:32   0s         slave2  7
 job2  192.168.100.2:/xcp/src7   192.168.100.4:/xcp/dst7   complete         2s             idle         00:11:32   0s         slave1  7
 job2  192.168.100.2:/xcp/src4   192.168.100.4:/xcp/dst4   complete         2s             idle         00:01:32   0s         slave2  12
 job2  192.168.100.2:/xcp/src5   192.168.100.4:/xcp/dst5   complete         2s             idle         00:06:32   0s         slave2  9
 job2  192.168.100.2:/xcp/src8   192.168.100.4:/xcp/dst8   complete         2s             idle         00:11:32   0s         slave2  7
 job2  192.168.100.2:/xcp/src9   192.168.100.4:/xcp/dst9   complete         2s             idle         00:11:32   0s         slave2  7
 job1  192.168.100.2:/xcp/src14  192.168.100.3:/xcp/dst14  complete         5s             idle         08:51:32   0s         slave2  109
 job1  192.168.100.2:/xcp/src15  192.168.100.3:/xcp/dst15  complete         4s             idle         08:51:32   0s         master  109
 job1  192.168.100.2:/xcp/src16  192.168.100.3:/xcp/dst16  complete         4s             idle         08:51:32   0s         slave1  109
 job1  192.168.100.2:/xcp/src10  192.168.100.3:/xcp/dst10  complete         0s             idle         00:11:32   0s         slave2  7
 job1  192.168.100.2:/xcp/src11  192.168.100.3:/xcp/dst11  complete         2s             idle         00:11:32   0s         slave2  7
 job1  192.168.100.2:/xcp/src12  192.168.100.3:/xcp/dst12  complete         3s             idle         00:11:32   1s         slave1  7
 job1  192.168.100.2:/xcp/src13  192.168.100.3:/xcp/dst13  complete         3s             idle         08:51:32   0s         slave2  109
```




