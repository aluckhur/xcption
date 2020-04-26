#!/bin/bash
echo 0 >  /proc/self/loginuid
/usr/local/bin/xcp "$@" 

