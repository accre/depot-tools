#!/usr/bin/env python

"""
Return a list of SMART attributes for a drive.   It tries to be smart and
return usable numbers for regular SATA drives as well as SAS drives.
"""

import os
import re
import sys
import tempfile
import collections

from ridlib import *

def Help_Smart_Attributes():
	print("")
	print(sys.argv[0] + " - Query the status of all SMART attributes on a drive.")
	print("")
	print("USAGE:  " + sys.argv[0] + " <device>")
	print("")
	sys.exit(1)

if len(sys.argv) != 2:
	Help_Smart_Attributes()

Dev = sys.argv[1]

# If Dev doesn't exist, bail out now...

f = open("/sys/block/" + Dev.split("/")[-1] + "/device/model")
Model = f.read().strip()
f.close()

# How to determine if a drive is SATA or SAS.  At some point we need to improve this...
SAS_Models = [ "ST8000NM0075", "ST4000NM0023", "WD4000F9YZ" ]
SAS=0
if Model in SAS_Models:
	SAS = 1

Drive_Attributes = {}

if SAS == 1:

	Attr = SysExec("smartctl -a " + Dev)

	for line in Attr.splitlines():

		# Some SAS attributes can be mapped to corresponding SATA attributes
		if re.search("^Accumulated start-stop cycles", line):
			t = line.split(":")[1].strip()
			Drive_Attributes[4] = "4_Start_Stop_Count " + t + " 0 0 " + t

		if re.search("number of hours powered up", line):
			t = line.split("=")[1].strip().split(".")[0]
			Drive_Attributes[9] = "9_Power_On_Hours " + t + " 0 0 " + t

		if re.search("Current Drive Temperature", line):
			t = line.split(":")[1]
			t = re.sub("C", "", t).strip()
			Drive_Attributes[194] = "194_Temperature_Celsius " + t + " " + t + " 0 " + t

		# Others we'll create unique SAS attributes for
		if re.search("^Elements in grown defect list", line):
			t = line.split(":")[1].strip()
			Drive_Attributes[9000] = "9000_SAS_Grown_Defect_List " + t + " 0 0 " + t

		if re.search("^Manufactured in", line):
			t = re.sub("Manufactured in ", "", line)
			t = re.sub(" of year ", ",", t)
			t = re.sub(" " "_", t)
			Drive_Attributes[9001] = "9001_SAS_Manufacture_Date 0 0 0 " + t

		if re.search("^read:", line):
			t = ' '.join(line.split())
			t = t.split(" ")[6].split(".")[0]
			Drive_Attributes[9002] = "9002_SAS_Gigabytes_Read " + t + " 0 0 " + t

		if re.search("^write:", line):
			t = ' '.join(line.split())
			t = t.split(" ")[6].split(".")[0]
			Drive_Attributes[9003] = "9003_SAS_Gigabytes_Write " + t + " 0 0 " + t

else:

	Attr = SysExec("smartctl --attributes " + Dev)

	for line in Attr.splitlines():

		line = line.lstrip()

		if not re.search("^[0-9]", line):
			continue

		line = ' '.join(line.split())

		Num    = line.split(" ")[0]
		Txt    = line.split(" ")[1]
		Val    = line.split(" ")[3]
		Worst  = line.split(" ")[4]
		Thresh = line.split(" ")[5]
		Raw    = line.split(" ")[9]

		key = int(Num)
		val = Num + "_" + Txt + " " + Val + " " + Worst + " " + Thresh + " " + Raw

		Drive_Attributes[key] = val

# Get the length of the longest key/val so we can format the output
pad_len = 3
len_key = 9
len_value = 5
len_worst = 5
len_thresh = 6
len_raw = 3
for key in Drive_Attributes:
	val = Drive_Attributes[key]
	len_key    = max(len(val.split(" ")[0]), len_key)
	len_value  = max(len(val.split(" ")[1]), len_value)
	len_worst  = max(len(val.split(" ")[2]), len_worst)
	len_thresh = max(len(val.split(" ")[3]), len_thresh)
	len_raw    = max(len(val.split(" ")[4]), len_raw)

FORMAT = "%-" + str(len_key+pad_len) + "s %-" + str(len_value+pad_len) + "s %-" + str(len_worst+pad_len) + "s %-" + str(len_thresh+pad_len) + "s %-" + str(len_raw+pad_len) + "s"

print FORMAT % ("Attribute", "Value", "Worst", "Thresh", "Raw")
print("=========================================================================")

sorted = collections.OrderedDict(sorted(Drive_Attributes.items()))
for key, val in sorted.iteritems():
#for key, val in sorted(Drive_Attributes.iteritems(), key=lambda (k,v): (v,k)):

	val = Drive_Attributes[key]

	Attr   = val.split(" ")[0]
	Value  = val.split(" ")[1]
	Worst  = val.split(" ")[2]
	Thresh = val.split(" ")[3]
	Raw    = val.split(" ")[4]

	print FORMAT % (Attr, Value, Worst, Thresh, Raw)


#	print(key + " " + Drive_Attributes[key])

#	printf '%-30s %-8s %-8s %-8s %-15s\n' ${Attr} ${Value} ${Worst} ${Thresh} ${Raw}


#ridlib.py:	FORMAT="%-6s %4s  %-13s %-11s  %-25s %-25s"
#ridlib.py:		print FORMAT % ("RID", "Type", "Data", "Metadata", "Import Metadata", "Sequester Status")

