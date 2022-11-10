#!/usr/bin/env python3

### Map drive -> enclosure/slot using sg_ses (hopefully a generic method that works on most/all depots without modification)

import re
import os
import sys
import math
import time

from prettytable import PrettyTable

# Note:  Any time you can avoid using Popen is a huge win time-wise
from subprocess import Popen, PIPE, STDOUT

# Cache info
CacheDataArray = {}
CacheTimeArray = {}

# Enable/disable debugging messages
Print_Debug = True

def Debug(input):

	"""
	Print debugging info on a single line.
	"""

	this_type = str(type(input))

	if Print_Debug:

		if this_type == "<class 'dict'>":
			for key in input.keys():
				print("DEBUG: " + str(key) + " - " + str(input[key]))
		else:
			print("DEBUG: " + str(input))


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


def parse_lsblk():

	"""
	Return info on all block devices and partitions.
	Note:  RHEL8 has an ancient version of "lsblk" compared to Ubuntu, and is missing some useful fields. :-/
	"""

	Debug("def parse_lsblk() entry")

	map = {}

	for line in SysExec(" lsblk -O -P").splitlines():

		# Parse all the keyval pairs
		keyval  = dict(re.findall(r'(\w+)="([^"]+)"', line))

		# Fetch the sd_dev device and delete it from the keyval pair
		name = keyval["NAME"]
		del keyval['NAME']

		if re.search("loop", name):
			continue

		map["/dev/" + name] = keyval

	Debug("parse_lsblk():: final_map = " + str(map))
	Debug("def parse_lsblk() exit")

	return(map)


def parse_lsblk_disks():

	"""
	parse_lsblk() returns info on disks, partitions, and possibly other things.   Use this to filter it down to just disks

	"""

	Debug("def parse_lsblk_disks() entry")

	map  = parse_lsblk()

	# First, iterate over map, find the lowest (h)ctl
	min_h = 9999
	for key in map.keys():

		# Skip non-SCSI drives that don't have a HCTL value
		if "HCTL" not in map[key]:
			continue

		h = int(map[key]["HCTL"].split(":")[0])

		min_h = min(h, min_h)

	# Create a working copy that only contains "disk" info
	map2 = {}

	for key in map.keys():

		if map[key]["TYPE"] != "disk":
			continue

		if "HCTL" not in map[key]:
			continue

		this_h    = int(map[key]["HCTL"].split(":")[0])

		if this_h != min_h:
			continue

		map2[key] = map[key]

	# Iterate over the initial map again.   If there is "mpath" data,
	# pluck it out and add it to the new map
	for key in map.keys():

		if map[key]["TYPE"] != "mpath":
			continue

		# keys to save are "NAME" (mpatha), "KNAME" (dm-0), "PATH" (/dev/mapper/mpatha), "PTUUID" (to match), "PKNAME" (sda)

		for key2 in map2.keys():

			if map2[key2]["PTUUID"] == map[key]["PTUUID"]:

				Debug("foo map[key] = " + str(map[key]))

				map2[key2]["MP_NAME"]   = key.split("/")[-1]
				map2[key2]["MP_KNAME"]  = map[key]["KNAME"]
				map2[key2]["MP_PKNAME"] = map[key]["PKNAME"]
				map2[key2]["MP_PATH"]   = map[key]["PATH"]
				break

	# foobar

	Debug("parse_lsblk_disks():: final_map = " + str(map))
	Debug("def parse_lsblk_disks() exit")

	return(map2)


