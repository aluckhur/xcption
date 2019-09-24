# XCPtion

## What is XCPtion?

XCPtion is a wrapper utility for [NetApp XCP](https://xcp.netapp.com/) NFS/CIFS file copy/migration utility (for CIFS the tool supports also robocopy.exe)  
XCPtion will be able to parallelly execute and manage multiple XCP jobs on more than one host in a distributed fashion. 
This is done by utilizing [Hashi Corp Nomad](https://www.nomadproject.io/) distributed scheduler. 


## Where do I get XCPtion?

XCPtion is currently available at [GitLab Repository](https://gitlab.com/haim.marko/xcption)
You will need to apply for XCP license from: [XCP License Site](https://xcp.netapp.com/) and download the XCP binary from: [NetApp Support Site](https://mysupport.netapp.com/tools/info/ECMLP2357425I.html?productID=62115&pcfContentID=ECMLP2357425)

## Installation

XCPtion Server can be installed directly on internet connected Ubuntu/CentOS/RedHat server by pulling the repository using the command:

`git pull https://gitlab.com/haim.marko/xcption.git`

*ALL instances should be pulled to the same path on all of the servers !!!*

The XCPtion package can be downloaded from the following location [xcption-master.tar.gz](https://gitlab.com/haim.marko/xcption/-/archive/master/xcption-master.tar.gz).



Before starting the setup, NFS accessed volume with root access should be created to host the shared XCP repository. This volume should be exported to all Linux servers that are going to be part of the cluster. The size is dependent on the number of files (good practice will be to allocate ~50G for the repository)

Deployment of the server role on the 1st linux host in the cluster should be done using the command (-r should point to the preconfigured repository)

`sudo ./xcption/system/xcption_deploy.sh -r x.x.x.x:/vol/folder -t server`

Deployment of the next linux hosts in the cluster should be done using the command (pointing to the server IP address):

`sudo ./xcption/system/xcption_deploy.sh -r x.x.x.x:/vol/folder -t client -s <Server IP>`

Deployment of windows hosts should be done by coping all files from the windows directory in the repository to *C:\NetApp\XCP* directory on the windows host than running the following powershell script:  
`PS C:\>C:\NetApp\XCP\xcption_deploy_windows.ps1 -XCPtionServer <Server IP> -XCPtionServerInstallDir <Install DIR> -XCPtionServerUser <user> -XCPtionServerPWD <passwd> -ServiceUser <Domain\user> -ServicePWD <passwd>`

`XCPtionServer` - IP address or resolvable name of the XCPtion Server  
`XCPtionServerInstallDir` - The installation path of XCPtion on the server (Ex. /root/xcption)  
`XCPtionServerUser` - username to access the XCPtion Server using scp to pull install files  
`XCPtionServerPWD` - passwd for the XCPtion Server username  
`ServiceUser` - Domain Username (Domain\User) to start the XCPtionNomad service,   
                This user will be used to access Source and Destination during the migration (This user need access to all files)  
`ServicePWD` - Password for service user  


After installing XCPtion **on all hosts**, xcp license file should be copied to the following location:  

linux hosts `/opt/NetApp/xFiles/xcp/license`  
windows hosts `c:\NetApp\XCP\license`  

Updates to the xcp binary can be done by replacing the existing file in the following location:  

linux hosts `/usr/local/bin/xcp`  
windows hosts `c:\NetApp\XCP\xcp.exe`  


## How To Use

The interaction is done using the following python CLI command (need root access)

```
[user@master xcption]$ sudo ./xcption.py  -h
usage: xcption.py [-h] [-d]

                  {nodestatus,status,asses,load,baseline,sync,syncnow,pause,resume,verify,delete,nomad}
                  ...

positional arguments:
  {nodestatus,status,asses,load,baseline,sync,syncnow,pause,resume,verify,delete,nomad}
                        sub commands that can be used
    nodestatus          display cluster nodes status
    status              display status
    asses               asses fielsystem and create csv file
    load                load/update configuration from csv file
    baseline            start baseline (xcp copy)
    sync                start schedule updates (xcp sync)
    syncnow             initiate sync now
    pause               disable sync schedule
    resume              resume sync schedule
    verify              start verify to validate consistency between source
                        and destination (xcp verify)
    delete              delete existing config

optional arguments:
  -h, --help            show this help message and exit
  -d, --debug           log debug messages to console
```

**To display the nodes in the cluster use the `nodestatus` subcommand**

[user@master xcption]$ sudo ./xcption.py nodestatus

```
 Name      IP             Status  OS                                           Reserved/Total CPU MHz  Reserved/Total RAM MB  # Running Jobs
 rhel1     192.168.0.61   ready   redhat                                       0/4588 (0.0%)           0/1838 (0.0%)          0
 DC1       192.168.0.253  ready   Microsoft Windows Server 2012 R2 Datacenter  0/4590 (0.0%)           0/1023 (0.0%)          0
 WFA       192.168.0.73   ready   Microsoft Windows Server 2016 Datacenter     0/4590 (0.0%)           0/8191 (0.0%)          0
 rhel2     192.168.0.62   ready   redhat                                       0/4588 (0.0%)           0/1838 (0.0%)          0
 JUMPHOST  192.168.0.5    ready   Microsoft Windows Server 2012 R2 Datacenter  0/2295 (0.0%)           0/2047 (0.0%)          0
```

The command display each node in the cluster, its status and amount of resources reserved/available by jobs and the nu,ber of running jobs.

**There are 2 options to create XCPtion jobs:**

**1. manual CSV creation**

a CSV file with the jobs should be created with the following columns:

`JOB NAME` - A name for the JOB, later on actions and output can be filtered by this name  
`SOURCE PATH` - Source NFSv3 path. The source should be mountable as root from all instances in the cluster  
`DEST PATH` - Destination NFSv3 path. The destination should be mountable as root from all instances in the cluster  
`SYNC SCHED` (optional) - sync schedule in [cron](http://www.nncron.ru/help/EN/working/cron-format.htm) format (DEFAULT is daily @ midnight:`0 0 * * * *`)  
`CPU MHz` (optional) - The reserved CPU frequency for the job (DEFAULT:3000)  
`RAM MB` (optional) - The reserved RAM for the job (DEFAULT:800)  
`TOOL` (optional) - For windows jobs it is possiable to chose between `xcp` (default) to `robocopy`  
`FAILBACKUSER` (optional, required for windows jobs using xcp.exe) - For windows jobs using the XCP tool it is mandatory to provide failback user (see xcp.exe help copy for details)  
`FAILBACKGROUP` (optional, required for windows jobs using xcp.exe) - For windows jobs using the XCP tool it is mandatory to provide failback group (see xcp.exe help copy for details)  


CSV file example:
```
#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB,TOOL,FAILBACKUSER,FAILBACKGROUP
#NFS Jobs 
jobnfs1,192.168.0.200:/nfssrc/dir1,192.168.0.200:/nfsdst/dir1,10 * * * *,1000,800
jobnfs1,192.168.0.200:/nfssrc/dir2,192.168.0.200:/nfsdst/dir2,20 * * * *,1000,800
jobnfs2,192.168.0.200:/nfssrc/dir3,192.168.0.200:/nfsdst/dir3,30 * * * *,1000,800
jobnfs2,192.168.0.200:/nfssrc/dir4,192.168.0.200:/nfsdst/dir4,40 * * * *,1000,800
#CIFS jobs 
jobwin1,\\192.168.0.200\src$\dir1,\\192.168.0.200\dst$\dir1,0 0 * * * *,2000,800,xcp
jobwin2,\\192.168.0.200\src$\dir2,\\192.168.0.200\dst$\dir2,0 0 * * * *,2000,800,xcp
jobwin1,\\192.168.0.200\src$\dir3,\\192.168.0.200\dst$\dir3,0 0 * * * *,2000,800,robocopy,demo\user1,demo\users
jobwin4,\\192.168.0.200\src$\dir4,\\192.168.0.200\dst$\dir4,0 0 * * * *,2000,800,robocopy,demo\user1,demo\users


```

**2. assessment of existing filesystem**

Automatic assessment of the source filesystem, preparation of the destination file system and creation of the csv file can be achieved using the `asses` command.

for example if our source file system directory structure up to depth of 2 levels look as follows (bellow the subfolders we have many other files and directories). 

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
     ├── subfolder2
     └── file1
```
we can use the `asses` command to build this initial directory structure on the destination volume and automatically create the XCPtion CSV file for us.
XCPtion will analyze the source file system, will validate destination filesystem is not already contains data and will create the directory structure on the destination (using rsync).  

**directory structure is created using `rsync` on linux and `robocopy` on windows will not be updated to the destination if new files/directories are created bellow the paths managed by XCPtion jobs  
for example if a file is created under /src/folder1/ it should be manually updated to the destination**

```
user@master:~/xcption$ ./xcption.py asses -h
usage: xcption.py asses [-h] -s SOURCE -d DESTINATION -l DEPTH -c CSVFILE
                        [-p CPU] [-m RAM] [-r] [-u FAILBACKUSER]
                        [-g FAILBACKGROUP] [-j jobname]

optional arguments:
  -h, --help            show this help message and exit
  -s SOURCE, --source SOURCE
                        source nfs path (nfssrv:/mount)
  -d DESTINATION, --destination DESTINATION
                        destintion nfs path (nfssrv:/mount)
  -l DEPTH, --depth DEPTH
                        filesystem depth to create jobs, range of 1-12
  -c CSVFILE, --csvfile CSVFILE
                        output CSV file
  -p CPU, --cpu CPU     CPU allocation in MHz for each job
  -m RAM, --ram RAM     RAM allocation in MB for each job
  -r, --robocopy        use robocopy instead of xcp for windows jobs
  -u FAILBACKUSER, --failbackuser FAILBACKUSER
                        failback user required for xcp for windows jobs, see
                        xcp.exe copy -h
  -g FAILBACKGROUP, --failbackgroup FAILBACKGROUP
                        failback group required for xcp for windows jobs, see
                        xcp.exe copy -h
  -j jobname, --job jobname
                        xcption job name

```

Example of running asses on NFS job:

```
user@master:~/xcption$ sudo ./xcption.py asses -c example/nfsjob.csv -s 192.168.0.200:/nfssrc -d 192.168.0.200:/nfsdst -l 1 -p 1000 -m 800 -j jobnfs1
2019-09-06 15:31:39,709 - WARNING - source directory: 192.168.0.200:/nfssrc/ contains 1 files. those files will not be included in the xcption jobs and need to be copied externaly
please review the warnings above, do you want to continue? [y/N] y
2019-09-06 15:31:55,143 - INFO - job csv file:example/nfsjob.csv created
2019-09-06 15:31:55,144 - INFO - rsync can be used to create the destination initial directory structure for xcption jobs
2019-09-06 15:31:55,144 - INFO - rsync command to sync directory structure for the required depth will be:
2019-09-06 15:31:55,144 - INFO - rsync -av --exclude ".snapshot" --exclude="/*/*" "/tmp/src_24145/" "/tmp/dst_24145/"
2019-09-06 15:31:55,144 - INFO - (192.168.0.200:/nfssrc is mounted on:/tmp/src_24145 and 192.168.0.200:/nfsdst is mounted on:/tmp/dst_24145)
do you want to run rsync ? [y/N] y
2019-09-06 15:32:03,808 - INFO - =================================================================
2019-09-06 15:32:03,808 - INFO - ========================Starting rsync===========================
2019-09-06 15:32:03,808 - INFO - =================================================================
sending incremental file list
./
file.txt
dir1/
dir2/
dir3/
dir4/

sent 213 bytes  received 58 bytes  542.00 bytes/sec
total size is 0  speedup is 0.00
2019-09-06 15:32:03,825 - INFO - =================================================================
2019-09-06 15:32:03,825 - INFO - ===================rsync ended successfully======================
2019-09-06 15:32:03,825 - INFO - =================================================================
2019-09-06 15:32:03,826 - INFO - csv file:example/nfsjob.csv is ready to be loaded into xcption

user@master:~/xcption$ sudo cat example/nfsjob.csv
#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB
jobnfs1,192.168.0.200:/nfssrc/dir1,192.168.0.200:/nfsdst/dir1,0 0 * * * *,1000,800
jobnfs1,192.168.0.200:/nfssrc/dir2,192.168.0.200:/nfsdst/dir2,0 0 * * * *,1000,800
jobnfs1,192.168.0.200:/nfssrc/dir3,192.168.0.200:/nfsdst/dir3,0 0 * * * *,1000,800
jobnfs1,192.168.0.200:/nfssrc/dir4,192.168.0.200:/nfsdst/dir4,0 0 * * * *,1000,800

```

Example of running asses on CIFS job **(make sure to escape \ when using cifs paths \\\\SRV\\share will be typed as \\\\\\\\SRV\\\\share)**:

```
user@master:~/xcption$ sudo  ./xcption.py asses -c example/cifsjob.csv -s \\\\192.168.0.200\\src$ -d \\\\192.168.0.200\\dst$ -j cifsjob -l 1 --cpu 2000 --ram 100 --robocopy
2019-09-06 15:38:44,948 - INFO - validating src:\\192.168.0.200\src$ and dst:\\192.168.0.200\dst$ cifs paths are avaialble from one of the windows server
2019-09-06 15:39:03,180 - WARNING - source path: \\192.168.0.200\src$ contains 2 files. those files will not be included in the xcption jobs and need to be copied externaly
please review the warnings above, do you want to continue? [y/N] y
2019-09-06 15:39:09,498 - INFO - job csv file:example/cifsjob.csv created
2019-09-06 15:39:09,498 - INFO - robocopy can be used to create the destination initial directory structure for xcption jobs
2019-09-06 15:39:09,498 - INFO - robocopy command to sync directory structure for the required depth will be:
2019-09-06 15:39:09,498 - INFO - C:\NetApp\XCP\robocopy_wrapper.cmd /COPYALL /MIR /NP /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:2 "\\192.168.0.200\src$" "\\192.168.0.200\dst$" /XF * ------ for directory structure
2019-09-06 15:39:09,499 - INFO - C:\NetApp\XCP\robocopy_wrapper.cmd /COPYALL /MIR /NP /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:1 "\\192.168.0.200\src$" "\\192.168.0.200\dst$" ------ for files
do you want to run robocopy ? [y/N] y
2019-09-06 15:39:19,573 - INFO - =================================================================
2019-09-06 15:39:19,573 - INFO - ========================Starting robocopy========================
2019-09-06 15:39:19,573 - INFO - =================================================================

C:\NetApp\XCP\lib\alloc\d2a93b8a-2493-45b9-3b84-92c3ac878eda\win_C-_NetApp_XCP_r2481324813>c:\windows\system32\robocopy.exe /COPYALL /MIR /NP /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:2 \\192.168.0.200\src$ \\192.168.0.200\dst$ /XF *

-------------------------------------------------------------------------------
   ROBOCOPY     ::     Robust File Copy for Windows
-------------------------------------------------------------------------------

  Started : Friday, September 6, 2019 8:39:02 AM
   Source : \\192.168.0.200\src$\
     Dest : \\192.168.0.200\dst$\

    Files : *.*

Exc Files : *

  Options : *.* /TEE /S /E /COPYALL /PURGE /MIR /NP /LEV:2 /MT:16 /R:0 /W:0

------------------------------------------------------------------------------


------------------------------------------------------------------------------

               Total    Copied   Skipped  Mismatch    FAILED    Extras
    Dirs :         5         5         4         0         0         0
   Files :        40         0        40         0         0         0
   Bytes :   5.388 g         0   5.388 g         0         0         0
   Times :   0:00:00   0:00:00                       0:00:00   0:00:00
   Ended : Friday, September 6, 2019 8:39:02 AM



C:\NetApp\XCP\lib\alloc\efd1fe93-61c3-4848-f23e-1b9a32da3b78\win_C-_NetApp_XCP_r2481324813>c:\windows\system32\robocopy.exe /COPYALL /MIR /NP /DCOPY:DAT /MT:16 /R:0 /W:0 /TEE /LEV:1 \\192.168.0.200\src$ \\192.168.0.200\dst$

-------------------------------------------------------------------------------
   ROBOCOPY     ::     Robust File Copy for Windows
-------------------------------------------------------------------------------

  Started : Friday, September 6, 2019 8:39:05 AM
   Source : \\192.168.0.200\src$\
     Dest : \\192.168.0.200\dst$\

    Files : *.*

  Options : *.* /TEE /S /E /COPYALL /PURGE /MIR /NP /LEV:1 /MT:16 /R:0 /W:0

------------------------------------------------------------------------------

100%        New File                   0        \\192.168.0.200\src$\file - Copy.txt
100%        New File                   0        \\192.168.0.200\src$\file.txt

------------------------------------------------------------------------------

               Total    Copied   Skipped  Mismatch    FAILED    Extras
    Dirs :         1         1         0         0         0         0
   Files :         2         2         0         0         0         0
   Bytes :         0         0         0         0         0         0
   Times :   0:00:00   0:00:00                       0:00:00   0:00:00
   Ended : Friday, September 6, 2019 8:39:05 AM


2019-09-06 15:39:26,677 - INFO - =================================================================
2019-09-06 15:39:26,677 - INFO - =================robocopy ended successfully=====================
2019-09-06 15:39:26,677 - INFO - =================================================================
2019-09-06 15:39:26,677 - INFO - csv file:example/cifsjob.csv is ready to be loaded into xcption


user@master:~/xcption$ sudo cat example/cifsjob.csv
#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB,TOOL,FAILBACKUSER,FAILBACKGROUP
cifsjob,\\192.168.0.200\src$\dir4,\\192.168.0.200\dst$\dir4,0 0 * * * *,2000,800,robocopy,,
cifsjob,\\192.168.0.200\src$\dir3,\\192.168.0.200\dst$\dir3,0 0 * * * *,2000,800,robocopy,,
cifsjob,\\192.168.0.200\src$\dir2,\\192.168.0.200\dst$\dir2,0 0 * * * *,2000,800,robocopy,,
cifsjob,\\192.168.0.200\src$\dir1,\\192.168.0.200\dst$\dir1,0 0 * * * *,2000,800,robocopy,,

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

**to start verification using xcp (linux and windows) the `verify` subcommand should be used (verify is possiable only when baseline is complete)** 

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

can be filtered by specific job (-j), source (-s) and phase (-p)

```
user@master:~/xcption$ sudo ./xcption.py status -h
usage: xcption.py status [-h] [-j jobname] [-s srcpath] [-v] [-p phase] [-l]

optional arguments:
  -h, --help            show this help message and exit
  -j jobname, --job jobname
                        change the scope of the command to specific job
  -s srcpath, --source srcpath
                        change the scope of the command to specific path
  -v, --verbose         provide detailed information
  -p phase, --phase phase
                        change the scope of the command to specific phase
                        (basline,sync#)
  -l, --logs            display xcp logs
```


Example:

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

verbose output can be seen using the `-v` argument for the `status` command 


```
user@master:~/xcption$ sudo ./xcption.py status  -v  -s dir1
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

```
user@master:~/xcption# sudo ./xcption.py status -v -s \\\\192.168.0.200\\src$\\dir1 -p verify1 -l
JOB: cifsjob
SRC: \\192.168.0.200\src$\dir1
DST: \\192.168.0.200\dst$\dir1
SYNC CRON: 0 0 * * * * (NEXT RUN 07:05:28)
OS: WINDOWS
TOOL NAME: robocopy

 Phase    Start Time           End Time             Duration  Scanned      Reviewed  Copied  Modified  Deleted  Errors  Data Sent  Node  Status
 verify1  2019-09-06 16:49:47  2019-09-06 16:52:09  2m20s     5,372/5,372  5,372     -       -         -        -       -          WFA   equal

9 compared, 9 same, 0 different, 0 missing, 5s
22 compared, 22 same, 0 different, 0 missing, 10s
38 compared, 38 same, 0 different, 0 missing, 15s
58 compared, 58 same, 0 different, 0 missing, 20s
80 compared, 80 same, 0 different, 0 missing, 25s
105 compared, 105 same, 0 different, 0 missing, 30s
134 compared, 134 same, 0 different, 0 missing, 35s
159 compared, 159 same, 0 different, 0 missing, 40s
194 compared, 194 same, 0 different, 0 missing, 45s
287 compared, 287 same, 0 different, 0 missing, 50s
410 compared, 410 same, 0 different, 0 missing, 55s
455 compared, 455 same, 0 different, 0 missing, 1m0s
594 compared, 594 same, 0 different, 0 missing, 1m5s
736 compared, 736 same, 0 different, 0 missing, 1m10s
1,043 compared, 1,043 same, 0 different, 0 missing, 1m15s
1,403 compared, 1,403 same, 0 different, 0 missing, 1m20s
1,581 compared, 1,581 same, 0 different, 0 missing, 1m25s
1,998 compared, 1,998 same, 0 different, 0 missing, 1m30s
2,403 compared, 2,403 same, 0 different, 0 missing, 1m35s
2,666 compared, 2,666 same, 0 different, 0 missing, 1m40s
3,077 compared, 3,077 same, 0 different, 0 missing, 1m45s
3,486 compared, 3,486 same, 0 different, 0 missing, 1m50s
3,758 compared, 3,758 same, 0 different, 0 missing, 1m55s
4,201 compared, 4,201 same, 0 different, 0 missing, 2m0s
4,510 compared, 4,510 same, 0 different, 0 missing, 2m5s
4,664 compared, 4,664 same, 0 different, 0 missing, 2m10s
4,991 compared, 4,991 same, 0 different, 0 missing, 2m15s
5,372 compared, 5,372 same, 0 different, 0 missing, 2m20s

