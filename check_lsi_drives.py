#!/accre/admin/bin/adm-python

"""
LSI drive check - Check the output of "storcli64" and report any drives that are
even a tiny bit odd.  Note that the "storcli64" needs to be runnable by the 'nrpe' user via sudo
"""

import re
import os
import sys
import math
import time
import threading

# Note:  Any time you can avoid using Popen is a huge win time-wise
from subprocess import Popen, PIPE, STDOUT

CacheDataArray = {}
CacheTimeArray = {}

# Set "True" to print debugging info
Print_Debug = False

def Debug(text):

        """
        A wrapper to print debugging info on a single line.
        """

        if Print_Debug:
                print("DEBUG: " + text)
        return()


def SysExec(cmd):

        """
        Run the given command and return the output
        """

        # Cache the output of the command for this many seconds
        Cache_Expires = 60

        # Computed once, used twice
        Cache_Keys = list(CacheDataArray.keys())
        if cmd in Cache_Keys:
                Cache_Age  = time.time() - CacheTimeArray[cmd]
        else:
             	Cache_Age  = 0

        Return_Val = "ERROR"

        # If we have valid data cached, return it
        if cmd in Cache_Keys and Cache_Age < Cache_Expires:
                Return_Val = CacheDataArray[cmd]

        # If the cmd is "cat", use fopen/fread/fclose to open it and
        # cache it as we go
        elif not cmd in Cache_Keys and cmd.split()[0] == "cat":
                f = open(cmd.split()[1], "r")
                CacheDataArray[cmd] = f.read()
                CacheTimeArray[cmd] = time.time()
                f.close()
                Return_Val = CacheDataArray[cmd]

        # If we don't have cached data, or it's too old, regenerate it
        elif not cmd in Cache_Keys or Cache_Age > Cache_Expires:
                CacheDataArray[cmd] = Popen(cmd.split(), stdout=PIPE, stderr=STDOUT).communicate()[0]
                CacheTimeArray[cmd] = time.time()
                Return_Val = CacheDataArray[cmd]

        if str(type(Return_Val)) == "<class 'bytes'>":
                Return_Val = Return_Val.decode("utf-8")

        return Return_Val


### Return values
INFO = 0
WARN = 1
CRIT = 2

### Get raw drive info so we can get a list of drives and see if any are in a bad state
Drives_Raw = SysExec("sudo /usr/local/bin/storcli64 /c0 show")

### Array to hold any bad drives
Bad_Drives = []
Bad_Drive_State = {}

### Parse Drives_Raw and get a list of e:s pairs
Drives = []

for line in Drives_Raw.splitlines():

	if not re.search("SAS", line):
		continue

	if not re.search("^[1-9]", line):
		continue

	Drives.append(line.split(" ")[0])

	if re.search("Onln", line):
		continue

	if re.search("UGood", line):
		continue

	if re.search("JBOD", line):
		continue

	if re.search("DRIVE", line):
		continue

	line = " ".join(line.split())
	es = line.split(" ")[0]
	msg = line.split(" ")[2]
	Bad_Drives.append(es)


### Run storcli show all on all drives.   We do this in parallel using SysExec
### once, and subsequent access will fetch from SysExec cache, which speeds
### things up noticably
jobs = []
for d in Drives:
	e = d.split(":")[0]
	s = d.split(":")[1]

	Debug("Spawning SysExec 'sudo /usr/local/bin/storcli64 /c0/eE/sS show all' process on e:s " + d)
	p = threading.Thread(target = SysExec, args = ("sudo /usr/local/bin/storcli64 /c0/e" + e + "/s" + s + " show all", ))
	jobs.append(p)
	p.start()

Debug("Waiting for SysExec() jobs to complete...")
for job in jobs:
	job.join()


### Defaults when things are really weird
error_level = -666
error_level_txt = "UNKNOWN"

### Iterate over all drives and look for any non-normal error counters
for d in Drives:

	e = d.split(":")[0]
	s = d.split(":")[1]

	drive_info = SysExec("sudo /usr/local/bin/storcli64 /c0/e" + e + "/s" + s + " show all")

	# Default to "fail safe", ie warn if you don't know what's going on.
	media_error       = "Yes"
	other_error       = "Yes"
	predict_fail      = "Yes"
	last_predict_fail = "Yes"
	smart_alert       = "Yes"

	for line in drive_info.splitlines():

		if re.search("^Media Error Count", line):
			media_error = line.split("=")[1].strip()

		if re.search("^Other Error Count", line):
			other_error = line.split("=")[1].strip()

		if re.search("^Predictive Failure Count", line):
			predict_fail = line.split("=")[1].strip()

		if re.search("^Last Predictive Failure Event Sequence", line):
			last_predict_fail = line.split("=")[1].strip()

		if re.search("^S.M.A.R.T alert flagged by drive", line):
			smart_alert = line.split("=")[1].strip()

	# SMART errors need to be treated as CRIT
	if smart_alert != "No":
		error_level = CRIT

	error_finding = media_error + " " + other_error + " " + predict_fail + " " + last_predict_fail + " " + smart_alert

	# This is the return on working non-JBOD drives
	if error_finding == "0 0 0 0 No":
		continue

	# This is the return on working JBOD drives
	if error_finding == "N/A N/A N/A N/A N/A":
		continue

#	print("DEBUG: error_finding for " + d + " = " + error_finding)

	# If there are any deviations from perfect, consider it a WARN
	error_level = max(WARN, error_level)

	Bad_Drives.append(d)

### Print our error message and done
if error_level == 0:
	error_level_txt = "INFO"
if error_level == 1:
	error_level_txt = "WARN"
if error_level == 2:
	error_level_txt = "CRIT"

if len(Bad_Drives) == 0:
	return_code = INFO
	return_txt = "OK"
else:
	return_code = error_level
	return_txt  = error_level_txt + ": Following drives are showing unusual drive states: " + ",".join(Bad_Drives)

print(return_txt)
sys.exit(return_code)
