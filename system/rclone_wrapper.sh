#!/bin/bash
echo "CMD: /usr/bin/rclone $@"
stdbuf -i0 -o0 -e0 /usr/bin/rclone "$@" | tee | egrep -v "^\s+*\s+"
exitcode=$?
exit $exitcode
