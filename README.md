# XCPtion

## What is XCPtion?

XCPtion is a wrapper utility for [NetApp XCP](https://xcp.netapp.com/) NFS/CIFS file copy/migration utility. Support been also extended to: [robocopy] (CIFS), [cloudsync] (CIFS, NFS, S3, etc) (https://bluexp.netapp.com/cloud-sync-service), rclone (s3, google drive, ondrive and many more) (https://rclone.org/) and ndmpcopy (copy data between netapp volume/sub volume)

XCPtion has the capability to concurrently execute and manage multiple tasks across a cluster of servers in a distributed manner
This is achieved by utilizing [Hashi Corp Nomad](https://www.nomadproject.io/) distributed scheduler. 

## Where do I get XCPtion?

XCPtion is currently available at [GitLab Repository](https://gitlab.com/haim.marko/xcption)
You will need to apply for XCP license from: [XCP License Site](https://xcp.netapp.com/) and download the XCP binary from: [NetApp Support Site](https://mysupport.netapp.com/tools/info/ECMLP2357425I.html?productID=62115&pcfContentID=ECMLP2357425)

## Installation

XCPtion Server can be installed directly on internet connected Ubuntu/CentOS/RedHat server by pulling the repository using the command:

`git clone https://gitlab.com/haim.marko/xcption.git`

*ALL instances should be pulled to the same path on all of the servers !!!*
*To make sure time is consistent timezome on the linux servers should be set to UTC and time should be set to localtime*

For offline istallation the XCPtion package can be downloaded from the following location [xcption-master.tar.gz](https://gitlab.com/haim.marko/xcption/-/archive/master/xcption-master.tar.gz).
(will require standard yum/apt repository avaialble for the linux servers)

Before starting the setup, NFS accessed volume with root access should be created to host the shared XCP repository. This volume should be exported to all Linux servers that are going to be part of the cluster. The size is dependent on the number of files (good practice will be to allocate ~50G for the repository)

Deployment of the server role on the first linux host in the cluster should be done using the command (-r should point to the preconfigured repository)

`sudo ./xcption/system/xcption_deploy.sh -r <nfsserver:/xcp_repo_vol> -t server`

Deployment of the next linux hosts in the cluster should be done using the command (pointing to the server IP address):

`sudo ./xcption/system/xcption_deploy.sh -r <nfsserver:/xcp_repo_vol> -t client -s <server ip>`

Deployment of windows hosts should be done by coping all files from the ./xcption/windows directory on the server **(must be done after deploying the server)** to *C:\NetApp\XCP* directory on the windows host than running the following powershell script:  
`PS C:\>C:\NetApp\XCP\xcption_deploy_windows.ps1 -XCPtionServer <Server IP> -XCPtionServiceUser <Domain\user> -XCPtionServicePWD <passwd>`

`XCPtionServer` - IP address or resolvable name of the XCPtion Server    
`XCPtionServiceUser` - Domain Username (Domain\User) to start the XCPtionNomad service,   
                This user will be used to access Source and Destination during the migration (This user need access to all files)  
`XCPtionServicePWD` - Password for service user  

After installing XCPtion xcp license file should be copied to the following location **on all hosts in the cluster**:  

linux hosts `/opt/NetApp/xFiles/xcp/license`  
windows hosts `c:\NetApp\XCP\license`  

Updates to the xcp binary can be done by replacing the existing file in the following location:  

linux hosts `/usr/local/bin/xcp`  
windows hosts `c:\NetApp\XCP\xcp.exe`  

For offline installation where rclone is required it need to be installed manual using the installation insturctions avaialble here: https://rclone.org/downloads/ 
The rclone bnary should be available on all nodes in /usr/bin/rclone

## How To Use

The interaction is done using the following python CLI command (need root access)

```
[root@centos1 xcption]# ./xcption.py -h
usage: xcption.py [-h] [-v] [-d]
                  {nodestatus,status,assess,map,load,create,baseline,sync,syncnow,pause,resume,abort,verify,delete,modify,copy-data,delete-data,nomad,export,web,fileupload,smartassess}
                  ...

positional arguments:
  {nodestatus,status,assess,map,load,create,baseline,sync,syncnow,pause,resume,abort,verify,delete,modify,copy-data,delete-data,nomad,export,web,fileupload,smartassess}
                        sub commands that can be used
    nodestatus          display cluster nodes status
    status              display status
    assess              assess filesystem and create csv file
    map                 map shares/exports
    load                load/update configuration from csv file
    create              create ad-hock task
    baseline            start initial baseline
    sync                activate scheduled sync
    syncnow             initiate sync now
    pause               disable sync schedule
    resume              resume sync schedule
    abort               abort running task
    verify              start verify to validate consistency between source
                        and destination (xcp verify)
    delete              delete existing config
    modify              modify task job
    copy-data           monitored copy of source to destination (nfs only)
    delete-data         monitored delete of data using xcp (nfs only)
    export              export existing jobs to csv
    web                 start web interface to display status
    fileupload          transfer files to all nodes, usefull for xcp license
                        update on all nodes
    smartassess         create tasks based on capacity and file count (nfs
                        only)

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         print version information
  -d, --debug           log debug messages to console

```

**To list the nodes in the cluster use the `nodestatus` subcommand**

[user@master xcption]$ sudo ./xcption.py nodestatus

```
[root@rhel1 xcption]# ./xcption.py nodestatus

 Name      IP            Status  OS                                        Reserved/Total CPU MHz  Used CPU %  Reserved/Total RAM MB  Used RAM %  # Running Jobs
 windows1  192.168.0.73  ready   Microsoft windows server 2016 datacenter  0/4390 (0.0%)           0%          0/8191 (0.0%)          59.0%       0
 rhel1     192.168.0.61  ready   Redhat                                    0/4388 (0.0%)           9%          0/1838 (0.0%)          63.0%       0
 rhel2     192.168.0.62  ready   Redhat                                    0/4388 (0.0%)           3%          0/1838 (0.0%)          29.0%       0
[root@rhel1 xcption]#

```

The command display each node in the cluster, its status and amount of resources reserved/available by jobs and the number of currently running jobs.

**There are several options to create XCPtion jobs:**

**1. manual CSV creation**

a CSV file with the jobs should be created with the following columns:

`JOB NAME` - A name for the JOB, later on actions and output can be filtered by this name  
`SOURCE PATH` - Source path (format is dependent in the tool) 
`DEST PATH` - Destination path (format is dependent in the tool) 
`SYNC SCHED` (optional) - sync schedule in [cron](http://www.nncron.ru/help/EN/working/cron-format.htm) format (DEFAULT is daily @ midnight:`0 0 * * * *`)  
`CPU MHz` (optional) - The reserved CPU frequency for the job (DEFAULT:3000)  
`RAM MB` (optional) - The reserved RAM for the job (DEFAULT:800)  
`TOOL` (optional) - The tool to be used be used: `xcp`(default) nfs of CIFS,`robocopy` (only for CIFS tasks), `cloudsync` (requires special src/dst format), `rclone` (required remotes to be configured), `ndmpcopy` for inta/inter OnTap cluster (requires ssh public copy to be configred to from xcption nodes to ontap clusters)
`FAILBACKUSER` (optional, required for windows jobs using xcp.exe) - For windows jobs using the XCP tool it is mandatory to provide failback user 
(see xcp.exe help copy for details)  

`FAILBACKGROUP` (optional, required for windows jobs using xcp.exe) - For windows jobs using the XCP tool it is mandatory to provide failback group (see xcp.exe help copy for details)

`EXCLUDE DIRS` (optional, supported for xcp for NFS, robocopy, rclone and ndmpcopy) - name of a file located in <installdir>/system/xcp_repo/excluedir containg a list of paths (diffrent lines) that will be excluded during the migration. using exclude with xcp for NFS is not recomanded becuase xcp still scanning excluded dirs
`ACL COPY` (optional) - incldue details for acl copy. no-win-acl will prevent acl copy for CIFS jobs (robocopy and xcp), nfs4-acl will include nfs4-acl for nfs jobs (require nfs4 acl suport on both source and destination)

SOURCE and DEST paths format are as follows: 
- NFS job using xcp - nfsserver:/export[/path] - both source and destination should be accesible from each one of the Linux servers in the cluster using root permissions  

- CIFS job using xcp for windows or robocopy - \\\\cifsserver\\share[\\path] - both source and destination should be accesible from each one of the Windows servers in the cluster using administrative permission (the user used for `XCPtion Nomad` service is used by the tool)

- CloudSync job accoring to the following format: protocol://path@broker_group_name@account_name@username , src and dst can be from diffrent protocols 
  - protocol - can be one of the following: nfs(same as nfs3),nfs3,nfs4,nfs4.1,nfs4.2,nfs-fsx,cifs,local,s3,sgws,s3ontap 
  - path - the following formats are supported paths:
        nfs path format: nfsserver:/export[:path]
        local (local storage on the broker) path format : /path
        cifs path format: cifsserver:/share[/path] - username, password and domain for cifs can be provided in xcption <installdir>/system/xcp_repo/cloudsync/cred file with the following format: cifs:cifsserver:username:password[:domain]. if not provided can be entered manually in cloudsync interface following job creation (after xcption load)
        s3ontap (ontap s3 server) path format: s3server:bucket - accesskey and secretkey can be provided in xcption <installdir>/system/xcp_repo/cloudsync/cred file with the following format: s3ontap:bucket@s3server:accessKey:secretKey. if not provided can be entered manualy in cloudsync interface following job creation (after xcption load)
        sgws (storage grid) path format: s3server:bucket - accesskey and secretkey can be provided in xcption <installdir>/system/xcp_repo/cloudsync/cred file with the following format: sgws:s3server:bucket@s3server:accessKey:secretKey. if not provided can be entered manualy in cloudsync interface following job creation (after xcption load)        
        s3 (aws s3) path format: region:bucket - accesskey and secretkey can be provided in xcption <installdir>/system/xcp_repo/cloudsync/cred file with the following format: sgws:s3server:bucket@region:accessKey:secretKey. if not provided can be entered manualy in cloudsync interface following job creation (after xcption load)           
  - broker_group_name - name of the cloud sync broker group (containing one or more broker) with access to both source and destination. can be seen in the cloudesync:manage data brokers tab
  - account_name - name of the cloud sync multitenancy account name 
  - username - the username provided should corelate to entry in the xcption <installdir>/system/xcp_repo/cloudsync/accounts with corelation to valid cloudsync API key created according to the procedure https://docs.netapp.com/us-en/occm/api_sync.html. Each line in the file should use the following format: username:apikey 

- rclone job accoridng to the following format: remote:path[/folder]. remotes should be confiugred according to rclone documentation and should be saved in <installdir>/system/xcp_repo/rclone/rclone.conf

- ndmpcopy job job according to the following format ontapuser@cluster:/svm/vol[/path]. ssh public key authentication should be configured to allow unauthenticated ssh conectivity from all XCPtion linux hosts in the cluster. 

CSV file example:
```
#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB,TOOL,FAILBACKUSER,FAILBACKGROUP,EXCLUDE DIR FILE
#NFS Jobs 
jobnfs1,192.168.0.200:/nfssrc/dir1,192.168.0.200:/nfsdst/dir1,10 * * * *,1000,800
jobnfs1,192.168.0.200:/nfssrc/dir2,192.168.0.200:/nfsdst/dir2,20 * * * *,1000,800
jobnfs2,192.168.0.200:/nfssrc/dir3,192.168.0.200:/nfsdst/dir3,30 * * * *,1000,800
jobnfs2,192.168.0.200:/nfssrc/dir4,192.168.0.200:/nfsdst/dir4,40 * * * *,1000,800,xcp,,,nfs_dir4_exclude_dirs
#CIFS jobs 
jobwin1,\\192.168.0.200\src$\dir1,\\192.168.0.200\dst$\dir1,0 0 * * * *,2000,800,xcp,domain\user1,domain\Domain Admins
jobwin2,\\192.168.0.200\src$\dir2,\\192.168.0.200\dst$\dir2,0 0 * * * *,2000,800,xcp,domain\user1,domain\Domain Admins
jobwin1,\\192.168.0.200\src$\dir3,\\192.168.0.200\dst$\dir3,0 0 * * * *,2000,800,robocopy
jobwin4,\\192.168.0.200\src$\dir4,\\192.168.0.200\dst$\dir4,0 0 * * * *,2000,800,robocopy,,,cifs_dir4_exclude_dirs
#CloudSync Jobs
cloudsync1,nfs://192.168.0.200:/unixsrc/dir7@grp1@XCPtion@hmarko,nfs://192.168.0.200:/unixdst/dir7@grp1@XCPtion@hmarko,0 0 * * * *,50,50,cloudsync
cloudsync1,cifs://192.168.0.200:/cifssrc@grp1@XCPtion@hmarko,nfs://192.168.0.200:/unixdst/dir8@grp1@XCPtion@hmarko,0 0 * * * *,50,50,cloudsync
cloudsync1,local:///etc@grp1@XCPtion@hmarko,nfs://192.168.0.200:/unixdst/dir9@grp1@XCPtion@hmarko,0 0 * * * *,50,50,cloudsync
cloudsync2,s3ontap://192.168.0.200:huge@grp1@XCPtion@hmarko,nfs://192.168.0.200:/unixdst/dir2@grp1@XCPtion@hmarko,0 0 * * * *,50,50,cloudsync
cloudsync2,sgws://192.168.0.200:bucket1:4443@grp1@XCPtion@hmarko,s3ontap://192.168.0.200:bucket2@grp1@XCPtion@hmarko,0 0 * * * *,50,50,cloudsync
cloudsync2,s3://us-east-1:bucket@grp1@XCPtion@hmarko,nfs://192.168.0.200:/unixdst/dir5@grp1@XCPtion@hmarko,0 0 * * * *,50,50,cloudsync
#CloudSync Jobs
rclone,s3source:bucket1,s3dest:bucket1,0 0 * * * *,50,50,rclone,,,
rclone,s3source:src,s3dest:dst,0 0 * * * *,50,50,rclone,,,rclone.exclude
#ndmpcopy Jobs
ndmpcopy,admin@cluster1:/svm/srcvol/folder1,admin@cluster2:/svm/dstvol/folder1,0 0 * * * *,50,50,ndmpcopy
ndmpcopy,admin@cluster1:/svm/srcvol/qtree1,admin@cluster2:/svm/dstvol/qtree1,0 0 * * * *,50,50,ndmpcopy,,,ndmpcopy.exclude
```

EXCLUDE DIRS file format example:

XCP NFS file example (<installdir>/system/xcp_repo/excluedir/nfs_dir4_exclude_dirs for the above example)
```
192.168.0.200:/nfssrc/dir4/unused_files
192.168.0.200:/nfssrc/dir4/subdir/old_to_delete
```
ROBOCOPY EXCLUDE DIRS file example (<installdir>/system/xcp_repo/excluedir/cifs_dir4_exclude_dirs for the above example)
```
\\192.168.0.200\src$\dir4\old_not_required_files_dir
\\192.168.0.200\src$\dir4\subdir1\files_not_needed
unused_files #name of specific directory to exclude
```
RCLONE EXCLUDE DIRS file example (<installdir>/system/xcp_repo/excluedir/rclone.exclude for the above example), format is according to rclone filtering rules: https://rclone.org/filtering/
```
/folder1/**
/folder2/**

```
NDMPCOPY EXCLUDE PATHS file example (<installdir>/system/xcp_repo/excluedir/ndmpcopy.exclude for the above example)
```
*.pst
*folder*
/folder/file 
```

cloudsync accounts file example (<installdir>/system/xcp_repo/cloudsync/accounts for the above example)
```
hmarko:<refresh token generated in https://services.cloud.netapp.com/refresh-token>
```
cloudsync cred file example (<installdir>/system/xcp_repo/cloudsync/creds for the above example)
```
cifs:192.168.0.200:<user>:<passwd>!:demo
s3:bucket:<accesskey>:<secretkey>
sgws:<bucket>@<endpoint>:<accesskey>:<secretkey>
```
**2. add-hoc job creation**
jobs can be created using the `xcption create` subcommand. 
```
usage: xcption.py create [-h] -j jobname -s SOURCE -d DESTINATION [-p CPU]
                         [-m RAM] [-t tool] [-n cron] [-e EXCLUDE] [-v]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        xcption job name
  -s SOURCE, --source SOURCE
                        source nfs/cifs path
  -d DESTINATION, --destination DESTINATION
                        destination nfs/cifs path
  -p CPU, --cpu CPU     CPU allocation in MHz for each job
  -m RAM, --ram RAM     RAM allocation in MB for each job
  -t tool, --tool tool  tool to use as part of the task
  -n cron, --cron cron  create all task with schedule
  -e EXCLUDE, --exclude EXCLUDE
                        comma seperated exclude paths
  -v, --novalidation    create can be faster for windows paths since
                        valaidation is prevented
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
user@master:~/xcption$ sudo ./xcption.py load -c example/nfsjob.csv
2019-09-06 15:47:22,956 - INFO - validating src:192.168.0.200:/nfssrc/dir1 and dst:192.168.0.200:/nfsdst/dir1 are mountable
2019-09-06 15:47:23,024 - INFO - validating src:192.168.0.200:/nfssrc/dir2 and dst:192.168.0.200:/nfsdst/dir2 are mountable
2019-09-06 15:47:23,094 - INFO - validating src:192.168.0.200:/nfssrc/dir3 and dst:192.168.0.200:/nfsdst/dir3 are mountable
2019-09-06 15:47:23,166 - INFO - validating src:192.168.0.200:/nfssrc/dir4 and dst:192.168.0.200:/nfsdst/dir4 are mountable
2019-09-06 15:47:23,251 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir1
2019-09-06 15:47:23,256 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir3
2019-09-06 15:47:23,260 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir2
2019-09-06 15:47:23,266 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir4


user@master:~/xcption$ sudo ./xcption.py load -c example/cifsjob.csv
2019-09-06 15:47:30,400 - INFO - validating src:\\192.168.0.200\src$\dir4 and dst:\\192.168.0.200\dst$\dir4 cifs paths are avaialble from one of the windows server
2019-09-06 15:47:37,485 - INFO - validating src:\\192.168.0.200\src$\dir3 and dst:\\192.168.0.200\dst$\dir3 cifs paths are avaialble from one of the windows server
2019-09-06 15:47:44,586 - INFO - validating src:\\192.168.0.200\src$\dir2 and dst:\\192.168.0.200\dst$\dir2 cifs paths are avaialble from one of the windows server
2019-09-06 15:47:52,677 - INFO - validating src:\\192.168.0.200\src$\dir1 and dst:\\192.168.0.200\dst$\dir1 cifs paths are avaialble from one of the windows server
2019-09-06 15:47:59,766 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir1
2019-09-06 15:47:59,778 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir3
2019-09-06 15:47:59,783 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir2
2019-09-06 15:47:59,787 - INFO - creating/updating relationship configs for src:192.168.0.200:/nfssrc/dir4
2019-09-06 15:47:59,792 - INFO - creating/updating relationship configs for src:\\192.168.0.200\src$\dir3
2019-09-06 15:47:59,796 - INFO - creating/updating relationship configs for src:\\192.168.0.200\src$\dir2
2019-09-06 15:47:59,799 - INFO - creating/updating relationship configs for src:\\192.168.0.200\src$\dir1
2019-09-06 15:47:59,803 - INFO - creating/updating relationship configs for src:\\192.168.0.200\src$\dir4

```

**To run the baseline (initial copy of data) the `baseline` command should be used**

For xcp for NFS the baseline uses `xcp isync` instead of `xcp copy` (available as part of xcp 1.9.3) to prevent re-baseline of all data when destination already contains data.
Baseline should be completed to enable incremental updated (sync). A rebaseline can be initiated using the `--force` (for xcp for NFS it will triger recreation of the index)
When running without --job/--source baseline will be issued on all migration jobs.
```
user@master:~/xcption$ sudo ./xcption.py baseline -h
usage: xcption.py baseline [-h] [-j jobname] [-s srcpath] [-f]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
  -f, --force           force re-baseline
```


Example:
```
user@master:~/xcption# sudo ./xcption.py baseline
2019-09-06 15:49:30,859 - INFO - starting/updating baseline job for src:192.168.0.200:/nfssrc/dir1 dst:192.168.0.200:/nfsdst/dir1
2019-09-06 15:49:30,914 - INFO - starting/updating baseline job for src:192.168.0.200:/nfssrc/dir3 dst:192.168.0.200:/nfsdst/dir3
2019-09-06 15:49:30,971 - INFO - starting/updating baseline job for src:192.168.0.200:/nfssrc/dir2 dst:192.168.0.200:/nfsdst/dir2
2019-09-06 15:49:31,029 - INFO - starting/updating baseline job for src:192.168.0.200:/nfssrc/dir4 dst:192.168.0.200:/nfsdst/dir4
2019-09-06 15:49:31,099 - INFO - starting/updating baseline job for src:\\192.168.0.200\src$\dir3 dst:\\192.168.0.200\dst$\dir3
2019-09-06 15:49:31,211 - INFO - starting/updating baseline job for src:\\192.168.0.200\src$\dir2 dst:\\192.168.0.200\dst$\dir2
2019-09-06 15:49:31,338 - INFO - starting/updating baseline job for src:\\192.168.0.200\src$\dir1 dst:\\192.168.0.200\dst$\dir1
2019-09-06 15:49:31,461 - INFO - starting/updating baseline job for src:\\192.168.0.200\src$\dir4 dst:\\192.168.0.200\dst$\dir4

```

**To schedule the incremental updates (xcp sync) the `sync` subcommand should be used (sync is possiable only when baseline is complete)**
The `sync` commnd will trigger/update the sync scheule and should be issued folloiwng every change in the cron schedule (for example after modifing the cron schedule of a job)
When running without --job/--source baseline will be issued on all migration jobs.

```
usage: xcption.py sync [-h] [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```

Example for starting sync on specific job name using the -j option
```
user@master:~/xcption# sudo ./xcption.py sync -j cifsjob
2019-09-06 15:52:27,632 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir3 dst:\\192.168.0.200\dst$\dir3
2019-09-06 15:52:27,708 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir2 dst:\\192.168.0.200\dst$\dir2
2019-09-06 15:52:27,758 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir1 dst:\\192.168.0.200\dst$\dir1
2019-09-06 15:52:27,807 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir4 dst:\\192.168.0.200\dst$\dir4

```

**To trigger on demand sync the `syncnow` subcommand should be used (syncnow is possiable only when baseline is complete)**
The `syncnow` commnd will start on demand sync not related to the cron schedule on the job.
When running without --job/--source baseline will be issued on all migration jobs.

```
[root@rhel1 xcption]# ./xcption.py syncnow -h
usage: xcption.py syncnow [-h] [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```

Example for starting sync on specific job name using the -j option
```
user@master:~/xcption# sudo ./xcption.py sync -j cifsjob
2019-09-06 15:52:27,632 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir3 dst:\\192.168.0.200\dst$\dir3
2019-09-06 15:52:27,708 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir2 dst:\\192.168.0.200\dst$\dir2
2019-09-06 15:52:27,758 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir1 dst:\\192.168.0.200\dst$\dir1
2019-09-06 15:52:27,807 - INFO - starting/updating sync job for src:\\192.168.0.200\src$\dir4 dst:\\192.168.0.200\dst$\dir4

```

**to start verification using xcp (linux and windows) the `verify` subcommand should be used (verify is possiable only when baseline is complete)**
The verify command will trigger xcp verify jobIt can be used with `--withdata` to include also file content and not only names, `--quick` to verify 1 out 1000 files (using xcp -match rand(1000) option) or `--reverse` to compare destination to the source.
```
[root@rhel1 xcption]# ./xcption.py verify -h
usage: xcption.py verify [-h] [-j jobname] [-s srcpath] [-q] [-w] [-r]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
  -q, --quick           perform quicker verify by using xcp random file verify
                        (1 out of 1000)
  -w, --withdata        perform deep data verification (full content
                        verification)
  -r, --reverse         perform reverse verify (dst will be compared to the
                        src)

```

```
user@master:~/xcption$ sudo ./xcption.py verify
2019-09-06 16:50:05,188 - INFO - starting/updating verify job for src:192.168.0.200:/nfssrc/dir1 dst:192.168.0.200:/nfsdst/dir1
2019-09-06 16:50:05,243 - INFO - starting/updating verify job for src:192.168.0.200:/nfssrc/dir3 dst:192.168.0.200:/nfsdst/dir3
2019-09-06 16:50:05,352 - INFO - starting/updating verify job for src:192.168.0.200:/nfssrc/dir2 dst:192.168.0.200:/nfsdst/dir2
2019-09-06 16:50:05,458 - INFO - starting/updating verify job for src:192.168.0.200:/nfssrc/dir4 dst:192.168.0.200:/nfsdst/dir4
2019-09-06 16:50:05,572 - INFO - starting/updating verify job for src:\\192.168.0.200\src$\dir3 dst:\\192.168.0.200\dst$\dir3
2019-09-06 16:50:05,697 - INFO - starting/updating verify job for src:\\192.168.0.200\src$\dir2 dst:\\192.168.0.200\dst$\dir2
2019-09-06 16:50:05,792 - INFO - starting/updating verify job for src:\\192.168.0.200\src$\dir1 dst:\\192.168.0.200\dst$\dir1
2019-09-06 16:50:05,894 - INFO - starting/updating verify job for src:\\192.168.0.200\src$\dir4 dst:\\192.168.0.200\dst$\dir4

```

**To report the status use the `status` command**

The `status` command is used to view the current status of the jobs managed by XCPtion. 
When running without filters it will display informatoin on all jobs. Filters can be issued on job name, srcpath, job status, jobs with errors, used nodes, etc. 
Output can be displayed in a human readable table or in CSV or JSON formats which can be used as part of automation.

Verbose job information inclding all job properties and the status all phases within the job using `--verbose`. 

```
user@master:~/xcption$ ./xcption.py status -h
usage: xcption.py status [-h] [-j jobname] [-s srcpath] [-t jobstatus] [-v] [-p phase] [-n node] [-e] [-o output] [-l]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
  -t jobstatus, --jobstatus jobstatus
                        change the scope of the command to specific job status ex:complete,running,failed,pending,aborted
  -v, --verbose         provide verbose per phase info
  -p phase, --phase phase
                        change the scope of the command to specific phase ex:baseline,sync#,verify#,lastsync (requires -v/--verbose)
  -n node, --node node  change the scope of the command to specific node (requires -v/--verbose)
  -e, --error           change the scope of the command to jobs with errors (requires -v/--verbose)
  -o output, --output output
                        output type: [csv|json]
  -l, --logs            display job logs

```


Example:
display general information on all jobs (no filters)

```

user@master:~/xcption# sudo ./xcption.py status

 BL=Baseline SY=Sync VR=Verify

 Job      Source Path                 Dest Path                   BL Status  BL Time  BL Sent    SY Status  Next SY   SY Time  SY Sent  SY#  VR Status  VR Start             VR Ratio     VR#
 jobnfs1  192.168.0.200:/nfssrc/dir1  192.168.0.200:/nfsdst/dir1  complete   1s       6.58 MiB   -          07:08:31  -        -        0    equal      2019-09-06 16:50:05  405/405      1
 jobnfs1  192.168.0.200:/nfssrc/dir3  192.168.0.200:/nfsdst/dir3  complete   1s       6.37 MiB   -          07:08:31  -        -        0    equal      2019-09-06 16:50:05  405/405      1
 jobnfs1  192.168.0.200:/nfssrc/dir2  192.168.0.200:/nfsdst/dir2  complete   1s       6.53 MiB   -          07:08:31  -        -        0    equal      2019-09-06 16:49:47  405/405      1
 jobnfs1  192.168.0.200:/nfssrc/dir4  192.168.0.200:/nfsdst/dir4  complete   1s       6.37 MiB   -          07:08:31  -        -        0    equal      2019-09-06 16:49:47  405/405      1
 cifsjob  \\192.168.0.200\src$\dir3   \\192.168.0.200\dst$\dir3   complete   01s      0.0 B      -          07:08:31  -        -        0    equal      2019-09-06 16:49:46  6/6          1
 cifsjob  \\192.168.0.200\src$\dir2   \\192.168.0.200\dst$\dir2   complete   01s      0.0 B      -          07:08:31  -        -        0    equal      2019-09-06 16:49:47  5/5          1
 cifsjob  \\192.168.0.200\src$\dir1   \\192.168.0.200\dst$\dir1   complete   22m27s   788.7 MiB  -          07:08:31  -        -        0    running    2019-09-06 16:49:47  1,043/1,043  1
 cifsjob  \\192.168.0.200\src$\dir4   \\192.168.0.200\dst$\dir4   complete   08m13s   5.44 GiB   -          07:08:31  -        -        0    equal      2019-09-06 16:49:47  276/276      1

```

display verbose on job containing `dir1` in the source path

```
user@master:~/xcption$ sudo ./xcption.py status -v -s dir1
JOB: jobnfs1
SRC: 192.168.0.200:/nfssrc/dir1
DST: 192.168.0.200:/nfsdst/dir1
SYNC CRON: 0 0 * * * * (NEXT RUN 07:07:14)
XCP INDEX NAME: 192.168.0.200-_nfssrc_dir1-192.168.0.200-_nfsdst_dir1
OS: LINUX

 Phase     Start Time           End Time             Duration  Scanned  Reviewed  Copied  Modified  Deleted  Errors  Data Sent             Node   Status
 baseline  2019-09-06 15:49:13  2019-09-06 15:49:14  1s        405      404       404     -         -        -       6.58 MiB(6.42 MiB/s)  rhel2  complete
 verify1   2019-09-06 16:50:05  2019-09-06 16:50:06  1s        405/405  100%      -       -         -        -       55.7 KiB(46.6 KiB/s)  rhel2  equal
 sync1     2019-09-06 16:51:54  2019-09-06 16:51:55  1s        -        405       -       -         -        -       87.0 KiB(72.9 KiB/s)  rhel2  complete


JOB: cifsjob
SRC: \\192.168.0.200\src$\dir1
DST: \\192.168.0.200\dst$\dir1
SYNC CRON: 0 0 * * * * (NEXT RUN 07:07:14)
OS: WINDOWS
TOOL NAME: robocopy

 Phase     Start Time           End Time             Duration  Scanned      Reviewed  Copied  Modified  Deleted  Errors  Data Sent  Node  Status
 baseline  2019-09-06 15:49:12  2019-09-06 15:50:33  22m27s    10734        -         10734   -         -        0       788.7 MiB  WFA   complete
 verify1   2019-09-06 16:49:47  2019-09-06 16:52:09  2m20s     5,372/5,372  5,372     -       -         -        -       -          WFA   equal
 sync1     2019-09-06 16:51:54  2019-09-06 16:51:59  01m07s    10734        -         10734   -         -        0       788.7 MiB  WFA   complete

```

**To see xcp logs for specific phase of a job use the `-p <phase>` argument together with the `-l` argument **

As part of this command only the last 50 lines of the `stdout` and `stderr` are displayed. to see the complete file you can use the `cat` command on the file path displayed as part of the `status` command output.
The following command is used to dispaly the logs of the last sync phase (`lastsync`), to see specific phase logs use baseline,sync#,verify#.

```
[root@rhel1 xcption]# ./xcption.py status -s vol1 -v -p lastsync -l

JOB: nfs
SRC: 192.168.0.132:/vol1
DST: 192.168.0.132:/vol2
SYNC CRON: 0 2 * * * (NEXT RUN 0d22h42m39s)
RESOURCES: 2000MHz CPU 800MB RAM
XCP INDEX NAME: 192.168.0.132-_vol1-192.168.0.132-_vol2
EXCLUDE DIRS FILE: /root/xcption/system/xcp_repo/excludedir/nfs.exclude
OS: LINUX
TOOL NAME: xcp

 Phase  Start Time           End Time             Duration  Scanned  Reviewed  Copied  Modified  Deleted  Errors  Data Sent             Node                   Status
 sync1  2024-02-03 08:16:56  2024-02-03 08:16:59  1s        1        1         -       1         -        -       19.4 KiB(12.4 KiB/s)  rhel1.demo.netapp.com  complete

Log type:stdout
xcp: WARNING: CPU count is only 2!
xcp: WARNING: CPU count is only 2!
Job ID: Job_192.168.0.132-_vol1-192.168.0.132-_vol2_2024-02-03_03.16.57.515540_sync
Index: 192.168.0.132-_vol1-192.168.0.132-_vol2 {source: 192.168.0.132:/vol1, target: 192.168.0.132:/vol2}


1 reviewed, 1 checked at source, 1 modification, 17.1 KiB in (11.4 KiB/s), 14.2 KiB out (9.46 KiB/s), 1s.
Starting search pass for 1 modified directory...
1 reviewed, 1 checked at source, 1 modification, 1 re-reviewed, 21.7 KiB in (14.0 KiB/s), 14.3 KiB out (9.26 KiB/s), 1s.
Rereading the 1 modified directory...
1 reviewed, 1 checked at source, 1 modification, 1 re-reviewed, 1 new dir, 22.5 KiB in (14.5 KiB/s), 14.7 KiB out (9.42 KiB/s), 1s.
Deep scanning the 1 modified directory...
1 scanned, 1 indexed, 1 excluded, 1 reviewed, 1 checked at source, 1 modification, 1 re-reviewed, 1 new dir, 23.8 KiB in (15.2 KiB/s), 19.4 KiB out (12.4 KiB/s), 1s.

the last 50 lines are displayed
full log file path: /root/xcption/system/xcp_repo/nomadcache/job_sync__192.168.0.132-_vol1/stdoutlog_5a79dec1-700b-1878-e4fa-7f0fa7d74209.log
Log type:stderr
XCP 1.9.3; (c) 2024 NetApp, Inc.; Licensed to haim marko [NetApp Inc] until Tue Dec 17 17:53:30 2024

Xcp command : xcp sync -id 192.168.0.132-_vol1-192.168.0.132-_vol2
Stats       : 1 scanned, 1 indexed, 1 excluded, 1 reviewed, 1 checked at source, 1 modification, 1 re-reviewed, 1 new dir
Speed       : 27.0 KiB in (16.4 KiB/s), 106 KiB out (64.0 KiB/s)
Total Time  : 1s.
Migration ID: 192.168.0.132-_vol1-192.168.0.132-_vol2
Job ID      : Job_192.168.0.132-_vol1-192.168.0.132-_vol2_2024-02-03_03.16.57.515540_sync
Log Path    : /root/xcption/system/xcp_repo/xcplogs/rhel1.demo.netapp.com/Job_192.168.0.132-_vol1-192.168.0.132-_vol2_2024-02-03_03.16.57.515540_sync.log
STATUS      : PASSED

the last 50 lines are displayed
full log file path: /root/xcption/system/xcp_repo/nomadcache/job_sync__192.168.0.132-_vol1/stderrlog_5a79dec1-700b-1878-e4fa-7f0fa7d74209.log
```
**XCPtion can help with mapping existing NFS exports and CIFS shares information using the `map` command**
This can be very helpful as part of migration to help with mapping the exisiting environment or to create automation for creation of CIFS shares and exports on the destinatation. 
The information can be displayed in human readable table or using CSV/JSON ourput. 

```
usage: xcption.py map [-h] -s HOSTS -p type [-o output]

optional arguments:
  -h, --help            show this help message and exit
  -s HOSTS, --hosts HOSTS
                        comma seperated servers to map shares or exportrts
  -p type, --protocol type
                        server protocol: [cifs|nfs]
  -o output, --output output
                        output type: [csv|json]
```

```
[root@rhel1 xcption]# ./xcption.py  map -p nfs -s 192.168.0.132
2024-02-03 03:41:40,877 - INFO - gathering NFS exports information on host: 192.168.0.132
 Server         Export               Free Space  Used Space  Free Files  Used Files
 192.168.0.132  192.168.0.132:/vol2  95.0GiB     884KiB      3.11M       884KiB
 192.168.0.132  192.168.0.132:/      17.6MiB     1.44MiB     462         1.44MiB
 192.168.0.132  192.168.0.132:/vol1  100.0GiB    15.4MiB     24.9M       15.4MiB
```

```
[root@rhel1 xcption]# ./xcption.py  map -p cifs -s 192.168.0.132
2024-02-03 03:41:49,138 - INFO - gathering CIFS shares information on host: 192.168.0.132
 Server         Share    Folder           Comment  ACL User        Action  ACL Permission  VOL Free Space  VOL Used Space
 192.168.0.132  xcption  C:\vol1\xcption           Domain Admins   Allow   Full Control    100.0GiB        15.4MiB
 192.168.0.132  xcption  C:\vol1\xcption           Domain Users    Allow   Read            100.0GiB        15.4MiB
 192.168.0.132  vol2     C:\vol2                   Everyone        Allow   Full Control    95.0GiB         884KiB
 192.168.0.132  vol1     C:\vol1                   Everyone        Allow   Full Control    100.0GiB        15.4MiB
 192.168.0.132  c$       C:\                       Administrators  Allow   Full Control    17.6MiB         1.45MiB
```

**additional sub commands that can be used includes the following**

`pause`  - pause cron scheules 
```
[root@rhel1 xcption]# ./xcption.py pause -h
usage: xcption.py pause [-h] [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```
`resume` - resume cron scheules 
```
[root@rhel1 xcption]# ./xcption.py resume -h
usage: xcption.py resume [-h] [-j jobname] [-s srcpath]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
```
`abort`  - abort running job
```
[root@rhel1 xcption]# ./xcption.py abort -h
usage: xcption.py abort [-h] [-j jobname] [-s srcpath] -t type [-f]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
  -t type, --type type  specify the type of job to abort, can be baseline,sync
                        or verify
  -f, --force           force abort
```
`modify` - modify job properties like job name, cron, reserved resources, etc. 
```
[root@rhel1 xcption]# ./xcption.py modify -h
usage: xcption.py modify [-h] [-j jobname] [-s srcpath] [-t tojob] [-c cron]
                         [-p CPU] [-m RAM] [-f]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
  -t tojob, --tojob tojob
                        move selected tasks to this job
  -c cron, --cron cron  modify the sync schedule for this job
  -p CPU, --cpu CPU     modify CPU allocation in MHz for each job
  -m RAM, --ram RAM     modify RAM allocation in MB for each job
  -f, --force           force modify
```
`export` - export jobs into csv file, the can be used for backup are job configuration migration to anther server. 
```
[root@rhel1 xcption]# ./xcption.py export -h
usage: xcption.py export [-h] -c CSVFILE [-j jobname] [-s srcpath]

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
`delete` - delete jobs from xcption 
```
[root@rhel1 xcption]# ./xcption.py delete -h
usage: xcption.py delete [-h] [-j jobname] [-s srcpath] [-f]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
  -f, --force           force delete
```
`web`    - starts simple web interface for ro access.
```
[root@rhel1 xcption]# ./xcption.py web -h
usage: xcption.py web [-h] [-p port]

optional arguments:
  -h, --help            show this help message and exit
  -p port, --port port  tcp port to start the web server on (default:1234)
```

`copy-data`   - ad-hoc monitored copy of source to destination (nfs only)
```
[root@rhel1 xcption]# ./xcption.py copy-data -h
usage: xcption.py copy-data [-h] -s SOURCE -d DESTINATION [-f] [-a]

optional arguments:
  -h, --help            show this help message and exit
  -s SOURCE, --source SOURCE
                        source nfs path (nfssrv:/mount)
  -d DESTINATION, --destination DESTINATION
                        destination nfs path (nfssrv:/mount)
  -f, --force           force copy event if destination contains files
  -a, --nfs4acl         use to include nfs4-acl
```
`delete-data` - ad-hoc monitored delete of data using xcp (nfs only)
```
[root@rhel1 xcption]# ./xcption.py delete-data -h
usage: xcption.py delete-data [-h] -s SOURCE [-t tool] [-f]

optional arguments:
  -h, --help            show this help message and exit
  -s SOURCE, --source SOURCE
                        source nfs path (nfssrv:/mount)
  -t tool, --tool tool  tool to use (default is xcp)
  -f, --force           force delete data without confirmation
```
