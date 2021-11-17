#!/usr/bin/env python3

"""
Parse the output of the "sg_ses" and "udevadm" utilities and print some useful stuff.
Will eventually be a replacement for both "lsblock" and "lsslot"
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

def Get_SASController():

	"""
	Return the SAS controller model in this depot.
	"""

	Debug("def Get_SASController() entry")

	output_lspci = SysExec("lspci")

	# Enumerate all HBA's on-board
	SAS_Controller = [ ]
	for line in output_lspci.splitlines():
		if re.search("RAID bus controller", line) or re.search("Serial Attached SCSI controller", line):
			SAS_Controller.append(line)

	if not SAS_Controller:
		SAS_Controller = [ "Unknown" ]

	Debug("Get_SASController()::  SAS Controller type = " + str(SAS_Controller))

	if "Unknown" in SAS_Controller:
		Debug("Get_SASController()::  There is an unknown controller type in this system.")

	Debug("def Get_SASController() exit")

	return SAS_Controller


def map_sd_to_sg():
	"""
	Return a map of SD device (/dev/sda) to SG Device (/dev/sg24)
	"""

	map = {}

	for line in SysExec("lsscsi -g").splitlines():

		line = re.sub('\s+',' ',line).strip()

		sd_dev = line.split(" ")[-2]
		sg_dev = line.split(" ")[-1]

		map[sd_dev] = sg_dev

	Debug("map_sd_to_sg:: map = " + str(map))

	return(map)


def map_intermediate_SAS_to_WWN_with_sas2ircu():

	"""
	This will return a mapping the intermediate SAS to WWN addreses using sas2ircu which is
	necessary for the LSI_Falcon HBA controllers.
	"""

	Debug("def map_intermediate_SAS_to_WWN_with_sas2ircu() entry")

	Map = {}

	SAS2IRCU_BIN = Bin_Suggests("sas2ircu")

	if SAS2IRCU_BIN is None:
		print("INFO: The LSI 'sas2ircu' utility was not found.  Mapping drives to enclosure/slot will be disabled on Chenbro chassis.")
		return Map

	val_device = None
	val_sas    = None
	val_wwn    = None

	output_sas2ircu = SysExec(SAS2IRCU_BIN + " 0 display")

	for line in output_sas2ircu.splitlines():

		if not re.search("Device is a", line) and \
		   not re.search("SAS Address", line) and \
		   not re.search("GUID", line):
			continue

		if re.search("Device is a", line):
			val_device = re.sub("Device is a ", "", line)
		elif re.search("SAS Address", line):
			val_sas = line.split(":")[1]
			val_sas = re.sub(" ", "", val_sas)
			val_sas = re.sub("-", "", val_sas).lower()
		elif re.search("GUID", line):
			val_wwn = line.split(":")[1]
			val_wwn = re.sub(" ", "", val_wwn)

#		Debug("map_intermediate_SAS_to_WWN_with_sas2ircu()::  val_device = " + str(val_device) + " val_sas = " + str(val_sas) + " val_wwn = " + str(val_wwn))

		if val_device and val_sas and val_wwn:
			if val_device == "Hard disk":
				Map[val_wwn] = val_sas

			val_device    = None
			val_sas       = None
			val_wwn      = None

	Debug("def map_intermediate_SAS_to_WWN_with_sas2ircu(): Map = " + str(Map))
	Debug("def map_intermediate_SAS_to_WWN_with_sas2ircu() exit")

	return Map

def map_intermediate_SAS_to_WWN_with_MegaCli():

        """
        Return a map of SAS to WWN using the LSI MegaCLI utility.  This is necessary for cards
        using our 2nd generation HBA controller ("LSI_Thunderbolt")
        """

        Debug("def map_intermediate_SAS_to_WWN_with_MegaCli() entry")

        Map = {}

        MEGACLI_BIN = Bin_Suggests("MegaCli64")
        if MEGACLI_BIN is None:
                print("INFO: The LSI 'MegaCli64' utility was not found.  Mapping drives to enclosure/slot might not work.")
                return Map

        val_wwn = None
        val_sas = None

        output_megacli = SysExec("MegaCli64 -PDList -aALL -NoLog")

        for line in output_megacli.splitlines():

                if not re.search("WWN", line) and not re.search("SAS Address", line):
                        continue

                if re.search("WWN", line):
                        val_wwn = line.split(":")[-1].strip().lower()

                elif re.search("SAS Address", line):
                        SAS = line.split(":")[-1]
                        val_sas = SAS.split("x")[-1].strip().lower()
                        # Sometimes there are multiple SAS values.  Ignore ones that are 0
                        if val_sas == "0":
                                val_sas = None
                                continue

                if val_wwn and val_sas:

                        # Extra hacky, but necessary.  This is a guess, but the LSI controller appears to use the
                        # drives's WWN if it has one, and autogenerates one if it  doesn't.  The former case appears
                        # to include some of our SAS drives (not SATA drives).  I'm not sure if this is the textbook
                        # solution, but it works in our case.
                        if val_sas.startswith("5000c"):
                                val_wwn = hex(int(val_sas, 16) + 2).split("x")[1].lower()

                        Debug("map_intermediate_SAS_to_WWN_with_MegaCli()::  SAS " + str(val_sas) + " maps to WWN " + str(val_wwn))
                        Map[val_wwn] = val_sas

                        val_wwn = None
                        val_sas = None

        Debug("def map_intermediate_SAS_to_WWN_with_Megacli():: Map = " + str(Map))

        Debug("def map_intermediate_SAS_to_WWN_with_MegaCli() exit")

        return Map


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


def findRawSize(SD_Device):
	"""
	Fetch raw device size (in bytes) by multiplying "/sys/block/DEV/queue/hw_sector_size"
	by /sys/block/DEV/size
	"""

	secsize = "0"
	numsec  = "0"

	tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/size"
	if os.path.isfile(tfile):
		numsec = SysExec("cat " + tfile).strip()

	tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/queue/hw_sector_size"
	if os.path.isfile(tfile):
		secsize = SysExec("cat " + tfile).strip()

	return int(numsec) * int(secsize)


def HumanFriendlyBytes(bytes, scale, decimals):

	"""
	Convert a integer number of bytes into something legible (10 GB or 25 TiB)
	Base 1000 units = KB, MB, GB, TB, etc.
	Base 1024 units = KiB, MiB, GiB, TiB, etc.
	"""

	AcceptableScales = [ 1000, 1024 ]

	if not scale in AcceptableScales:
		return "ERR_BAD_SCALE"

	# For removable media like dvd's
	if bytes == 0:
		return "Empty"

	unit_i = int(math.floor(math.log(bytes, scale)))

	if scale == 1000:
		UNITS = [ "B",  "KB",  "MB",  "GB",  "TB",  "PB",  "EB",  "ZB",  "YB" ]
	if scale == 1024:
		UNITS = [ "B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB" ]

	scaled_units = UNITS[unit_i]
	scaled_size = round(bytes / math.pow(scale, unit_i), decimals)

	return_str = str(scaled_size) + " " + scaled_units
	return_str = re.sub(".0 ", " ", return_str)

	return(return_str)


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

		if re.search("^WD", Model):
			Vendor = "WDC"

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

def standardize_Serial(SCSI_IDENT_SERIAL, ID_SCSI_SERIAL):
	"""
	The HBA/backplane/drive stack seemingly randomly returns either the human-visble
	serial num on the drive label, or the "05" SATA/SAS serial.   I want to standardize
	this to the extent possible.   Look at the serial #.   If it starts with "50" or "0x50",
	call it the "HBA_SERIAL".   Otherwise call it the HR_SERIAL (Human-Readable Serial).
	This is inherently a "best effort" attempt.
	"""
	HR_Serial  = "None"
	HBA_Serial = "None"

	if SCSI_IDENT_SERIAL == ID_SCSI_SERIAL:
		if re.search("^500", SCSI_IDENT_SERIAL) or re.search("0x500", SCSI_IDENT_SERIAL):
			HBA_Serial = SCSI_IDENT_SERIAL
			HR_Serial = "Unknown"
		else:
			HR_Serial = SCSI_IDENT_SERIAL
			HBA_Serial = "Unknown"

	if re.search("^500", SCSI_IDENT_SERIAL) or re.search("0x500", SCSI_IDENT_SERIAL):
		HBA_Serial = SCSI_IDENT_SERIAL
	else:
		HR_Serial  = SCSI_IDENT_SERIAL

	if re.search("^500", ID_SCSI_SERIAL) or re.search("0x500", ID_SCSI_SERIAL):
		HBA_Serial = ID_SCSI_SERIAL
	else:
		HR_Serial  = ID_SCSI_SERIAL

	if HR_Serial == "None" or HR_Serial == "Unknown":
		HR_Serial = HBA_Serial

	return (HR_Serial, HBA_Serial)


#####################################################################################
### Start of program
#####################################################################################

LSPCI_BIN = Bin_Requires("lspci")
LSSCSI_BIN = Bin_Requires("lsscsi")
SG_SES_BIN = Bin_Recommends("sg_ses")
UDEVADM_BIN = Bin_Requires("udevadm")

#sas2ircu (Falcon), MegaCLI (Thunderbolt), and smartctl (NVME drives) are also dependencies
# need to figure out this case.

Controller = Get_SASController()
# For Falcon controllers, we need an assist from sas2ircu to map SATA drives to backplane/slot
for i in Controller:
	if re.search("Falcon", i):
		fal_map = map_intermediate_SAS_to_WWN_with_sas2ircu()
		Falcon = True

	if re.search("Thunderbolt", i):
		thu_map = map_intermediate_SAS_to_WWN_with_MegaCli()
		Thunderbolt = True


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

# Iterate over all enclosures...

# Blank dictionary to hold parsed output from the "sg_ses" command
sg_ses_dict = {}

if enclosures:
	for e in enclosures:

		# Blank dictionary for this enclosure
		sg_ses_dict[e] = {}

		slots = List_Slots(e)

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
						val_txt = "Off"
						if int(val) == 1:
							val_txt = "On"

					sg_ses_dict[e][s][key] = val_txt


# Blank dictionary to hold parsed output from the "sg_ses" command
udevadm_dict = {}

blockdevs = List_BlockDevices()

if not blockdevs:
	print("ERROR: No block devices detected!")
	sys.exit(1)

keys_whitelist = [
	"DEVNAME",\
	"ID_VENDOR",\
	"SCSI_VENDOR",\
	"ID_MODEL",\
	"SCSI_IDENT_SERIAL",\
	"ID_SCSI_SERIAL",\
	"SCSI_REVISION",\
	"ID_BUS",\
	"ID_WWN",\
	"MEDIA_TYPE",\
	"SCSI_IDENT_PORT_NAA_REG",\
	"ID_PATH"]

for bd in blockdevs:

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

		#Debug("bd " + bd + " key " + key + " val = " + val)

		udevadm_dict[bd][key] = val

sorted_keys = sorted(udevadm_dict.keys())
udevadm_dict = {key:udevadm_dict[key] for key in sorted_keys}

### Now we want to iterate over and simplify/clarify a few things
for bd in udevadm_dict:

	if "ID_VENDOR" in udevadm_dict[bd] and not "SCSI_VENDOR" in udevadm_dict[bd]:
		udevadm_dict[bd]["SCSI_VENDOR"] = udevadm_dict[bd]["ID_VENDOR"]

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
	(udevadm_dict[bd]["SCSI_IDENT_SERIAL"], udevadm_dict[bd]["ID_SCSI_SERIAL"]) = standardize_Serial(udevadm_dict[bd]["SCSI_IDENT_SERIAL"], udevadm_dict[bd]["ID_SCSI_SERIAL"])

	# Trim Seagate serial #'s to the first 6 characters
	if udevadm_dict[bd]["SCSI_VENDOR"] == "Seagate":
		udevadm_dict[bd]["SCSI_IDENT_SERIAL"] = udevadm_dict[bd]["SCSI_IDENT_SERIAL"][0:6]

	# Trim the leading "WD-" on WDC Serial #'s
	if udevadm_dict[bd]["SCSI_VENDOR"] == "WDC":
		udevadm_dict[bd]["SCSI_IDENT_SERIAL"] = re.sub("^WD-", "", udevadm_dict[bd]["SCSI_IDENT_SERIAL"])

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

sd_to_sg_map = map_sd_to_sg()

### Now we have sg_ses_dict and udevadm_dict.  Join them together and print
for bd in udevadm_dict:

	# This is result on drives attached via SATA, NVME, and other non-enclosure topologies
	search = "unknown"

	# You can match this directly with sg_ses_dict
	if "SCSI_IDENT_PORT_NAA_REG" in udevadm_dict[bd]:
		if re.search("^50", udevadm_dict[bd]["SCSI_IDENT_PORT_NAA_REG"]):
			search = udevadm_dict[bd]["SCSI_IDENT_PORT_NAA_REG"]

	if search == "unknown" and "SCSI_IDENT_SERIAL" in udevadm_dict[bd]:
		if re.search("^50", udevadm_dict[bd]["SCSI_IDENT_SERIAL"]):
			# We want to subtract 2 from whatever value is here
			search = udevadm_dict[bd]["SCSI_IDENT_SERIAL"]
			search = hex(int(search, 16) - 2)
			search = re.sub("^0x", "", search)

	if "Falcon" in vars():
	#	if udevadm_dict[bd]["ID_BUS"] == "ata":
		if "ID_WWN" in udevadm_dict[bd]:
			st = re.sub("0x", "", udevadm_dict[bd]["ID_WWN"])
			if st in fal_map:
				search = fal_map[st]

	if "Thunderbolt" in vars():
		if udevadm_dict[bd]["ID_BUS"] == "ata":
			if "ID_WWN" in udevadm_dict[bd]:
				st = re.sub("0x", "", udevadm_dict[bd]["ID_WWN"])
				if st in thu_map:
					search = thu_map[st]

	# If there are no enclosures, there are no backplanes...
	if search != "unknown" and enclosures:
		for e in sg_ses_dict:
			for s in sg_ses_dict[e]:
				if sg_ses_dict[e][s]["media_wwn"] == "0x" + search:
#					Debug("bd" + bd + " corresponds to enclosure " + e + " slot " + s)
					udevadm_dict[bd].update(sg_ses_dict[e][s])
					break
	else:
		null_dict = { "enclosure":  "None",    \
                              "slot":       "NA",      \
                              "media_type": "unknown", \
			      "media_wwn":  "unknown", \
                              "descriptor": "none",    \
                              "s_ident":    "None"}
		udevadm_dict[bd].update(null_dict)

	udevadm_dict[bd]["DISK_SIZE"] = HumanFriendlyBytes(findRawSize(bd), 1000, 0)
	if bd in sd_to_sg_map:
		udevadm_dict[bd]["SG_DEV"]    = sd_to_sg_map[bd]
	else:
		udevadm_dict[bd]["SG_DEV"]    = "None"

	if re.search("/dev/nvme", bd):
		udevadm_dict[bd]["SG_DEV"]    = "None"
		udevadm_dict[bd]["enclosure"] = "None"
		udevadm_dict[bd]["slot"]      = "NA"
		udevadm_dict[bd]["s_ident"]   = "None"

print_list = [ "DEVNAME", "SG_DEV", "enclosure", "slot", "SCSI_VENDOR", "ID_MODEL", "SCSI_IDENT_SERIAL", "SCSI_REVISION", "ID_BUS", "MEDIA_TYPE", "DISK_SIZE", "s_ident" ]

pretty_name = {
	"DEVNAME":           "SD_Dev",   \
	"SG_DEV":            "SG_Dev",   \
	"enclosure":         "Enclosure",\
	"slot":              "Slot",     \
	"SCSI_VENDOR":       "Vendor",   \
	"ID_MODEL":          "Model",    \
	"SCSI_IDENT_SERIAL": "Serial",   \
	"SCSI_REVISION":     "Firmware", \
	"ID_BUS":            "Bus",      \
	"MEDIA_TYPE":        "Media",    \
	"DISK_SIZE":         "Size",     \
	"s_ident":           "Locate_LED"
}

# Pretty versions of the above
pretty_list =  [ "SD_Dev", "SG_Dev", "Enclosure", "Slot", "Vendor", "Model", "Serial", "Firmware", "Bus", "Media", "Size", "Locate_LED" ]

for bd in udevadm_dict:
	for o_key, n_key in pretty_name.items():
		udevadm_dict[bd][n_key] = udevadm_dict[bd].pop(o_key)

x = PrettyTable(pretty_list)
x.padding_width = 1
x.align = "l"
for bd in udevadm_dict:
	tmp2 = []
	for key in pretty_list:
		if key in udevadm_dict[bd]:
			tmp2.append(udevadm_dict[bd][key])
		else:
			tmp2.append("")
	x.add_row(tmp2)
print(x)
