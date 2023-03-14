#!/bin/bash

# NRPE check for zpool
# Written by: Søren Klintrup <soren at klintrup.dk>
# Cleanups by Mathew.Binkley@Vanderbilt.edu

INFO=0 ; WARN=1 ; CRIT=2

ZPOOL=$(which zpool 2>&1 | grep -v which)

debug () {
:
#	echo "DEBUG::  ${1}"
}

debug "zpool binary = ${ZPOOL}"

if [ ! -x "${ZPOOL}" ]; then
	echo "zpool binary does not exist on system"
	exit ${INFO}
fi

unset ERRORSTRING
unset OKSTRING
unset ERR

DEVICES="$(sudo zpool list -H -o name)"

debug "DEVICES = ${DEVICES}"
#DEVICES="pool1"

for DEVICE in ${DEVICES}
do
	debug "Scanning ${DEVICE}..."

	DEVICESTRING="$(sudo zpool list -H -o health "${DEVICE}")"

	debug "DEVICESTRING = ${DEVICESTRING}"

	if [ "$(echo "${DEVICESTRING,,}" | sed -Ee 's/.*(degraded|faulted|offline|online|removed|unavail).*/\1/')" = "" ]; then

		ERRORSTRING="${ERRORSTRING} / ${DEVICE}: unknown state"

		if ! [ "${ERR}" = ${WARN} ]; then
			ERR=${CRIT}
		fi

	else
		case $(echo "${DEVICESTRING,,}" | sed -Ee 's/.*(degraded|faulted|offline|online|removed|unavail).*/\1/') in
			degraded)
				ERR=${CRIT}
				ERRORSTRING="${ERRORSTRING} / ${DEVICE}: DEGRADED"
				;;
			offline)
				ERR=${CRIT}
				ERRORSTRING="${ERRORSTRING} / ${DEVICE}: OFFLINE"
				;;
			removed)
				ERR=${CRIT}
				ERRORSTRING="${ERRORSTRING} / ${DEVICE}: REMOVED"
				;;
			unavail)
				ERR=${CRIT}
				ERRORSTRING="${ERRORSTRING} / ${DEVICE}: UNAVAIL"
				;;
			faulted)
				ERR=${CRIT}
				ERRORSTRING="${ERRORSTRING} / ${DEVICE}: FAULTED"
				;;
			online)
				OKSTRING="${OKSTRING} / ${DEVICE}: online"
				;;
		esac
	fi
done

if [ "${1}" ]; then
	if [ "${ERRORSTRING}" ]; then
		echo "${ERRORSTRING} ${OKSTRING}" | sed s/"^\/ "// | mail -s "$(hostname -s): ${0} reports errors" -E "${*}"
	fi
else
	if [ "${ERRORSTRING}" ] || [ "${OKSTRING}" ]; then
		echo "${ERRORSTRING} ${OKSTRING}" | sed s/"^\/ "//
		exit ${ERR}
	else
		echo no zpool volumes found
		exit ${CRIT}
	fi
fi
