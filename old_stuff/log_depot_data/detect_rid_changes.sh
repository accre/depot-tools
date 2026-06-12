#!/usr/bin/env bash

################################################################################
# Parse the log and look for changes.  Right now it's noting two types:
#
#  * Serial number changes (usually previous drive failed and was replaced)
#  * Backplane/slot changes (same drive was put in a different slot)
################################################################################

t=$(mktemp)

Logfile="/var/log/aggregate_drive_info.csv"

if [ ! -e "${Logfile}" ]; then
	echo "ERROR:  Logfile ${Logfile} not found on this server."
	exit 1
fi

# Date, backplane, slot, rid, serial
awk -F ',' '{print $1,",",$6,",",$4,",",$5,",",$8 }' ${Logfile} | sed "s/ , /,/g" > "${t}"

rids=$(cat "${t}" | cut -d "," -f 2 | sort | uniq)

p=$(mktemp)

for rid in ${rids}
do
        # Look for instances where the RID changed slot, backplane, or serial #.   If no changes, then
        # the drive hasn't changed
        diff=$(grep ",${rid}," "${t}" | cut -d "," -f 3,4,5 | sort | uniq)
        [[ ! ${diff} == *$'\n'* ]] && continue

        for i in ${diff}
        do
                change_time=$(grep "${rid},${i}$" "${t}" | cut -d "," -f 1 | head -n 1)
                echo "${change_time}|${rid}|${i}" >> "${p}"
        done
done

# Now iterate over our file of changes.
# We want to drop the first *time* the depot appears, as that's just it's initial logging
# We *don't* want to drop its state, as we will be referring to it going forward
rids=$(cat "${p}" | cut -d "|" -f 2 | sort | uniq)

s=$(mktemp)

# See when the first date mention in the log is.   Ignore messages on this date/time, as they
# are usually "set up" noise
first_date=$(cat ${Logfile} | head -n 1 | cut -d "," -f 1)

for rid in ${rids}
do
        grep "|${rid}|" "${p}" | cut -d "|" -f 1,3 | sort > "${s}"

        i=0
        IFS="/"
        for line in $(cat "${s}" | tr "\n" "/")
        do

                if [ "${i}" -eq "0" ]; then
                        # First time, just keep the state
                        State0=$(echo "${line}" | cut -d "|" -f 2)
                        i=$((i+1))
                        continue
                fi

                Time1=$(echo "${line}" | cut -d "|" -f 1)
                State1=$(echo "${line}" | cut -d "|" -f 2)


		if [[ "${Time1}" =~ "${first_date}" ]] ; then
			continue
		fi

                ### Now see if it's a backplane/slot change (indicating the drive has been moved)
                ### Or a serial # change (indicating the drive has been replaced)
                Backplane0=$(echo "${State0}" | cut -d "," -f 1)
                     Slot0=$(echo "${State0}" | cut -d "," -f 2)
                   Serial0=$(echo "${State0}" | cut -d "," -f 3)

                Backplane1=$(echo "${State1}" | cut -d "," -f 1)
                     Slot1=$(echo "${State1}" | cut -d "," -f 2)
                   Serial1=$(echo "${State1}" | cut -d "," -f 3)

                MSG=""
                if [ "${Serial0}" == "${Serial1}" ]; then

                        # It was a backplane/slot change.  See if we have source/destination slot info.
			# If not, it was probably a blip and can be ignored
			if [ -n "${Backplane0}" ] && [ -n "${Slot0}" ] && [ -n "${Backplane1}" ] && [ -n "${Slot1}" ] ; then
	                        MSG="Rid moved from ${Backplane0} ${Slot0} to ${Backplane1} ${Slot1}"
			fi
                else
			if [ -n "${Serial0}" ] && [ -n "${Serial1}" ]; then
	                        MSG="Drive ${Serial0} replaced with ${Serial1}"
			fi
                fi

                if [ -n "${MSG}" ]; then
			echo "${Time1} - ${rid} - ${MSG}"
		fi
                State0="${State1}"
        done

        rm -f "${s}"

done

rm -f "${t}" "${p}"
