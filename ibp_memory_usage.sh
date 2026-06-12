#!/usr/bin/env bash

# What's the memory % limit before throwing warnings
MEM_THRESH="50"

# Assume failure until proven otherwise
STATUS=1

# Get the number of running IBP processes
NUM_DAEMONS=$(ps -ef | grep ibp_server | grep -c -v grep)

# Get the percentage of memory used by ibp_server
MEM=$(ps -eo %mem,pid,args | grep ibp_server | grep -E -v "(defunct|grep)" | awk '{ print $1 }' | cut -d "." -f 1)

# If there's not ibp daemon, error
if [ "${NUM_DAEMONS}" -eq "0" ]; then
        MSG="No running ibp_server daemon detected."
fi

# If there's more two or more ibp daemons, error
if [ "${NUM_DAEMONS}" -ne "0" ] && [ "${NUM_DAEMONS}" -ne "1" ]; then
        MSG="Multiple (${NUM_DAEMONS}) running ibp_server daemons detected."
fi

# If ibp is using too much memory, error
if [ "${MEM}" -ge "${MEM_THRESH}" ]; then
        MSG="ibp_server over ${MEM_THRESH} memory usage.  Please kill and restart. ${MSG}"
fi

# If everything looks good
if [ "${NUM_DAEMONS}" -eq "1" ] && [ "${MEM}" -lt "${MEM_THRESH}" ]; then
        MSG="OK"
        STATUS=0
fi

echo "${MEM}% - ${MSG}"
exit ${STATUS}
