#!/usr/bin/env bash

### SNMP data to a log file

### Get the date for logging
Day=$(date "+%F")
Hour=$(date "+%H")
Date="${Day} ${Hour}:00:00"

t=$(mktemp)

### Dump SNMP output to file.   1st col = key, 2nd col = units, 3rd col = value
snmpwalk -v 2c -c reddnetcms localhost | sed "s/=/|/" | sed "s/:/|/" | sed "s/ *|/|/g" | sed "s/|  */|/g" > ${t}

IFS="\\"
cat "${t}" | while IFS= read -r line
do
	key=$(echo ${line} | cut -d "|" -f 1)
	units=$(echo ${line} | cut -d "|" -f 2)
	val=$(echo ${line} | cut -d "|" -f 3 | sed "s/^\"//" | sed "s/\"$//" | strings)

	echo "\"${Date}\",\"${HOSTNAME}\",\"${key}\",\"${units}\",\"${val}\"" | sed "s/\"\"\"\"/\"\"/g"
done

rm -f "${t}"
