#!/bin/bash

set -x

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
XCP_REPO_MOUNT_POINT=${SCRIPT_DIR}/xcp_repo
SLEEP_BETWEEN_RUNS=10

while true
do
	${SCRIPT_DIR}/../xcption.py nomad
	sleep $SLEEP_BETWEEN_RUNS
done

