#!/usr/bin/env bash

[ "${#}" -eq "1" ] || exit

force_umount_rids () {

	# Look for any rid- folders in /depot that didn't unmount properly and force them
	for dir in $(ls -1 /depot | grep rid\-)
	do
		rid=$(echo "${dir}" | rev | cut -d "-" -f 1 | rev)
		dev=$(ls -alh /dev/disk/by-label | grep "rid-data-${rid}" | rev | cut -d "/" -f 1 | rev | sed "s/[0-9]$//")

		# Umount the rid
		umount_rid.py "${rid}"

		# if the /depot/rid- entry still exists, umount -l and umount_rid
		# This can happen if the drive is active and slow to umount
		if [ -e "/depot/rid-${rid}" ]; then
			umount -l "${dev}"
			umount_rid.py "${rid}"
		fi
	done
}

stop_ibp_server () {
	ikill.py
	umount_all_rids.py
        force_umount_rids
	fsck_all.py
}

start_ibp_server() {
        force_umount_rids
	fsck_all.py
	mount_all_rids.py
	merge_config.py
	ibp_server.py -d /depot/ibp.conf
}

restart_ibp_server() {
	stop_ibp_server
	start_ibp_server
}


case "${1}" in

  "start")
    start_ibp_server
    ;;

  "stop")
    stop_ibp_server
    ;;

  "restart")
    restart_ibp_server
    ;;

  *)
    echo "Unrecognized command.  Valid commands are 'start', 'stop', and 'restart'"
    exit 1
    ;;
esac