def parse_lsscsi():

	"""
	Parse the output of "lssci -gUN" into a dict
	"""

	Debug("def parse_lsscsi() entry")

	map = {}

	c = 0

	for line in SysExec("lsscsi -gUN").splitlines():

		line = ' '.join(line.split())

		hctl    = line.split()[0]
		hctl    = re.sub("\]", "", hctl)
		hctl    = re.sub("\[", "", hctl)
		type    = line.split()[1]
		sas_wwn = line.split()[2]
		sd_dev  = line.split()[3]
		sg_dev  = line.split()[4]

		# If the sd_dev doesn't point to an actual sd_dev, give it a fake one
		if sd_dev == "-":
			sd_dev = "/dev/null" + str(c)
			c = c + 1

		map[sd_dev] = {}
		map[sd_dev]["sg_dev"]  = sg_dev
		map[sd_dev]["hctl"]    = hctl
		map[sd_dev]["sas_wwn"] = sas_wwn
		map[sd_dev]["type"]    = type

	# Since we have two HBA's, each backplane is visible twice.  Let's eliminate duplicate copies by
	# iterating over the map and only leaving backplanes from the lowest (h)ctl
	min_h = 9999
	for sd_dev in map:
		h     = int(map[sd_dev]["hctl"].split(":")[0])
		min_h = min(min_h, h)

	map2 = {}
	for sd_dev, dict in map.items():
		h     = int(map[sd_dev]["hctl"].split(":")[0])
		if h == min_h:
			map2[sd_dev] = dict

	Debug("parse_lsscsi():: final_map = " + str(map2))
	Debug("def parse_lsscsi() exit")

	return(map2)


def parse_lsscsi_disks():

	"""
	Parse the output of parse_lsscsi() and only return info on disks
	"""

	Debug("def parse_lsscsi_disks() entry")

	map  = parse_lsscsi()
	map2 = parse_lsscsi()

	for key in map.keys():
		if map[key]["type"] != "disk":
			del map2[key]

	Debug("parse_lsblk_disks():: final_map = " + str(map2))
	Debug("def parse_lsscsi_disks() exit")

	return(map2)


def parse_lsscsi_enclosures():

	"""
	Parse the output of parse_lsscsi() and only return info on enclosures
	"""

	Debug("def parse_lsscsi_enclosures() entry")

	map  = parse_lsscsi()
	map2 = parse_lsscsi()

	for key in map.keys():

		if map[key]["type"] != "enclosu":
			del map2[key]

	Debug("parse_lsblk_enclosures():: final_map = " + str(map2))
	Debug("def parse_lsscsi_enclosures() exit")

	return(map2)


def map_sata_wwn_to_hba_wwn():

	"""
	With SATA drives the HBA or backplane sometimes lies about the WWN of the actual drive.
	Get a list of all drives (so we can map sd_devices to their sg_devices), and then
	query sg_vpd --page=di <sg_dev> to find the mapping between fake WWN and real WWN.
	"""

	Debug("def map_sata_wwn_to_hb_wwn() entry")

	map_sata_wwn_to_hba_wwn = {}

	for sd_dev in map_sd_to_sg:

		sg_dev = map_sd_to_sg[sd_dev]["sg_dev"]

		wwn_list = []

		cmd = "sg_vpd --page=di " + str(sg_dev)
		for line in SysExec("sg_vpd --page=di " + str(sg_dev)).splitlines():

			if not re.search("0x5", line):
				continue

			wwn_list.append(line.strip())

		if len(wwn_list) != 2:
			continue

		map_sata_wwn_to_hba_wwn[wwn_list[1]] = wwn_list[0]

	Debug("map_sata_wwn_to_hba_wwn():: final_map = " + str(map_sata_wwn_to_hba_wwn))
	Debug("def map_sata_wwn_to_hb_wwn() exit")

	return(map_sata_wwn_to_hba_wwn)


def GetLocateLEDState(This_Backplane, This_Slot):

        """
        This function returns the state of the Locate LED on the given backplane/slot
        """

        This_LedState = SysExec("sg_ses -I " + str(This_Slot) + " --get=ident " + This_Backplane).strip()

        LedState_Descr = "Unknown"
        if This_LedState == "1":
                LedState_Descr = "On"
        if This_LedState == "0":
                LedState_Descr = "Off"

        return(LedState_Descr)


