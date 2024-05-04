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

stdbuf -i0 -o0 -e0 /usr/local/bin/xcp "$@" 
exitcode=$?

if [[ " $@ " =~ "-acl4" ]]; then
    umount /tmp/xcption_nfs4_src_mount$$
    if [ $? -eq 0 ]; then
    	rm -d /tmp/xcption_nfs4_src_mount$$
    fi
    umount /tmp/xcption_nfs4_dst_mount$$
    if [ $? -eq 0 ]; then
        rm -d /tmp/xcption_nfs4_dst_mount$$    
    fi
fi

exit $exitcode
