#!/usr/bin/env python

import os
import re
import sys
import socket
import logging
import psutil

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')
#logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

def SysExecZ(Cmd):
	logging.debug(Cmd)

def Help_RID_SetRWState():
	print("")
	print(sys.argv[0] + " - Get/Set the RO/RW state of a given RID")
	print("")
	print("USAGE:  " + sys.argv[0] + " [get|set] <Rid> [ro|rw]")
	print("")
	sys.exit(1)

def Die(Msg):
	logging.error(Msg)
	sys.exit(1)

def mark_ro(Rid):

	logging.debug("Entering mark_ro::")

	RO_Size = "1"

	Set_Ini_Option(Config_File, Sec, Key, Val)

	SysExecZ("set_rid_option " + str(Rid) + " rid  max_size " + str(RO_Size))
	SysExecZ("set_rid_option " + str(Rid) + " rid soft_size " + str(RO_Size))
	SysExecZ("set_rid_option " + str(Rid) + " rid hard_size " + str(RO_Size))


def mark_rw(Rid):

	logging.debug("Entering mark_rw::")

	Rid_to_Dev_Dict = Generate_Rid_to_Dev_Dict()
	Dev = Rid_to_Dev_Dict[Rid]

	# Get the capacity of the drive in bytes
	Capacity = findRawSize(Dev.split("/")[-1])

	# This is a heuristically determined (not carved in stone)
	# scale factor relating capacity to the RW_Size by taking our
	# existing values in our old bash script and doing a regression.
	Scale = 1123454

	RW_Size = Capacity / Scale

	SysExecZ("set_rid_option " + str(Rid) + " rid  max_size " + str(RW_Size))
	SysExecZ("set_rid_option " + str(Rid) + " rid soft_size " + str(RW_Size))
	SysExecZ("set_rid_option " + str(Rid) + " rid hard_size " + str(RW_Size))


# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
        if re.search("pychecker", i):
                sys.argv.remove(i)

        if re.search("time", i):
                sys.argv.remove(i)

if len(sys.argv) != 4:
	Help_RID_SetRWState()

IBP_Hostname = socket.gethostname()
IBP_Port = "6714"
Verb = sys.argv[1]
Rid = sys.argv[2]
State = sys.argv[3]

logging.debug("Hostname = " + str(IBP_Hostname) + " and Port = " + str(IBP_Port))
logging.debug("Verb = " + str(Verb) + " and Rid = " + str(Rid) + " and State = " + str(State))

if Verb != "get" and Verb != "set":
	Die("Didn't specifiy either \"get\" or \"set\"")

if State != "ro" and State != "rw":
	Die("Didn't specify either \"rw\" or \"ro\"")

Metadata_Path = LocateMetadata(Rid)

if Metadata_Path == "UNKNOWN":
	Die("Cannot determine path to metadata for Rid " + Rid)

if Metadata_Path.startswith("PATH:"):
	Metadata_Path = Metadata_Path.split(":")[-1]

Umount_Necessary = False
if Metadata_Path.startswith("BLOCKDEV:"):
	Dev = Metadata_Path.split(":")[-1]
	# Now mount this somewhere...

	Umount_Necessary = True
	print("You need to code this case one of these days...")

if Verb == "set":

	IBP_Server_Status = IBP_Server_Status()
	if IBP_Server_Status == "Running":
#		RID_Detach(Rid)

		if State == "ro":
			mark_ro(Rid)
		elif State == "rw":
			mark_rw(Rid)

#		RID_MergeConfig()

#		RID_Attach(Rid)

	else:

		if State == "ro":
			mark_ro(Rid)
		elif State == "rw":
			mark_rw(Rid)

#		RID_MergeConfig()

#		IBP_Server_Start()

elif Verb == "get":

	RID_Settings = Metadata_Path + "/rid.settings" # /depot/import/md-${RID}/rid.settings

	Max_Size = 1
	Hard_Size = 1
	Soft_Size = 1

	f = open(RID_Settings, "r")
	for line in f.read().splitlines():

		if re.search("^max_size", line):
			Max_Size = int(line.split("=")[1].strip())

		if re.search("^hard_size", line):
			Hard_Size = int(line.split("=")[1].strip())

		if re.search("^soft_size", line):
			Soft_Size = int(line.split("=")[1].strip())

	f.close()

	logging.debug("Max_Size = "  + str(Max_Size))
	logging.debug("Hard_Size = " + str(Hard_Size))
	logging.debug("Soft_Size = " + str(Soft_Size))

	if Max_Size == 1 and Hard_Size == 1 and Soft_Size == 1:
		This_State = "ro"
	else:
		This_State = "rw"


	logging.debug("State = " + str(State) + " and This_State = " + str(This_State))

	if State == This_State:
		print("1")
	else:
		print("0")

