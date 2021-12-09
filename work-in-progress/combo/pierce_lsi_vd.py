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

def SysExec(cmd):

        """
        Run the given command and return the output
        """

        # Cache the output of the command for 20 seconds
        Cache_Expires = 20

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

        return(Return_Val)


VD_to_PD_Map = {}
VD = []
scsi_naa_id = ""
PD = []
for line in SysExec("storcli64 /c0 /vall show all").splitlines():

	if not re.search("/c0/|SCSI NAA| HDD ", line):
		continue

	if re.search("/c0/", line):
		VD = line.split("/")[2].split()[0]

	if re.search(" HDD ", line):
		PD.append(line.split()[0])

	if re.search("SCSI NAA", line):
		scsi_naa_id = line.split("=")[1].strip()

	if PD and VD and scsi_naa_id:

		VD_to_PD_Map[VD] = {}

		VD_to_PD_Map[VD]["scsi_naa_id"] = scsi_naa_id
		VD_to_PD_Map[VD]["PD_List"] = PD

		VD = []
		scsi_naa_id = ""
		PD = []


for VD, list in VD_to_PD_Map.items():
	print("DEBUG:  Parsing virtual disk " + VD)

	print("DEBUG:  scsi_naa_id = " + VD_to_PD_Map[VD]["scsi_naa_id"])

	PD_List = VD_to_PD_Map[VD]["PD_List"]
	for i in PD_List:

		e = i.split(":")[0]
		s = i.split(":")[1]
		print("DEBUG: i = " + i + " and e = " + e + " and s = " + s)

		cmd = "storcli64 /c0/e" + str(e) + "/s" + str(s) + " show all"
		print("DEBUG:  cmd = " + cmd)

		cmd_output = SysExec(cmd)
		print("DEBUG: cmd_output = " + cmd_output)

		for line in SysExec(cmd).splitlines():
			if re.search("^WWN", line):
				WWN = line.split("=")[1].strip()

		print("DEBUG:  " + i  + " = " + WWN)
