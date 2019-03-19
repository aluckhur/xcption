#!/bin/bash

set -x

NOMAD_ALLOC_DIR="/var/lib/nomad/alloc"
XCP_REPO_MOUNT_POINT=`cat /etc/fstab | grep xcp_repo | awk '{print($2)}'`
TMP_REPORT_DIR="${XCP_REPO_MOUNT_POINT}/tmpreports"
DELETE_AFTER_DAYS=30
SLEEP_BETWEEN_RUNS=10
#NUMBER_OF_SERVERS_IN_THE_CLUSTER=`nomad node status | grep ready| wc -l`
#echo "${NUMBER_OF_SERVERS_IN_THE_CLUSTER} servers in the nomad cluster"

mkdir -p $TMP_REPORT_DIR

while true
do
	rsync -avh --prune-empty-dirs --exclude xcption_gc* --include '*/' --include="*.stderr.*" --exclude "*" ${NOMAD_ALLOC_DIR} ${TMP_REPORT_DIR}
	find $tmpreportdir -mtime +${DELETE_AFTER_DAYS} -execdir rm -- '{}' +
	sleep $SLEEP_BETWEEN_RUNS
done
#nomad status | grep xcption_gc/periodic | head --lines=-1 | grep dead | awk '{system("nomad job stop -purge "$1)}'
/usr/sbin/xcption.py -c nomadcache nomad
