#!/usr/bin/env python

import os
import re
import sys

from ridlib import *

def RID_Run_SmartTest(Rid, TestType = "short"):

	if TestType != "short" and TestType != "long":
		print("ERROR:  You requested a " + TestType + " SMART test which isn't supported.")
		sys.exit(1)

	# Just promote it to a string here...
	Rid = str(Rid)

	Rid_to_Dev = Generate_Rid_to_Dev_Dict()

	if Rid not in Rid_to_Dev:
		print("ERROR:  Could not find Rid " + Rid + " on this system.")
		sys.exit(1)

	Dev = Rid_to_Dev[Rid]

	print("DEBUG:  Dev = " + Dev)

	# I want to check and see if there's already a SMART test running before
	# spawning another.   Unfortunately, this test only works on SATA drives.
	Drive_Protocol = Determine_Drive_Protocol(Dev)

	if Drive_Protocol == "SATA":

		Test_in_Progress = False
		for line in SysExec("smartctl -c " + Dev).splitlines():
			if re.search("Self-test routine in progress", line):
				Test_in_Progress = True
				break

		print("DEBUG:  Test_in_Progress = " + str(Test_in_Progress))

	# Start a SMART test...
	SysExec("smartctl -t " + TestType + " " + Dev)

RID_Run_SmartTest(3660, TestType = "short")
