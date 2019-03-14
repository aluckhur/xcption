# xcption

## What is XCPtion?

XCPtion is a wrapper utility for [NetApp XCP](https://xcp.netapp.com/) NFS filecopy/migration utility
XCPtion will be able to run and manage multiple XCP jobs paralely in a distributed fasion by using underlying services from Hashi Corp [Nomad](https://www.nomadproject.io/) scheduler.

## Where do I get the NAbox?

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

XCPtion uses a CSV format as an input file, The CSV file contains the following columns:

JOB NAME - A name for the JOB, later on actions and output can be filtered by this name

SOURCE PATH - Source NFSv3 path. The source should be mountable as root from all instances in the cluster 

DEST PATH - Destination NFSv3 path. The source should be mountable as root from all instances in the cluster 

SYNC SCHED (optional) - sync schedule in [cron](http://www.nncron.ru/help/EN/working/cron-format.htm) format (DEFAULT is daily @ midnight:`0 0 * * * *`)

CPU MHz - The allocated CPU frequency for the job (DEFAULT:3000)

RAM MB - The allocated RAM for the job (DEFAULT:800)


Example for the file:

#JOB NAME,SOURCE PATH,DEST PATH,SYNC SCHED,CPU MHz,RAM MB

job1,192.168.100.2:/xcp/src15,192.168.100.3:/xcp/dst15

job1,192.168.100.2:/xcp/src16,192.168.100.3:/xcp/dst16

job2,192.168.100.2:/xcp/src1,192.168.100.4:/xcp/dst1,*/20 * * * *,2000,2800

job2,192.168.100.2:/xcp/src2,192.168.100.4:/xcp/dst2,*/3 * * * *,3000,2800

job2,192.168.100.2:/xcp/src3,192.168.100.4:/xcp/dst3,* * * * *,5000,2800

job2,192.168.100.2:/xcp/src4,192.168.100.4:/xcp/dst4,*/10 * * * *,2323,22800

job2,192.168.100.2:/xcp/src5,192.168.100.4:/xcp/dst5,*/15 * * * *,100,22800

job2,192.168.100.2:/xcp/src6,192.168.100.4:/xcp/dst6,*/20 * * * *,100,24400





