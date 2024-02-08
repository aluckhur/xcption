#!/bin/bash

export SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

export XCP_LOG_DIR=${SCRIPT_DIR}/xcp_repo/xcplogs
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
