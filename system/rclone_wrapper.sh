#!/bin/bash
echo "CMD: /usr/bin/rclone $@"
/usr/bin/rclone "$@" | tee
exitcode=$?
exit $exitcode
