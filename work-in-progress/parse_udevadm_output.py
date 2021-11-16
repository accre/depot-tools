#!/usr/bin/env python3

"""
Parse the output of the "udevadm" utility and print the useful stuff

Dependencies:  lsscsi, python "prettytable" package

"""

import re
import os
import sys
import math
import time

from subprocess import Popen, PIPE, STDOUT
from prettytable import PrettyTable

# Enable/disable debugging messages
Print_Debug = False

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


def List_BlockDevices():
	"""
	List block devices (hard drives, ssd's, nvme's, etc) visible to the OS
	"""

	Block_Devs = [ "/dev/" + s for s in os.listdir("/sys/block")]

	Debug("Block_Devs = " + str(Block_Devs))

	return(Block_Devs)


def HumanFriendlyVendor(Vendor, Model):
	"""
	Return the Vendor string for the media (Seagate, Hitachi, etc.)
	Note that this isn't as straightforward as you'd hope because
	many vendors are quite loose with the standards.  This is meant to be
	human-friendly, and you should always use the raw query instead when
	trying to match something.
	"""

	# udev likes to use underscores instead of spaces, so change that here.
	Vendor = re.sub("_", " ", Vendor)
	Model  = re.sub("_", " ", Model)

	# Ok, sometimes they like to put the vendor in the model field
	# so try to fix some of the more egregious ones
	if Vendor == "ATA" or Vendor == "ATAPI" or Vendor == "UNKNOWN":

		if re.search("Hitachi", Model, re.I):
			Vendor = "Hitachi"

		if re.search("Fujitsu", Model, re.I):
			Vendor = "Fujitsu"

		if re.search("Maxtor", Model, re.I):
			Vendor = "Maxtor"

		if re.search("MATSHITA", Model, re.I):
			Vendor = "Matshita"

		if re.search("LITE-ON", Model, re.I):
			Vendor = "Lite-On"

		if Model.startswith("WDC"):
			Vendor = "WDC"

		if Model.startswith("INTEL"):
			Vendor = "Intel"

		if Model.startswith("OCZ"):
			Vendor = "OCZ"

		if Model.startswith("Optiarc"):
			Vendor = "Optiarc"

	if re.search("KINGSTON", Model):
		Vendor = "Kingston"

	# Seagate is all the fark over the place...
	if Vendor.startswith("ST"):
		Vendor = "Seagate"

	if Model.startswith("ST"):
		Vendor = "Seagate"

	if re.search("Toshiba", Model, re.I):
 		Vendor = "Toshiba"

	if re.search("Maxtor", Vendor, re.I):
		Vendor = "Maxtor"

	if re.search("LITE-ON", Vendor):
		Vendor = "Lite-On"

	# If it's still set to ATAPI or ATA, then it's a unknown
	# vendor who's *really* lax on following standards.
	if Vendor == "ATAPI" or Vendor == "ATA":
		Vendor = "unknown"

	return Vendor.strip()


# Blank dictionary to hold parsed output from the "sg_ses" command
udevadm_dict = {}

blockdevs = List_BlockDevices()

if not blockdevs:
	print("ERROR: No block devices detected!")
	sys.exit(1)

keys_whitelist = [
	"DEVNAME",\
	"SCSI_VENDOR",\
	"ID_MODEL",\
	"SCSI_IDENT_SERIAL",\
	"SCSI_REVISION",\
	"ID_BUS",\
	"ID_ATA_ROTATION_RATE_RPM",\
	"ID_SERIAL_SHORT",\
	"ID_WWN",\
	"SCSI_IDENT_PORT_NAA_REG",\
	"SCSI_IDENT_TARGET_NAA_REG",\
	"ID_PATH"]


for bd in blockdevs:

	Debug("Looping over bd " + bd)

	# Blank dictionary for this enclosure
	udevadm_dict[bd] = {}

	# Parse "udevadm" output
	udevadm_output = SysExec("udevadm info --query=property --name=" + bd)
	for line in udevadm_output.splitlines():
		line = ' '.join(line.split()).strip()

		key = line.split("=")[0]
		val = line.split("=")[1]

		if not key in keys_whitelist:
			continue

		Debug("bd " + bd + " key " + key + " val = " + val)

		udevadm_dict[bd][key] = val

sorted_keys = sorted(udevadm_dict.keys())
udevadm_dict = {key:udevadm_dict[key] for key in sorted_keys}

### Now we want to iterate over and simplify/clarify a few things
for bd in udevadm_dict:

	if not "ID_BUS"  in udevadm_dict[bd] and re.search("nvme", udevadm_dict[bd]['ID_PATH']):
		print("DEBUG : " + str(udevadm_dict[bd]))
		udevadm_dict[bd]['ID_BUS'] = "nvme"
	else:
		udevadm_dict[bd]['ID_BUS'] = udevadm_dict[bd]['ID_BUS']

#	udevadm_dict[bd]["SCSI_VENDOR"] = HumanFriendlyVendor(udevadm_dict[bd]["SCSI_VENDOR"], udevadm_dict[bd]["ID_MODEL"])


x = PrettyTable(keys_whitelist)
x.padding_width = 1
for bd in udevadm_dict:
	tmp = []
	for key in keys_whitelist:
		if key in udevadm_dict[bd]:
			tmp.append(udevadm_dict[bd][key])
		else:
			tmp.append("")
	x.add_row(tmp)
print(x)
