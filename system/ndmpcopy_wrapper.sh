#!/bin/bash 

if [ "$1" == "verify" ]; 
then
    echo ""
    echo ""
    echo "=========================================="
    echo "verify is not supported for ndmpcopy tasks"
    echo "=========================================="
    exit 1
fi

echo "CMD: ssh $@"
ssh "$@" | tee
exitcode=$?
exit $exitcode
