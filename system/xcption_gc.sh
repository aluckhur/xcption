#!/bin/bash

NOMAD_ALLOC_DIR="/var/lib/nomad/alloc"
XCP_REPO_MOUNT_POINT="/root/xcption/system/xcp_repo"
TMP_REPORT_DIR="${XCP_REPO_MOUNT_POINT}/tmpreports"
DELETE_AFTER_DAYS=30

mkdir -p $TMP_REPORT_DIR

rsync -zavC --ignore-existing --prune-empty-dirs --include '*/' --include="*.stderr.*" --exclude "*" ${NOMAD_ALLOC_DIR} ${TMP_REPORT_DIR}
find $tmpreportdir -mtime +${DELETE_AFTER_DAYS} -execdir rm -- '{}' +
