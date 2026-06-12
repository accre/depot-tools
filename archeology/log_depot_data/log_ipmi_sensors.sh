#!/usr/bin/env bash

### Log the IPMI sensors to a log file

### Get the date for logging
Day=$(date "+%F")
Hour=$(date "+%H")
Date="${Day} ${Hour}:00:00"

t=$(mktemp)

# Dump ipmi sensors to temp logfile
sudo ipmitool sensor | sed "s/|/,/g" | tr "\t" " " | sed "s/  */ /g" | sed "s/ ,/,/g" | sed "s/, /,/g" | sed "s/ *$//" | sed -e 's/^\|$/"/g' -e 's/,/","/g' > "${t}"

IFS="|"
cat "${t}" | while IFS= read -r line
do
	echo "\"${Date}\",\"${HOSTNAME}\",${line}"
done

rm -f "${t}"
