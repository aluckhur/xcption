#!/bin/bash
echo "CMD: /usr/bin/rclone $@"
/usr/bin/rclone "$@" | tee | egrep -v "^\s+*\s+"
exitcode=$?
exit $exitcode
