#!/usr/bin/env bash

for i in $(storcli64 /c0 show all | grep ^[89] | grep -v RAID0 | awk '{ print $1 }')
do
	e=$(echo ${i} | cut -d ":" -f 1)
	s=$(echo ${i} | cut -d ":" -f 2)

	error=$(storcli64 /c0/e${e}/s${s} show all | grep -i error | grep -v " = 0$")

	[ -z "${error}" ] && continue

	echo "${i} - ${error}"
done
