#!/bin/bash

export XCP_LOG_DIR=/root/xcption/system/xcp_repo/xcplogs
echo 0 >  /proc/self/loginuid

if [[ " $@ " =~ "-acl4" ]]; then
    mkdir -p /tmp/xcption_nfs4_src_mount$$
    mount -t nfs4 $5 /tmp/xcption_nfs4_src_mount$$
    mkdir -p /tmp/xcption_nfs4_dst_mount$$
    mount -t nfs4 $6 /tmp/xcption_nfs4_dst_mount$$    
fi

/usr/local/bin/xcp "$@" 
exitcode=$?

if [[ " $@ " =~ "-acl4" ]]; then
    umount /tmp/xcption_nfs4_src_mount$$
    rm -d /tmp/xcption_nfs4_src_mount$$
    umount /tmp/xcption_nfs4_dst_mount$$
    rm -d /tmp/xcption_nfs4_dst_mount$$    
fi

exit $exitcode
