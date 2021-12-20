#!/usr/bin/env bash

##
## LSI drive check - Check the output of "storcli64" and report any drives that are
## even a tiny bit odd. - Mat
##

INFO=0 ; WARN=1 ; CRIT=2

# Get a list of all drives
DRIVES=$(sudo storcli64 /c0 show | grep SAS | grep ^[1-9] | cut -d " " -f 1)

tmp=$(mktemp)

BAD_DRIVES=$(sudo storcli64 /c0 show | grep SAS | grep ^[1-9] | grep ":" | egrep -v "(Onln|UGood)" | grep -v DRIVE | awk '{ print $1, $3 }' | sed "s/ /|/" | tr "\n" " " | sed "s/^ *//" | sed "s/ *$//")

error_level=${INFO}
for i in ${DRIVES}
do
        e=$(echo ${i} | cut -d ":" -f 1)
        s=$(echo ${i} | cut -d ":" -f 2)
        sudo storcli64 /c0/e${e}/s${s} show all > ${tmp}

        media_error=$(cat ${tmp} | grep "^Media Error Count" | cut -d "=" -f 2 | sed "s/ //g")
        other_error=$(cat ${tmp} | grep "^Other Error Count" | cut -d "=" -f 2 | sed "s/ //g")
        predict_fail=$(cat ${tmp} | grep "^Predictive Failure Count" | cut -d "=" -f 2 | sed "s/ //g")
        last_predict_fail=$(cat ${tmp} | grep "^Last Predictive Failure Event Sequence" | cut -d "=" -f 2 | sed "s/ //g")
        smart_alert=$(cat ${tmp} | grep "^S.M.A.R.T alert flagged by drive" | cut -d "=" -f 2 | sed "s/ //g")

	# SMART errors need to be treated as CRIT
	if [ ${smart_alert} != "No" ]; then
		error_level=${CRIT}
	fi

        error_finding="${media_error} ${other_error} ${predict_fail} ${last_predict_fail} ${smart_alert}"

        [ "${error_finding}" == "0 0 0 0 No" ] && continue

	if [ "${error_level}" -eq "${INFO}" ]; then
		error_level=${WARN}
	fi

        BADDRIVES=$(echo "${BADDRIVES},${i}" | sed "s/^,//")
done

rm -f ${tmp}

case ${error_level} in

	0)
	error_level_txt="INFO"
	;;

	1)
	error_level_txt="WARN"
	;;

	2)
	error_level_txt="CRIT"
	;;
esac


if [ -z "${BADDRIVES}" ]; then
	return_code=${INFO}
	return_text="OK '$(whoami)'"
else
	return_code=${error_level}
	return_text="${error_level_txt}: Following drives are showing unusual drive states:  ${BADDRIVES}"
fi

echo "${return_text} "
exit ${return_code}
