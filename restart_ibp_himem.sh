#!/usr/bin/env bash

### Log the current IBP memory usage, and restart if it is above the threshold

# Log file
LOG="/var/log/ibp_memory_usage.log"

# Default memory threshold
MEM_THRESH="25.0"

# How many ibp_server daemons are running
NUM_DAEMONS=$(ps -ef | grep ibp_server | grep -c -v grep)

# The default log message
MSG="OK"

# Current datetime
DT=$(date +"%Y-%m-%d %H:%M:%S %Z")

# Default values
MEM="NA"
IBP_UPTIME="NA"
IBP_CONN="NA"
IBP_OPS="NA"

if [ "${NUM_DAEMONS}" -ne "1" ]; then
	if [ "${NUM_DAEMONS}" -eq "0" ]; then
		MSG="No running ibp_server daemon detected."
	else
		MSG="Multiple (${NUM_DAEMONS}) running ibp_server daemons detected."
	fi
else

	MEM=$(ps -eo %mem,pid,args | grep ibp_server | grep -E -v "(defunct|grep)" | awk '{ print $1 }')

	# Get IBP stats so we can look for correlations
	tmp=$(mktemp)
	get_version -a > "${tmp}"
	IBP_UPTIME=$(cat "${tmp}" | grep ^Uptime | cut -d " " -f 2)
	IBP_CONN=$(cat "${tmp}" | grep ^"Total Commands" | cut -d ":" -f 3 | cut -d "(" -f 1 | sed "s/ //g")
	IBP_OPS=$(cat "${tmp}" | grep ^"Total Commands" | cut -d ":" -f 2 | cut -d "(" -f 1 | sed "s/ //g")

	if (( $(echo "${MEM} >= ${MEM_THRESH}" | bc -l) )); then

		MSG="ibp_server over ${MEM_THRESH}% memory usage.  Restarting ibp_server..."

		ikill.py
		umount_all_rids.py
		fsck_all.py
		mount_all_rids.py
		merge_config.py
		ibp_server.py -d /depot/ibp.conf
	else
		MSG="ibp_server using ${MEM}% memory usage."
	fi
fi

echo "${DT}|${MEM}%|${IBP_UPTIME}|${IBP_CONN}|${IBP_OPS}|${MSG}" | tee -a ${LOG}
rm -f "${tmp}"