def is_multipath_enabled():

	"""
	Probe server and see if multipath is enabled.  True if yes, False if no.
	"""

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

	"""
	Map the dm block device exposed by block mapper to the corresponding /dev/mapper entry
	"""

	Debug("def map_dm_to_mpath() entry")

	map = {}

	for line in SysExec("ls -alh /dev/mapper").splitlines():

		if not re.search("mpath", line):
			continue

		line = " ".join(line.split())

		dm_dev = line.split()[-1].split("/")[1]

		mpath_dev = line.split()[-3]
		mpath_dev = re.sub("-part1", "", mpath_dev)
		mpath_dev = re.sub("-part2", "", mpath_dev)

		map[dm_dev] = mpath_dev

	Debug("map_dm_to_mpath():: final_map = " + str(map))
	Debug("def map_dm_to_mpath() exit")

	return(map)


def map_dm_to_sd_dev():

	"""
	Map the dm block device exposed by device mapper to the underlying /dev/sd* entries
	"""

	Debug("def map_dm_to_sd_dev() entry")

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

	Debug("map_dm_to_sd_dev():  final_map = " + str(map))
	Debug("def map_dm_to_sd_dev() exit")

	return(map)


def map_mpath_to_sd_dev():

	"""
	Combine the two previous function to map /dev/sda -> /dev/mapper/mpatha

	"""

	Debug("def map_mpath_to_sd_dev() entry")

	map = {}

	map_1 = map_dm_to_sd_dev()
	map_2 = map_dm_to_mpath()

	dict_1 = dict(map_1)
	dict_2 = dict(map_2)

	for dm in sorted(dict_1):

		sd_dev = map_1[dm]
		mpath  = map_2[dm]

		map[mpath] = sd_dev

	Debug("map_mpath_to_sd_dev:: final_map = " + str(map))
	Debug("def map_mpath_to_sd_dev() exit")

	return(map)


def map_Dev_to_RID():

        """
        Return a map of /dev/ entry -> RID
        """

        Debug("def map_Dev_to_RID() entry")

        Map = {}

        output_ridlist = SysExec("ls -alh /dev/disk/by-label")

        map_dm_mpath = map_dm_to_mpath()

        for line in output_ridlist.splitlines():

                if not re.search("rid-data-", line):
                        continue

                This_Dev = line.split(" ")[-1]
                This_Dev = This_Dev.split("/")[2]

                if re.search("^sd", This_Dev):
                        This_Dev = re.sub("[0-9]*$", "", This_Dev)
                This_Dev = "/dev/" + This_Dev

                This_Rid = line.split(" ")[-3]
                This_Rid = This_Rid.split("-")[2]

                Debug("map_Dev_to_Rid()::  Dev " + This_Dev + " = Rid " + This_Rid)

                if multipath_active:
                        This_Dev = This_Dev.split("/")[2]
                        This_Dev = map_dm_mpath[This_Dev]
                        This_Dev = "/dev/mapper/" + This_Dev

                Map[This_Dev] = This_Rid

        Debug("map_Dev_to_RID:: final_map = " + str(Map))
        Debug("def map_Dev_to_RID() exit")

        return(Map)


def map_enclosures():

	"""
	Loop over the enclosures and pull together some info on them.
	"""

	Debug("def map_enclosures() entry")

	map_lsscsi = parse_lsscsi_enclosures()

	map = {}

	for sd_dev, dict in map_lsscsi.items():

		hctl   = dict["hctl"]
		wwn    = dict["sas_wwn"]
		sg_dev = dict["sg_dev"]

#		Debug("map_enclosures:: sg_dev = " + str(sg_dev) + " wwn = " + str(wwn) + " hctl = " + str(hctl) + " sd_dev = " + str(sd_dev))

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


		map_lsscsi[sd_dev]["num_slots"] = num_slots

		if num_slots == 12:
			map_lsscsi[sd_dev]["alias"] = "Back"

		if num_slots == 24:
			map_lsscsi[sd_dev]["alias"] = "Front"

		for line in SysExec("sg_ses -p cf " + sg_dev).splitlines():

			if re.search("enclosure vendor:", line):
				enc_vendor = re.sub("vendor:", ":", line)
				enc_vendor = enc_vendor.split(":")[1].strip()
				map_lsscsi[sd_dev]["enc_vendor"] = enc_vendor

			if re.search("product:", line):
				enc_product = re.sub(" rev:", ":", line)
				enc_product = enc_product.split(":")[2].strip()
				map_lsscsi[sd_dev]["enc_product"] = enc_product

	Debug("def map_enclosures() exit")

	return(map_lsscsi)


