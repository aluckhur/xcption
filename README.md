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



