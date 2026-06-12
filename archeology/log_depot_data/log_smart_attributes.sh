#!/usr/bin/env bash

### Get the date for logging
Day=$(date "+%F")
Hour=$(date "+%H")
Date="${Day} ${Hour}:00:00"

DRIVES=$(lsblock | grep /dev/ | awk '{ print $1,$2 }' | tr " " ",")

t=$(mktemp)

for line in ${DRIVES}
do

	DEV=$(echo ${line} | cut -d "," -f 1)
	RID=$(echo ${line} | cut -d "," -f 2)

	if [ "${RID}" == "NORID" ]; then

		# See if it's the OS SSD
		d=$(echo ${DEV} | cut -d "/" -f 3)

		is_rotational=$(cat /sys/block/${d}/queue/rotational)

		if [ "${is_rotational}" -eq "0" ]; then
			RID="OS_SSD"
		fi
	fi

	smart_attributes.py ${DEV} | grep "[0-9]_" | awk '{ print $1,$2,$3,$4,$5 }' | tr " " ":" > ${t}

	for entry in $(cat ${t})
	do

		echo "${Date},${HOSTNAME},${RID},${entry}"

	done
done