def map_sg_ses_enclosure_slot_to_sas_wwn():

	Debug("def map_sg_ses_enclosure_slot_to_sas_wwn() entry")

	map = {}

	map_enc = map_enclosures()
	map_wwn = map_sata_wwn_to_hba_wwn()

	for enc in map_enc.keys():

		sg_dev = map_enc[enc]["sg_dev"]

		map[sg_dev] = {}

		slot = ""
		sas_wwn = ""


		for line in SysExec("sg_ses -p aes " + str(sg_dev)).splitlines():

			if re.search("Element type: SAS expander", line):
				break

			if not re.search("(Element index:|SAS address|target port for:)", line):
				continue

			if re.search("attached SAS address", line):
				continue

			if re.search("target port for:", line):

				line = line.split(":")[1].strip()

				if line == "SSP":
					protocol = "SAS"
				elif line == "SATA_device":
					protocol = "SATA"
				else:
					protocol = "UNKNOWN_PROTO"

			if re.search("Element index:", line):
				slot = ' '.join(line.split())
				slot = slot.split(":")[1]
				slot = ' '.join(slot.split())
				slot = slot.split()[0]

			if re.search("SAS address", line):

				sas_wwn = line.split(":")[1].strip()

				if protocol == "SATA":
					sas_wwn = map_wwn[sas_wwn]

				if sas_wwn == "0x0":
					sas_wwn = "EMPTY"

			if slot and not slot in map[sg_dev]:
				map[sg_dev][slot] = {}

			if sas_wwn:
				map[sg_dev][slot]["wwn"] = sas_wwn

			if slot and sas_wwn:

				slot = ""
				sas_wwn = ""

#	Debug("map_sg_ses_enclosure_slot_to_sas_wwn:: map = " + str(map))
	Debug("def map_sg_ses_enclosure_slot_to_sas_wwn() exit")

	return(map)


def Return_SD_Dev(wwn_1, map):

	"""
	Match the given wwn and return the sd_dev that belongs to it
	"""

#	Debug("Return_SD_Dev::  wwn_1 = " + str(wwn_1))
#	Debug("Return_SD_Dev::  map   = " + str(map))

	if wwn_1 == "EMPTY":
		return("EMPTY")

	for sd_dev in map.keys():

		wwn_2 = map[sd_dev]["WWN"]

		# Now, the actual Serial may be Serial, or Serial +/- 3.   I wish I understood the logic here better.
		wwn_m1 = hex(int(wwn_2, 16) - 1)
		wwn_p1 = hex(int(wwn_2, 16) + 1)
		wwn_m2 = hex(int(wwn_2, 16) - 2)
		wwn_p2 = hex(int(wwn_2, 16) + 2)

		Serial_list = [ wwn_m2, wwn_m1, wwn_2, wwn_p1, wwn_p2 ]

		if wwn_1 in Serial_list:
			return(sd_dev)

	return("UNKNOWN")


### Main()

### Determine whether multipathing is enabled or not.
### Enabled requires more data and is a bit more complex
multipath_active = is_multipath_enabled()
Debug("main:: multipath_active = " + str(multipath_active))

### Use lsblk to report info on all detected block devices.
### map_lsblk will be the primary data structure of this script,
### and others will be used to augment it before printing
map_lsblk = parse_lsblk_disks()
Debug("main:: map_lsblk = " + str(map_lsblk))

### Parse "lsscsi" output and add useful fields to map_lsblk
map_sd_to_sg = parse_lsscsi_disks()
for sd_dev, dict in map_sd_to_sg.items():

	if not re.search("/dev/", sd_dev):
		continue

	map_lsblk[sd_dev]["sg_dev"]     = dict["sg_dev"]
	map_lsblk[sd_dev]["hctl"]       = dict["hctl"]
	map_lsblk[sd_dev]["lsscsi_wwn"] = dict["sas_wwn"]

