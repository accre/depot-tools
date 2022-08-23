#!/usr/bin/env python3

### Map drive -> enclosure/slot on the new depots with multipathing

import re
import os
import sys
import math
import time

# Note:  Any time you can avoid using Popen is a huge win time-wise
from subprocess import Popen, PIPE, STDOUT

# Cache info
CacheDataArray = {}
CacheTimeArray = {}

# Enable/disable debugging messages
Print_Debug = False

def Debug(text):

        """
        A wrapper to print debugging info on a single line.
        """

        if Print_Debug:
                print("DEBUG: " + text)
        return

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

        return Return_Val


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

def is_multipath_enabled():

	# Quick and dirty, but works for now.

	# Verify if the multipath binary exists in the PATH.  If not, then
	# it's not running multipath
	if not which("multipath"):
		return(False)

	# Now query multipath and see if it's actually running in multipath
	# mode or not
	num_lines = sum(1 for line in SysExec("multipath -ll").splitlines())

	if num_lines == 0:
		return(False)
	else:
		return(True)

multipath_active = is_multipath_enabled()

if not multipath_active:
	print("ERROR:  Multipathing is not enabled on this depot.")
	sys.exit(0)

def map_dm_to_mpath():

	map = {}

	for line in SysExec("ls -alh /dev/mapper").splitlines():

		if re.search("part", line):
			continue

		if not re.search("mpath", line):
			continue

		line = " ".join(line.split())

		dm_dev = line.split()[-1].split("/")[1]
		mpath_dev = line.split()[-3]

		map[dm_dev] = mpath_dev
		Debug("map_dm_to_mpath()::  dm_dev = " + str(dm_dev) + " and mpath_dev = " + str(mpath_dev))

	return(map)


def map_dm_to_sd_dev():

	map = {}

	for line in SysExec("ls -1 /sys/block").splitlines():
		if not re.search("^dm", line):
			continue

		dm_dev = line
		sd_dev = SysExec("ls -1 /sys/block/" + str(dm_dev) + "/slaves")
		sd_dev = sd_dev.replace("\n", ",").strip().rstrip(",")

		if re.search("dm-", sd_dev):
			continue

		map[dm_dev] = sd_dev
		Debug("map_dm_to_sd_dev():: dm_dev = " + str(dm_dev) + " and sd_dev = " + str(sd_dev))

	return(map)


def map_mpath_to_sd_dev():

	map = {}

	map_1 = map_dm_to_sd_dev()
	map_2 = map_dm_to_mpath()

	dict_1 = dict(map_1)
	dict_2 = dict(map_2)

	for dm in sorted(dict_1):

		sd_dev = map_1[dm]
		mpath  = map_2[dm]

		map[mpath] = sd_dev

		Debug("map_mpath_to_sd_dev()::  dm = " + str(dm) + " and mpath = " + str(mpath) + " and sd_dev = " + str(sd_dev))

	return(map)


def map_sd_dev_to_sn_wwn():

	# Instead of using smartctl, use "lsblk -S -o +WWN".  This returns instantly
	# and is vastly faster than parsing "smartctl" output like the 1st iteration
	# of this script tried to to.

	map = {}

	map_1 = map_mpath_to_sd_dev()
	sd_devs = list(map_1.values())

	for line in SysExec("lsblk -S -o +WWN").splitlines():

		if not re.search(" sas ", line):
			continue

		line = " ".join(line.split())

		sd_dev = line.split()[0]
		sn     = line.split()[6]
		wwn    = line.split()[8]

		map[sd_dev] = {}
		map[sd_dev]["sn"] = sn
		map[sd_dev]["wwn"] = wwn

		Debug("map_sd_dev_sn_wwn()::  sd_dev = " + str(sd_dev) + " and sn = " + str(sn) + " and wwn = " + str(wwn))

	Debug("map_sd_dev_sn_wwn():: map = " + str(map))

	return(map)

def map_sn_to_mpath_sd_dev_wwn():

	map_1 = map_mpath_to_sd_dev()
	map_2 = map_sd_dev_to_sn_wwn()

	map = {}

	for sd_dev in map_2.keys():

		wwn = map_2[sd_dev]["wwn"]
		sn  = map_2[sd_dev]["sn"]

		map[sn] = {}

		for mpath_dev, sd_devs in map_1.items():

			sd_list = sd_devs.split(",")

			if not sd_dev in sd_list:
				continue

			map[sn]["mpath"] = mpath_dev
			map[sn]["sd_devs"] = sd_devs
			map[sn]["wwn"] = wwn

	return(map)


def map_sn_to_storcli_enclosure_slot_wwn():

	map = {}

	for line in SysExec("storcli64 /c0 show all").splitlines():

		if not re.search("^Drive|^SN|^WWN", line):
			continue

		if re.search("Policies|Detailed Information|State|Device attributes|Driver Name|Driver Version|Drive Coercion", line):
			continue

		if re.search("^Drive", line):
			ces = line.split()[1]

		if re.search("^SN", line):
			sn = line.split("=")[1].strip()

		if re.search("^WWN", line):
			wwn = line.split("=")[1].strip()

		if 'ces' in locals() and 'sn' in locals() and 'wwn' in locals():

			Debug("map_sn_to_storcli_enclosure_slot_wwn()::  ces = " + str(ces) + " sn = " + str(sn) + " wwn = " + str(wwn))

			map[sn] = {}

			map[sn]["ces"] = ces
			map[sn]["wwn"] = wwn

			del(sn)
			del(ces)
			del(wwn)

	return(map)


def map_mpath_to_storcli_enclosure_slot():

	map = {}

	map_1 = map_sn_to_mpath_sd_dev_wwn()
	map_2 = map_sn_to_storcli_enclosure_slot_wwn()

	for sn in map_1.keys():

		mpath   = map_1[sn]["mpath"]
		sd_devs = map_1[sn]["sd_devs"]
		ces     = map_2[sn]["ces"]

		es = "/".join(ces.split("/")[2:])

		map[mpath] = {}
		map[mpath]["sd_devs"] = sd_devs
		map[mpath]["es"]      = es

	return(map)


map = map_mpath_to_storcli_enclosure_slot()

for key, val in map.items():

	mpath = key
	sd_devs = map[mpath]["sd_devs"]
	es      = map[mpath]["es"]

	print(str(mpath) + "|" + str(sd_devs) + "|" + str(es))
