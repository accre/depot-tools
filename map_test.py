#!/usr/bin/env python3

### Map drive -> enclosure/slot using sg_ses (hopefully a generic method that works on most/all depots without modification)

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

	multipath_ll = SysExec("multipath -ll")
	if re.search("DM multipath kernel driver not loaded", multipath_ll):
		return(False)

	# Now query multipath and see if it's actually running in multipath
	# mode or not
	num_lines = sum(1 for line in multipath_ll.splitlines())

	if num_lines == 0:
		return(False)
	else:
		return(True)


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
#                Debug("map_dm_to_mpath()::  dm_dev = " + str(dm_dev) + " and mpath_dev = " + str(mpath_dev))

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
 #               Debug("map_dm_to_sd_dev():: dm_dev = " + str(dm_dev) + " and sd_dev = " + str(sd_dev))

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

#                Debug("map_mpath_to_sd_dev()::  dm = " + str(dm) + " and mpath = " + str(mpath) + " and sd_dev = " + str(sd_dev))

        return(map)


def map_enclosures():

	map = {}

	for line in SysExec("lsscsi -guN").splitlines():

		if not re.search("enclosu", line):
			continue

		line = " ".join(line.split())

		hctl = line.split()[0]
		hctl = re.sub("(\[|\])", "", hctl)

		wwn  = line.split()[2]
		sg_dev = line.split()[4]

		# WWN maps to the backplane, while HCTL and SG_Dev map depend on number of HBA's.  For a depot with N hba's, they will have N unique values.
		if not sg_dev in map:
			map[sg_dev] = {}

		map[sg_dev]["wwn"]  = wwn
		map[sg_dev]["hctl"] = hctl

		# Figure out if it's the "front" or "back" backplane
		output = SysExec("sg_ses -p aes " + str(sg_dev)).splitlines()
		num_slots = 0
		for i in output:

			if re.search("Element type: SAS expander", i):
				break

			if re.search("Element index:", i):
				num_slots = num_slots + 1

		map[sg_dev]["num_slots"] = num_slots

		if num_slots == 12:
			map[sg_dev]["alias"] = "Back"

		if num_slots == 24:
			map[sg_dev]["alias"] = "Front"


		for line in SysExec("sg_ses -p cf " + sg_dev).splitlines():

			# There are other things that could be parsed out, but for now focus on these two

			if re.search("enclosure vendor:", line):
				enc_vendor = re.sub("vendor:", ":", line)
				enc_vendor = enc_vendor.split(":")[1].strip()
				map[sg_dev]["enc_vendor"] = enc_vendor

			if re.search("product:", line):
				enc_product = re.sub(" rev:", ":", line)
				enc_product = enc_product.split(":")[2].strip()
				map[sg_dev]["enc_product"] = enc_product

	return(map)


def map_sg_ses_enclosure_slot_to_sas_wwn():

	map = {}

	map_enc = map_enclosures()

	for enc in map_enc.keys():

		map[enc] = {}

		slot = ""
		sas_wwn = ""

		for line in SysExec("sg_ses -p aes " + str(enc)).splitlines():

			if not re.search("(Element index:|SAS address)", line):
				continue

			if re.search("attached SAS address", line):
				continue

			if re.search("Element index:", line):
				slot = ' '.join(line.split())
				slot = slot.split(":")[1]
				slot = ' '.join(slot.split())
				slot = slot.split()[0]

			if re.search("SAS address", line):
				sas_wwn = line.split(":")[1].strip()

			if slot and not slot in map[enc]:
				map[enc][slot] = {}

			if sas_wwn:
				map[enc][slot]["wwn"] = sas_wwn

			if slot and sas_wwn:

				slot = ""
				sas_wwn = ""

	return(map)


def map_sd_dev_to_sas_wwn():

	map = {}

	for line in SysExec("lsblk -S -o PATH,HCTL,WWN,SERIAL").splitlines():

		line = ' '.join(line.split())

		sd_dev  = line.split()[0]
		hctl    = line.split()[1]
		sas_wwn = line.split()[2]
		serial  = line.split()[3]

		if not re.search("/dev/", sd_dev):
			continue

		map[sd_dev] = {}
		map[sd_dev]["hctl"] = hctl
		map[sd_dev]["sas_wwn"] = sas_wwn
		map[sd_dev]["serial"] = serial

	return(map)


def Return_SD_Dev(wwn_1, map):

	for sd_dev in map.keys():

		wwn_2 = map[sd_dev]["sas_wwn"]

		# Now, the actual Serial may be Serial, or Serial +/- 3.   I wish I understood the logic here better.
		wwn_m1 = hex(int(wwn_2, 16) - 1)
		wwn_p1 = hex(int(wwn_2, 16) + 1)
		wwn_m2 = hex(int(wwn_2, 16) - 2)
		wwn_p2 = hex(int(wwn_2, 16) + 2)
		wwn_m3 = hex(int(wwn_2, 16) - 3)
		wwn_p3 = hex(int(wwn_2, 16) + 3)

		Serial_list = [ wwn_m3, wwn_m2, wwn_m1, wwn_2, wwn_p1, wwn_p2, wwn_p3 ]

		if wwn_1 in Serial_list:
			return(sd_dev)

	return("EMPTY")


### Main()::

# We need to get these mappings on all machines
map1 = map_enclosures()
map2 = map_sg_ses_enclosure_slot_to_sas_wwn()
map3 = map_sd_dev_to_sas_wwn()

Debug("map1 = " + str(map1))
Debug("map2 = " + str(map2))
Debug("map3 = " + str(map3))

# We need to do additional maps if multipathing is enabled
multipath_active = is_multipath_enabled()
Debug("Multipath_Active = " + str(multipath_active))

# Iterate over the map and add the "Front"/"Back" alias to the map.
for enclosure in map2:

	if map1[enclosure]:
		if map1[enclosure]["alias"]:
			alias = map1[enclosure]["alias"]
	else:
		alias = "unknown"
	for slot in map2[enclosure]:
		map2[enclosure][slot]["alias"] = alias + "_" + slot

# Iterate over the map and only leave backplanes from the lowest (h)ctl
min_h = 9999
for enclosure in map1:
	h     = int(map1[enclosure]["hctl"].split(":")[0])
	min_h = min(min_h, h)

for enclosure in map1:
	h     = int(map1[enclosure]["hctl"].split(":")[0])
	if h > min_h:
		del map2[enclosure]

# Add sd_dev (and mpath_dev for multipath devices) to the map
for enclosure in map2:
	for slot in map2[enclosure]:
		wwn = map2[enclosure][slot]["wwn"]
		sd_dev = Return_SD_Dev(wwn, map3)
		Debug("Enclosure " + str(enclosure) + " slot " + str(slot) + " maps to sd_dev " + str(sd_dev))
		map2[enclosure][slot]["sd_dev"] = sd_dev

		if multipath_active:
			map4 = map_mpath_to_sd_dev()
			for key, val in map4.items():

				val_list = val.split(",")

				if sd_dev.split("/")[2] in val_list:
					map2[enclosure][slot]["mpath_dev"] = "/dev/mapper/" + str(key)
					map2[enclosure][slot]["sd_dev"] = [ "/dev/" + x for x in val_list]
					continue
		continue

# Iterate over map2 and print
print("Enclosure\tSlot\tDrive")
for enclosure in map2:
	for slot in map2[enclosure]:
		print(enclosure +  "\t" + slot + "\t" + str(map2[enclosure][slot]))
