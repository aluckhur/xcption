#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
XCP_REPO_MOUNT_POINT=${SCRIPT_DIR}/xcp_repo
SLEEP_BETWEEN_RUNS=10

/usr/bin/wget $1 --output-document $2

if [ $? -eq 0 ]
then
	echo "success file downloading from $1 to $2 on `hostname`"
	exit 0
fi
echo "failed file downloading from $1 to $2 on `hostname`"
exit 1
