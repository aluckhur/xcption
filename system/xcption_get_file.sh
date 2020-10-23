#!/bin/bash
/usr/bin/wget $1 --output-document $2

if [ $? -eq 0 ]
then
	echo "success file download from $1 to $2 on `hostname`"
	exit 0
fi
echo "failed file download from $1 to $2 on `hostname`"
exit 1
