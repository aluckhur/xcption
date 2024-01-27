#!/usr/bin/bash
BASEDIR=/mnt/c/Temp/

./xcption.py status -o csv > ${BASEDIR}/full.csv

sed 's/,//g; s/\t/,/g; s/nfs:\/\///g; s/\#//; s/@[^,]*,/,/g' ${BASEDIR}/full.csv > ${BASEDIR}/full_tab_phase1.csv
awk 'BEGIN {FS=OFS=","} NR>1 {split($12, a, /[hms]+/); $12 = a[1]*60 + a[2] + a[3]/60} 1' ${BASEDIR}/full_tab_phase1.csv > ${BASEDIR}/full_tab_phase2.csv
awk 'BEGIN {FS=OFS=","} {for (i=13; i<=18; i++) gsub(/-/, "0", $i)} 1' ${BASEDIR}/full_tab_phase2.csv > ${BASEDIR}/full_tab.csv

rm -rf ${BASEDIR}/full_tab_phase*

