#!/bin/bash

set -x

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
XCP_REPO_MOUNT_POINT=${SCRIPT_DIR}/xcp_repo
SLEEP_BETWEEN_RUNS=10

while true
do
#	rsync -avh --prune-empty-dirs --exclude xcption_gc* --include '*/' --include="*.stderr.*" --exclude "*" ${NOMAD_ALLOC_DIR} ${TMP_REPORT_DIR}
#	find $tmpreportdir -mtime +${DELETE_AFTER_DAYS} -execdir rm -- '{}' +
	${SCRIPT_DIR}/../xcption.py nomad
	#curl     --request PUT     http://localhost:4646/v1/system/gc
	sleep $SLEEP_BETWEEN_RUNS
done
#nomad status | grep xcption_gc/periodic | head --lines=-1 | grep dead | awk '{system("nomad job stop -purge "$1)}'

