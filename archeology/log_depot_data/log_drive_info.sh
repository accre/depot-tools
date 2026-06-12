#!/usr/bin/env bash

### This command logs critical drive info once an hour:
###
### * Drive temperature
### * Drive enclosure/slot
### * Drive serial (in case bad rid is replaced with new one)

### Get the date for logging
Day=$(date "+%F")
Hour=$(date "+%H")
Date="${Day} ${Hour}:00:00"

### Pull Dev/Rid info from lsblock
lb=$(mktemp)
lsblock | grep disk:hd | awk '{ print $1,$2 }' | sed "s/ /,/" > "${lb}"

### Determine the enclosure type
Enclosure_tmp=$(lsscsi -g | grep "enclosu")

Enclosure_type="Unknown"
if [[ ${Enclosure_tmp} =~ "AIC" ]]; then
	Enclosure_type="AIC"
fi

if [[ ${Enclosure_tmp} =~ "80H10323501A0" ]]; then
	Enclosure_type="Chenbro"
fi

### Create an associative array to hold the names of our backplanes.  On all depots
### to date, Front backplane has 24 drives and Back backplane has 12
declare -A Backplane_Name

Backplanes=$(ls -1 /sys/class/enclosure)

for backplane in ${Backplanes}
do

	Count=$(ls -1 /sys/class/enclosure/"${backplane}"/ | grep -Ec "(Slot|Disk)")

	if [ "${Count}" -eq "24" ]; then
		Enc_Name="Front"
	elif [ "${Count}" -eq "12" ]; then
		Enc_Name="Back"
	else
		Enc_Name="Unknown"
	fi

	Backplane_Name["${backplane}"]="${Enc_Name}"
done

### Cache smartctl and lsslot results so we don't have to poll multiple times
s=$(mktemp)
l=$(mktemp)
lsslot | egrep -v "(Backplane|----)" | awk '{ print $2,$4,$8,$10 }' | sed "s/ /,/g" > ${l}

### Iterate over all drives and collect info
for i in $(cat "${lb}")
do
	DEV=$(echo "${i}" | cut -d "," -f 1)
	RID=$(echo "${i}" | cut -d "," -f 2)

	smartctl -a "${DEV}" > "${s}"

	### Poll SMART and get the temperature of the drive
	TEMP=$(grep -E '(Current Drive Temperature|Temperature_Celsius)' "${s}")

	if [[ ${TEMP} =~ "Current Drive Temperature" ]]; then
		TEMP=$(echo "${TEMP}" | awk '{ print $4 }')
	fi

	if [[ ${TEMP} =~ "Temperature_Celsius" ]]; then
		TEMP=$(echo "${TEMP}" | awk '{ print $10 }')
	fi

	dev=$(echo "${DEV}" | cut -d "/" -f 3)
	INFO=$(echo /sys/class/enclosure/*/*/device/block/"${dev}" 2>&1)

	if [[ ${INFO} =~ "/*/*/" ]]; then
		INFO=$(cat ${l} | grep ",${DEV},")
		Backplane=$(echo ${INFO} | cut -d "," -f 1)
		Slot=$(echo ${INFO} | cut -d "," -f 2)
	else
		### Pluck out the backplane
		BP=$(echo "${INFO}" | cut -d "/" -f 5)
		Backplane=${Backplane_Name[${BP}]}

		### Pluck out the slot
		Slot=$(echo "${INFO}" | cut -d "/" -f 6 | sed "s/Slot //" | sed "s/Disk//")
		Slot=$(echo ${Slot} | bc)
	fi

	### Get the model of the drive
	Model=$(grep -E "(Product|Device Model):" "${s}" | cut -d ":" -f 2- | sed "s/^  *//" | sed "s/  *$//")

	### Get the serial # of the drive in case we have to replace it
	Serial=$(grep "Serial [Nn]umber:" "${s}" | awk '{ print $3 }')

	echo "${Date},${HOSTNAME},${Enclosure_type},${Backplane},${Slot},${RID},${Model},${Serial},${TEMP}"

done

rm -f "${s}" "${lb}" "${l}"
