#!/usr/bin/env python

import os
import re
import sys

from ridlib import *

def Help_Set_Rid_Option():
	print("")
	print(sys.argv[0] + " - Set the config value for a particular rid")
	print("")
	print("USAGE:  " + sys.argv[0] + " <RID> [rid|db] <key> <value>")
	print("")
	sys.exit(1)

def Set_Rid_Option(Rid, Sec, Key, Val):

	Section = "resource " + Rid

	if Sec == "db":
		Section = "db " + Rid

	# In a better version of this program, it would detect the metadata location and
	# then operate on it.   Until then, this is a direct Bash-to-Python translation of
	# Alan's original script
	Config_File = "/depot/rid-" + Rid + "/md/rid.settings"

	Set_Ini_Option(Config_File, Sec, Key, Val)

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
	if re.search("pychecker", i):
		sys.argv.remove(i)

if len(sys.argv) != 5:
	Help_Set_Rid_Option()

Rid = sys.argv[1]
Sec = sys.argv[2]
Key = sys.argv[3]
Val = sys.argv[4]

Set_Rid_Option(Rid, Sec, Key, Val)
