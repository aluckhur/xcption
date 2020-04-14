#!/bin/bash -x 
echo 0 >  /proc/self/loginuid
/usr/local/bin/xcp $* 

