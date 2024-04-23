#!/bin/bash
for j in {1..1000000}}
do
	dir="dir${RANDOM}"
	for i in {1..100}
	do
		for src in {1..3}
		do
			mkdir -p $1//${src}/${dir}
			dd if=/dev/sda of=$1/${src}/${dir}/file${RANDOM} bs=100000 count=1
		done	
	done
	RAND2=$(( ( RANDOM % 9 )  + 1 ))
	for src in {1..3}
	do
		rm -rf $1/src${src}/dir${RAND2}*
	done
	sleep 10
done


