#!/usr/bin/env python3

"""
Parse the output of the "sg_ses" and "udevadm" utilities and print some useful stuff.
Will eventually be a replacement for "lsblock"
Dependencies:  lsscsi, python "prettytable" package, smartctl (for nvme drives)

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

	# Remove unwanted block devices
	Filtered_Block_Devs = []
	for i in Block_Devs:

		# Remove loopback devices
		if re.search("/dev/loop", i):
			continue

		# Remove compressed ramdisks
		if re.search("/dev/zram", i):
			continue

		# Remove RAID devices
		if re.search("/dev/md", i):
			continue

		# Remove device mapper devices
		if re.search("/dev/dm-", i):
			continue

		Filtered_Block_Devs.append(i)

	Debug("Block_Devs = " + str(Filtered_Block_Devs))

	return(Filtered_Block_Devs)


def List_Enclosures():
	"""
        List the available enclosures on this server
	"""

	enclosures_list_cmd = SysExec("lsscsi -g")
	enclosures = []
	for line in enclosures_list_cmd.splitlines():

		line = line.strip()

		if not re.search("enclosu", line):
			continue
		if re.search("VirtualSES", line):
			continue

		enclosures.append(line.split(" ")[-1])

	Debug("List_Enclosures:: enclosures = " + str(enclosures))

	return(enclosures)


def List_Slots(e):
	"""
	List the available slots on this enclosure
	"""
	### Get the number of slots for this enclosure
	slots_list_cmd = SysExec("sg_ses --page=aes " + e)
	slots = []
	for l in slots_list_cmd.splitlines():

		if re.search("Element type: SAS expander", l):
			break

		if not re.search("Element index: ", l):
			continue
		slots.append(l.split(":")[1].strip().split(" ")[0])

	Debug("List_Slots:: slots for enclosure " + e + " = " + str(slots))

	return(slots)


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
	if Vendor == "ATA" or Vendor == "ATAPI" or Vendor == "UNKNOWN" or Vendor == "unknown" or not Vendor.strip():

		if re.search("Hitachi", Model, re.I):
			Vendor = "Hitachi"

		if re.search("Fujitsu", Model, re.I):
			Vendor = "Fujitsu"

		if re.search("Maxtor", Model, re.I):
			Vendor = "Maxtor"

		if re.search("MATSHITA", Model, re.I):
			Vendor = "Matshita"

		if re.search("Samsung", Model, re.I):
			Vendor = "Samsung"

		if re.search("LITE-ON", Model, re.I) or re.search("iHAS", Model):
			Vendor = "Lite-On"

		if Model.startswith("INTEL"):
			Vendor = "Intel"

		if Model.startswith("Optiarc"):
			Vendor = "Optiarc"

		if re.search("PNY", Model):
			Vendor = "PNY"

		if re.search("^OCZ", Model):
			Vendor = "OCZ"

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


def HumanFriendlyModel(Vendor, Model):

	"""
	Return the Model string for the media
	Note that this isn't as straightforward as you'd hope because
	many vendors are quite loose with the standards  This is meant to be
	human-friendly, and you should always use the raw query instead when
	trying to match something.

	"""

	# udev likes to use underscores instead of spaces, so change that here.
	Vendor = re.sub("_", " ", Vendor)
	Model  = re.sub("_", " ", Model)

	# Ok, sometimes they like to put the vendor in the model field
	# so try to fix some of the more egregious ones
	if re.search("Hitachi", Model, re.I):
		Model = re.sub("Hitachi","", Model).strip()
		Model = re.sub("HITACHI","", Model).strip()

	if re.search("Fujitsu", Model, re.I):
		Model = re.sub("Fujitsu","", Model).strip()
		Model = re.sub("FUJITSU","", Model).strip()

	if re.search("Maxtor", Model, re.I):
		Model = re.sub("Maxtor","", Model).strip()
		Model = re.sub("MAXTOR","", Model).strip()

	if re.search("Matshita", Model, re.I):
		Model = re.sub("Matshita","", Model).strip()
		Model = re.sub("MATSHITA","", Model).strip()

	if re.search("LITE-ON", Model, re.I):
		Model = re.sub("Lite-On","", Model).strip()
		Model = re.sub("LITE-ON","", Model).strip()

	if re.search("KINGSTON", Model):
		Model = re.sub("KINGSTON ", "", Model)

	if Model.startswith("WDC"):
		Model = re.sub("^WDC", "", Model).strip()

	if Model.startswith("INTEL"):
		Model = re.sub("^INTEL", "", Model).strip()

	if Model.startswith("OCZ-"):
		Model = re.sub("^OCZ-", "", Model).strip()

	if Model.startswith("Optiarc"):
		Model = re.sub("^Optiarc", "", Model).strip()

	if Vendor.startswith("ST"):
		Model = Vendor + Model

	if re.search("Samsung", Model, re.I):
		Model = re.sub("Samsung", "", Model).strip()

	if Model.startswith("TOSHIBA"):
		Model = re.sub("^TOSHIBA ", "", Model).strip()

	if Vendor.startswith("MAXTOR"):
		Model = re.sub("^MAXTOR ", "", Vendor + Model).strip()

	if Model.startswith("ATAPI"):
		Model = re.sub("^ATAPI", "", Model)

	return Model.strip()


def HumanFriendlySerial(Serial, Vendor, Model):
	"""
	Try to de-crapify the Serial Number (again, polluted with other fields)
	"""

	NO_SERIAL = "NO_SERIAL"

	if Serial == Model:
		return NO_SERIAL

	Serial = Serial.split("_")[-1]

	Serial = re.sub("^SATA","", Serial)      # one drive starts with "SATA_"
	Serial = re.sub(Model,"", Serial)        # Filter out the model
	Serial = re.sub(Model[:-1],"", Serial)   # Filter out the model (catches an edge case with WDC <bangs head>)
	Serial = re.sub(Vendor, "", Serial)      # Filter out the Vendor
	Serial = re.sub("^(_)*","", Serial)      # Filter out leading "_"
	Serial = re.sub("(_)*$","", Serial)      # Filter out trailing "_"
	Serial = re.sub("^-", "", Serial)        # Another edge case... (WDC...)
	Serial = re.sub("^WD-", "", Serial)      # Yet another WDC edge case...
	Serial = Serial.strip()                  # and strip

	if not Serial:
		Serial = "NO_SERIAL"

	return Serial


# Blank dictionary to hold parsed output from the "sg_ses" command
sg_ses_dict = {}

# Get a list of all enclosures
enclosures = List_Enclosures()

# Some "enclosures" aren't really, so remove them from the list
tmp_enclosures = []
for e in enclosures:
	slots = List_Slots(e)
	if not slots:
		continue
	tmp_enclosures.append(e)
enclosures = tmp_enclosures

if not enclosures:
	print("ERROR: No enclosures detected, or enclosure does not have attached drives.")
	sys.exit(1)

# Iterate over all enclosures...
for e in enclosures:

	# Blank dictionary for this enclosure
	sg_ses_dict[e] = {}

	slots = List_Slots(e)
	Debug("Slots for Enclosure " + e + " = " + str(slots))

	for s in slots:

		sg_ses_dict[e][s] = {}
		sg_ses_dict[e][s]["enclosure"] = e
		sg_ses_dict[e][s]["slot"]      = s

		# Parse the "aes" page
		sg_ses_output = SysExec("sg_ses -p aes --index=" + s + " " + e)
		sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()
		for line in sg_ses_output.splitlines():
			line = ' '.join(line.split()).strip()

			if re.search("target port for:", line):
				dev_type = line.split(":")[1].strip()
				if dev_type == "SSP":
					sg_ses_dict[e][s]["media_type"] = "SAS"
				elif dev_type == "SATA_device":
					sg_ses_dict[e][s]["media_type"] = "SATA"
				elif dev_type == "":
					sg_ses_dict[e][s]["media_type"] = "Empty"
				else:
					sg_ses_dict[e][s]["media_type"] = "Unknown"
			if re.search("SAS address:", line) and not re.search("attached SAS address", line):
					sg_ses_dict[e][s]["media_wwn"] = line.split(":")[1].strip()

		# Parse the "ed" page
		sg_ses_output = SysExec("sg_ses -p ed --index=" + s + " " + e)
		sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()
		for line in sg_ses_output.splitlines():
			line = ' '.join(line.split()).strip()
			if re.search("Element " + str(s) + " descriptor:", line):
				sg_ses_dict[e][s]["descriptor"] = line.split(":")[1].strip()

		# Parse the "ec" page
		sg_ses_output = SysExec("sg_ses -p ec --index=" + s + " " + e)
		sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()

		# Right now only print the "ident" column, haven't found much use for the others
		whitelist = [ "s_ident" ]
		for line in sg_ses_output.splitlines():
			line = ' '.join(line.split()).strip()

			# Rather than writing a thousand rules, just parse anything that looks like "foo=bar" as a key/value pair
			if re.search("=", line):

				tmp_line = line.lower()
				tmp_line = re.sub("/", "_", tmp_line)
				tmp_line = re.sub(" ", "_", tmp_line)

				key = "s_" + tmp_line.split("=")[0].strip()
				val =        tmp_line.split("=")[1].strip()

				if not key in whitelist:
					continue

				if key == "s_ident":
					if val == 1:
						val = "On"
					else:
						val = "Off"

				sg_ses_dict[e][s][key] = val

# Get the list of column names for PrettyTable
col = sg_ses_dict[enclosures[0]][slots[0]].keys()
Debug("col = " + str(col))

x = PrettyTable(col)
x.padding_width = 1
for e in sg_ses_dict:
	for s in sg_ses_dict[e]:
		vals = sg_ses_dict[e][s].values()
		Debug("vals = " + str(vals))
		x.add_row(sg_ses_dict[e][s].values())
print(x)


####################################################################################################################################


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
	"ID_SCSI_SERIAL",\
	"SCSI_REVISION",\
	"ID_BUS",\
	"MEDIA_TYPE",\
	"SCSI_IDENT_PORT_NAA_REG",\
	"ID_PATH"]


for bd in blockdevs:

	Debug("Looping over bd " + bd)

	# Blank dictionary for this enclosure
	udevadm_dict[bd] = {}

	# udevadm lies about whether whether the drive spins or not, so check under /sys/block
	rotation = int(SysExec("cat /sys/block/" + bd.split("/")[2] + "/queue/rotational"))

	if rotation == 0:
		udevadm_dict[bd]["MEDIA_TYPE"] = "ssd"
	else:
		udevadm_dict[bd]["MEDIA_TYPE"] = "hd"

	# Parse "udevadm" output
	udevadm_output = SysExec("udevadm info --query=property --name=" + bd)
	for line in udevadm_output.splitlines():
		line = ' '.join(line.split()).strip()

		key = line.split("=")[0]
		val = line.split("=")[1]

		Debug("bd " + bd + " key " + key + " val = " + val)

		udevadm_dict[bd][key] = val

sorted_keys = sorted(udevadm_dict.keys())
udevadm_dict = {key:udevadm_dict[key] for key in sorted_keys}

### Now we want to iterate over and simplify/clarify a few things
for bd in udevadm_dict:

	if "ID_TYPE" in udevadm_dict[bd]:
		if udevadm_dict[bd]["ID_TYPE"] == "disk":
			udevadm_dict[bd]["MEDIA_TYPE"] = udevadm_dict[bd]["MEDIA_TYPE"]
		elif udevadm_dict[bd]["ID_TYPE"] == "cd":
			udevadm_dict[bd]["ID_TYPE"] == "cd"
		else:
			udevadm_dict[bd]["MEDIA_TYPE"] = udevadm_dict[bd]["ID_TYPE"]

	if not "ID_SCSI_SERIAL" in udevadm_dict[bd]:
		udevadm_dict[bd]["ID_SCSI_SERIAL"] = ""

	if not udevadm_dict[bd]["ID_SCSI_SERIAL"]:
		if "SCSI_IDENT_SERIAL" in udevadm_dict[bd]:
			udevadm_dict[bd]['ID_SCSI_SERIAL'] = udevadm_dict[bd]['SCSI_IDENT_SERIAL']

		if "ID_SERIAL_SHORT" in udevadm_dict[bd]:
			udevadm_dict[bd]['ID_SCSI_SERIAL'] = udevadm_dict[bd]['ID_SERIAL_SHORT']

	# If it doesn't have a SCSI serial #, see if there's a SATA serial # and use that
	if not "SCSI_IDENT_SERIAL" in udevadm_dict[bd]:
		if "ID_SERIAL_SHORT" in udevadm_dict[bd]:
			udevadm_dict[bd]['SCSI_IDENT_SERIAL'] = udevadm_dict[bd]['ID_SERIAL_SHORT']

	# Also, if it doesn't have a SCSI firmware revision #, use the SATA firmware revision #
	if not "SCSI_REVISION" in udevadm_dict[bd]:
		if "ID_REVISION" in udevadm_dict[bd]:
			udevadm_dict[bd]['SCSI_REVISION'] = udevadm_dict[bd]['ID_REVISION']

	if not "ID_BUS" in udevadm_dict[bd]:
		if "ID_PATH" in udevadm_dict[bd]:
			if re.search("nvme", udevadm_dict[bd]['ID_PATH']):
				udevadm_dict[bd]['ID_BUS'] = "nvme"
	else:
		udevadm_dict[bd]['ID_BUS'] = udevadm_dict[bd]['ID_BUS']

	if not "SCSI_VENDOR" in udevadm_dict[bd]:
		udevadm_dict[bd]["SCSI_VENDOR"] = " "

	if "ID_MODEL" in udevadm_dict[bd]:
		udevadm_dict[bd]["SCSI_VENDOR"] = HumanFriendlyVendor(udevadm_dict[bd]["SCSI_VENDOR"], udevadm_dict[bd]["ID_MODEL"])

	if "SCSI_VENDOR" in udevadm_dict[bd] and "ID_MODEL" in udevadm_dict[bd]:
		udevadm_dict[bd]["ID_MODEL"]    = HumanFriendlyModel(udevadm_dict[bd]["SCSI_VENDOR"], udevadm_dict[bd]["ID_MODEL"])

	if "SCSI_IDENT_SERIAL" in udevadm_dict[bd]:
		udevadm_dict[bd]["SCSI_IDENT_SERIAL"] = HumanFriendlySerial(udevadm_dict[bd]["SCSI_IDENT_SERIAL"], udevadm_dict[bd]["SCSI_VENDOR"], udevadm_dict[bd]["ID_MODEL"])
	else:
		udevadm_dict[bd]["SCSI_IDENT_SERIAL"] = "UNKNOWN"

	if "ID_BUS" in udevadm_dict[bd]:
		if udevadm_dict[bd]['ID_BUS'] == "nvme":

			smartctl_output = SysExec("smartctl -i " + bd)
			for l in smartctl_output.splitlines():

				if re.search("Serial Number:", l):
					udevadm_dict[bd]['SCSI_IDENT_SERIAL'] = l.split(":")[1].strip()

				if re.search("Firmware Version:", l):
					udevadm_dict[bd]['SCSI_REVISION'] = l.split(":")[1].strip()

### I need to add a final loop to filter out all entries except the ones in the whitelist
tmp = {}
for bd in udevadm_dict:
	tmp[bd] = {}
	for key in keys_whitelist:
		if key in udevadm_dict[bd]:
			tmp[bd][key] = udevadm_dict[bd][key]
		else:
			tmp[bd][key] = ""
udevadm_dict = tmp

### Now we have sg_ses_dict and udevadm_dict.  Join them together and print


x = PrettyTable(keys_whitelist)
x.padding_width = 1
x.align = "l"
for bd in udevadm_dict:
	tmp2 = []
	for key in keys_whitelist:
		if key in udevadm_dict[bd]:
			tmp2.append(udevadm_dict[bd][key])
		else:
			tmp2.append("")
	x.add_row(tmp2)
print(x)


#sg_ses_dict looks like:
#| enclosure | slot | media_type |     media_wwn      | descriptor | s_ident |
#|  /dev/sg0 |  0   |    SAS     | 0x5000c500a6dae405 |  Disk001   |   Off   |

# udevadm_dict looks like:
#| DEVNAME   | SCSI_VENDOR | ID_MODEL      | SCSI_IDENT_SERIAL  | ID_SCSI_SERIAL       | SCSI_REVISION | ID_BUS | MEDIA_TYPE | SCSI_IDENT_PORT_NAA_REG | ID_PATH                        |
#| /dev/sdaa | Seagate     | ST12000NM0038 | 5000c500aecd9b4f   | ZHZ4QZ430000C011DR2B | E002          | scsi   | hd         |                         | pci-0000:81:00.0-scsi-0:0:47:0 |