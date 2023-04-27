#!/bin/bash
echo "CMD: ssh $@"
ssh "$@" | tee
exitcode=$?
exit $exitcode
