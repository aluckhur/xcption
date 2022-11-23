#!/bin/bash

/usr/bin/rclone "$@" | tee
exitcode=$?
exit $exitcode
