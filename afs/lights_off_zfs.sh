#!/usr/bin/env bash

# Get a list of all enclosure/slot id's
drives=$(storcli64 /c0 show | grep HDD | awk '{ print $1 }')

# Iterate over them and stop the location LED
for i in ${drives}
do
	e=$(echo ${i} | cut -d ":" -f 1)
	s=$(echo ${i} | cut -d ":" -f 2)

	storcli64 /c0/e${e}/s${s} stop locate
done
