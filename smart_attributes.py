#!/usr/bin/env python3

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

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
        if re.search("pychecker", i):
                sys.argv.remove(i)

        if re.search("time", i):
                sys.argv.remove(i)

if len(sys.argv) != 2:
	Help_Smart_Attributes()

Dev = sys.argv[1]

Drive_Attributes = Smart_Attributes(Dev)

# Do some formatting so we can pretty-print the info.   First,
# get the length of the longest key/val so we can format the output
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

print(FORMAT % ("Attribute", "Value", "Worst", "Thresh", "Raw"))
print("=========================================================================")

for key, val in Drive_Attributes.iteritems():

	val = Drive_Attributes[key]

	Attr   = val.split(" ")[0]
	Value  = val.split(" ")[1]
	Worst  = val.split(" ")[2]
	Thresh = val.split(" ")[3]
	Raw    = val.split(" ")[4]

	print(FORMAT % (Attr, Value, Worst, Thresh, Raw))

