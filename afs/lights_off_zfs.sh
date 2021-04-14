#!/usr/bin/env bash

tmp=$(mktemp)

storcli64 /c0 show | grep "TB SAS" | awk '{ print $1 }' > ${tmp}

for i in $(cat ${tmp})
do
	e=$(echo ${i} | cut -d ":" -f 1)
	s=$(echo ${i} | cut -d ":" -f 2)

	storcli64 /c0/e${e}/s${s} stop locate
done

rm -f ${tmp}