Debug("main:: map_lsblk = " + str(map_lsblk))

### Map of sd_dev -> RID
map_dev_to_rid = map_Dev_to_RID()
#Debug("main:: map_dev_to_rid = " + str(map_dev_to_rid))

### Scan the backplanes and build a dict of useful info
map_bp_slot = map_enclosures()
Debug("main:: map_bp_slot = " + str(map_bp_slot))

### Parse "sg_ses" and get enclosure/slot info for each wwn
map_es_to_sas_wwn = map_sg_ses_enclosure_slot_to_sas_wwn()
Debug("main:: map_es_to_sas_wwn = " + str(map_es_to_sas_wwn))

### Loop over enclosures to find the alias/backplane and add it to map_lsblk
for sg_dev in map_es_to_sas_wwn:

	Debug("main:: Looking for " + sg_dev + " in map_bp_slot()")

	for key, dict in map_bp_slot.items():

		actual_sg_dev = dict["sg_dev"]
		num_slots     = dict["num_slots"]
		alias         = dict["alias"]

		Debug("actual_sg_dev = " + str(actual_sg_dev) + " and num_slots = " + str(num_slots) + " and alias = " + str(alias))

		if sg_dev == actual_sg_dev:

			for slot in map_es_to_sas_wwn[sg_dev]:
				wwn_1 = map_es_to_sas_wwn[sg_dev][slot]["wwn"]

				sd_dev = Return_SD_Dev(wwn_1, map_lsblk)
				Debug("main:: sg_dev " + str(actual_sg_dev) + " slot " + str(slot) + " maps to sd_dev " + str(sd_dev))

				map_lsblk[sd_dev]["backplane"] = actual_sg_dev
				map_lsblk[sd_dev]["slot"]      = slot
				map_lsblk[sd_dev]["bp_alias"]  = alias


###########################################################################

# Add the RID to map_lsblk

for key in map_lsblk.keys():
	map_lsblk[key]["RID"] = map_dev_to_rid[map_lsblk[key]["MP_PATH"]]



###########################################################################

# Add the locate LED status to map_lsblk
for sd_dev in map_lsblk.keys():

	backplane = map_lsblk[sd_dev]["backplane"]
	slot      = map_lsblk[sd_dev]["slot"]
	map_lsblk[sd_dev]["locate_led"] = GetLocateLEDState(backplane, slot)


###########################

### Output and done
output = []

# Iterate over map2 and build output list
for sd_dev, dict in map_lsblk.items():

	locate   = dict["locate_led"]
	rid      = dict["RID"]
	alias_bp = dict["bp_alias"]
	slot     = dict["slot"]

	vendor   = dict["VENDOR"]
	model    = dict["MODEL"]
	serial   = dict["SERIAL"]
	firmware = dict["REV"]

	trans   = dict["TRAN"]
	rota    = dict["ROTA"]
	type	= dict["TYPE"]
	sg_dev  = dict["sg_dev"]

	if rota == "1":
		rota_txt = "hd"
	elif rota == "0":
		rota_txt = "ssd"
	else:
		rota_txt = "unknown"

	type_rota = type + ":" + rota_txt

	wwn     = dict["WWN"]   # Or maybe lssscsi_wwn

	bd = sd_dev
	if multipath_active:
		bd     = dict["MP_PATH"]

	# This output is for "lsslot"
	#output.append([alias_bp, slot, locate, bd, rid])

	output.append([alias_bp, slot, bd, rid, sg_dev, locate, vendor, model, serial, firmware, trans, type_rota])

# This output is for "lsslot"
#x = PrettyTable(["Backplane", "Slot", "Locate LED", "Dev", "RID"])

x = PrettyTable(["Backplane", "Slot", "Dev", "Rid", "SG_Dev", "Locate", "Vendor", "Model", "Serial", "Firmware", "Trans", "Media"])
x.padding_width = 1
x.align = "l"
for row in output:
        x.add_row(row)
print(x)
