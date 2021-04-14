#!/bin/sh

ZFS_PATH="/sys/module/zfs/parameters"

set_zfs_val () {
	if [ ! -e "${ZFS_PATH}/${1}" ]; then
		echo "INFO::  ${1} variable not found in ${ZFS_PATH}"
	else
		echo "INFO::  Setting ${ZFS_PATH}/${1} to ${2}..."
		echo ${2} > ${ZFS_PATH}/${1}
	fi
}

set_zfs_val zfs_resilver_delay  0
set_zfs_val zfs_scrub_delay     0
set_zfs_val zfs_top_maxinflight 512
set_zfs_val zfs_resilver_min_time_ms 8000
set_zfs_val zfs_vdev_async_read_max_active 12
set_zfs_val zfs_vdev_async_read_min_active 8
set_zfs_val zfs_vdev_async_write_max_active 12
set_zfs_val zfs_vdev_async_write_min_active 8
set_zfs_val zfs_vdev_scrub_max_active 4
set_zfs_val zfs_vdev_scrub_min_active 2
