#!/usr/bin/env python3

import re
import os
import sys
import math
import time

from subprocess import Popen, PIPE, STDOUT

# Enable/disable debugging messages
Print_Debug = True

# Cache info from SysExec
CacheDataArray = {}
CacheTimeArray = {}

def Debug(text):

        """
        A wrapper to print debugging info on a single line.
        """

        if Print_Debug:
                print("DEBUG: " + text)
        return()


def which(program):

        """

        Functions similar to the 'which' program in Unix.  Given
        an executable filename, it will return the whole path to
        that executable.

        which("ls") should return "/bin/ls"

        Will print an error message and terminate the program if
        it can't locate the executable in the path.

        """

        def is_exe(fpath):
                return os.path.exists(fpath) and os.access(fpath, os.X_OK)

        def ext_candidates(fpath):
                yield fpath
                for ext in os.environ.get("PATHEXT", "").split(os.pathsep):
                        yield fpath + ext

        fpath, fname = os.path.split(program)

        if fpath:
                if is_exe(program):
                        return program
        else:
                for path in os.environ["PATH"].split(os.pathsep):
                        exe_file = os.path.join(path, program)
                        for candidate in ext_candidates(exe_file):
                                if is_exe(candidate):
                                        return candidate


# If a required binary isn't available, quit.
def Bin_Requires(bin):

        # Because "bin" is required for this script to run, we do a little
        # extra work trying to find it before giving up.

        if os.path.isfile("/sbin/" + bin):
                return "/sbin/" + bin
        elif os.path.isfile("/usr/sbin/" + bin):
                return  "/usr/sbin/" + bin
        elif os.path.isfile("/usr/local/sbin/" + bin):
                return  "/usr/local/sbin/" + bin

        bin_path = which(bin)
        if not bin_path:
                print("ERROR: Could not locate " + bin + " in the PATH")
                sys.exit()
        return bin_path

# If a recommended binary isn't available, you can still run, but let
# the user know it would work better if the binary was available
def Bin_Recommends(bin):
        bin_path = which(bin)
        #if not bin_path:
        #       print("INFO:  This program would run better with " + bin + " in the PATH")
        return bin_path


# If a suggested binary isn't available, run anyway
def Bin_Suggests(bin):
        return which(bin)

Bin_Requires("storcli64")

def SysExec(cmd):

        """
        Run the given command and return the output
        """

        # Cache the output of the command for 20 seconds
        Cache_Expires = 20

        # Computed once, used twice
        Cache_Keys = CacheDataArray.keys()

### Why is this broken??!?
#        Cache_Keys = list(Cache_Keys)
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

        return(Return_Val)

def parse_storcli_allvirtdrives():
	"""
	Return a parsed version of "storcli /cALL/eALL/sALL show all"
	"""

	output = SysExec("storcli64 /cALL/vALL show all")

	parse_output = {}

	# Pass 1:  Pluck out all the "key = val" lines and put them into a dict
	for line in output.splitlines():

		if not re.search("/c| = ", line):
			continue

		if re.search("^CLI Version|^Operating system|^Controller|^Status|^Description", line):
			continue

		if re.search("^Drive", line) and re.search(" - Detailed Information :| State:| Device attributes :| Policies/Settings :", line):
			continue

		spl = line.split(" = ")

		if len(spl) == 1:
			ces = spl[0].split(" ")[1]
			parse_output[ces] = {}
		else:
			key = line.split(" = ")[0].lower().strip().replace(" ", "_")
			val = line.split(" = ")[1].strip().replace(" ", "_")

			parse_output[ces][key] = val


	# Pass 2:  Parse this section:
	#
	# -----------------------------------------------------------------------------
	# EID:Slt DID State DG      Size Intf Med SED PI SeSz Model            Sp Type
	# -----------------------------------------------------------------------------
	# 9:12     10 Onln   0 10.913 TB SAS  HDD N   N  512B ST12000NM0027    U  -

	# EID:Slt == Enclosure Device ID:Slot No.
	# DID = Device ID
	# State = Drive State
	# DG = DriveGroup
	# Size = Size of Drive
	# Intf = Interface (SAS, SATA, etc.)
	# Med  = Media Type
	# SED  = Self Encryptive Drive
	# PI   = Protection Info
	# SeSZ = Sector Size
	# Model = Drive Model
	# Sp   = Spun [(U)p, (D)own, etc]
	# Type = ???
	Drive_info_headers = [ "EID:Slt", "DID", "State", "DG", "Size", "Size_Units", "Intf", "Med", "SED", "PI", "SeSz", "Model", "Sp", "Type" ]

	Drive = ""
	Drive_info = {}
	for line in output.splitlines():

		if not re.search("Drive |:", line):
			continue

		if re.search("^Drive", line) and re.search(" - Detailed Information :| State:| Device attributes :| Policies/Settings :|position", line):
			continue

		if re.search("Port Information|EID:Slt|Drive Temperature|Inquiry Data", line):
			continue

		if re.search("Drive", line):
			Drive = line.split()[1]
		else:
			tmp = line.split()
			Drive_info = dict(zip([x.lower() for x in Drive_info_headers], tmp))

		if Drive and Drive_info:
			for key, val in Drive_info.items():
				parse_output[Drive][key] = val

			Drive = ""
			Drive_info = {}


	# Pass 3:  Parse this section:
	#
	# Port Information :
	# -----------------------------------------
	# Port Status Linkspeed SAS address
	# -----------------------------------------
	#    0 Active 12.0Gb/s  0x5000c500a6c97269
	#    1 Active 12.0Gb/s  0x0

	Port_info_headers = ["Port", "State", "Speed", "SASAddr"]

	Drive = ""
	Port0_info = []
	Port1_info = []
	for line in output.splitlines():

		if not re.search("Drive|0x", line):
			continue

		if re.search("Detailed Information|State|Device attributes|Policies|=|\|", line):
			continue

		if re.search("Drive", line):
			Drive = line.split()[1]

		if re.search(" 0 ", line):
			tmp = line.split()
			Port0_info = dict(zip([x.lower() for x in Port_info_headers], tmp))

		if re.search(" 1 ", line):
			tmp = line.split()
			Port1_info = dict(zip([x.lower() for x in Port_info_headers], tmp))

		if Drive and Port0_info and Port1_info:
			for key, val in Port0_info.items():
				parse_output[Drive][key + "_0"] = val
			for key, val in Port1_info.items():
				parse_output[Drive][key + "_1"] = val

	return(parse_output)

storcli_info = parse_storcli_allvirtdrives()

# For debugging, take one drive and print out its info
foo = storcli_info["/c0/e8/s1"]
for key, val in foo.items():
	print("/c0/e8/s1 " + key + " = " + val)
