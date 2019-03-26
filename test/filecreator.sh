#!/bin/bash
for j in {1..1000000}}
do
	dir="dir${RANDOM}"
	for i in {1..100}
	do
		for src in {1..3}
		do
			mkdir -p /xcp/src${src}/${dir}
			dd if=/dev/sda of=/xcp/src${src}/${dir}/file${RANDOM} bs=${RANDOM} count=1
		done	
	done
	RAND2=$(( ( RANDOM % 9 )  + 1 ))
	for src in {1..3}
	do
		rm -rf /xcp/src${src}/dir${RAND2}*
	done
	sleep 10
done


