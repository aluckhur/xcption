#!/bin/bash
ssh slave1 wondershaper clear enp0s8
ssh slave2 wondershaper clear enp0s8
rm -rf /root/xcption/system/xcp_repo/catalog/*
rm -rf /root/xcption/system/xcp_repo/tmpreports/*
rm -rf /root/xcption/system/xcp_repo/nomadcache/*

rm -rf /root/xcption/jobs/*
rm -rf /mnt/slave1/xcp/*
rm -rf /mnt/slave2/xcp/*
for i in {1..20}
do
	for j in {1..2}
	do
		mkdir /mnt/slave$j/xcp/dst$i
		chmod -R 777 /mnt/slave$j

	done	
done


if [[ $(nomad status) != "No running jobs" ]]; then
    for job in $(nomad status | awk {'print $1'} || grep /)
    do  
        # Skip the header row for jobs.
        if [ $job != "ID" ]; then
			echo "killing job $job"
            nomad stop -purge -detach $job > /dev/null
        fi  
    done
fi
curl     --request PUT     http://localhost:4646/v1/system/gc
df | grep /var/lib/nomad/alloc | awk '{system( "umount "$6)}'

