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

#       Debug("SysExec()::  cmd = " + cmd)

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


def Get_Enclosure_Info():

        """
        Get info on all enclosures.
        """

        # Our current depots have 24 slots on the Front backplane and 12 on the Rear
        # In a more complex setup, we might need a more cumbersome way to alias backplanes
        Alias_by_NumSlots = {}
        Alias_by_NumSlots["24"] = "Front"
        Alias_by_NumSlots["12"] = "Back"

        # Array to hold the output for pretty printing
        Output = []

        Enclosure_Raw = SysExec("lsscsi -g")
        for line in Enclosure_Raw.splitlines():

                if not re.search("enclosu", line):
                        continue

                if re.search("VirtualSES", line):
                        continue

                SG_Dev = line.split()[-1]

                SG_Bus = line.split()[0]
                SG_Bus = re.sub("\[", "", SG_Bus)
                SG_Bus = re.sub("\]", "", SG_Bus)

                SAS_Addr = "UNKNOWN_SAS"
                SAS_Addr_Raw = SysExec("sg_ses --page=aes " + SG_Dev)
                for text in SAS_Addr_Raw.splitlines():
                        if re.search("Primary enclosure logical identifier", text):
                                SAS_Addr = text.split(":")[1]
                                SAS_Addr = re.sub(" ", "", SAS_Addr)

                Num_Slots = "UNKNOWN_SLOTS"
                Num_Slots_Raw  = SysExec("sg_ses --page=cf " + SG_Dev)
                match = re.search(r'Array device slot(.*)ArrayDevicesInSubEnclsr0', Num_Slots_Raw, re.DOTALL)
                match = match.group(0)
                for l in match.splitlines():
                        if re.search("number of possible elements", l):
                                Num_Slots = l.split(":")[-1]
                                Num_Slots = re.sub(" ", "", Num_Slots)


                Alias = "UNKNOWN_ALIAS"
                if Num_Slots in Alias_by_NumSlots:
                        Alias = Alias_by_NumSlots[Num_Slots]

                Output.append([SG_Dev, Num_Slots, SG_Bus, SAS_Addr, Alias])

        return(Output)


def map_sd_to_sg():
	"""
	Return a map of SD device (/dev/sda) to SG Device (/dev/sg24)
	"""

	map = {}

	for line in SysExec("lsscsi -g").splitlines():

		if re.search("enclosu", line):
			continue

		line = re.sub('\s+',' ',line).strip()

		sd_dev = line.split(" ")[-2]
		sg_dev = line.split(" ")[-1]

		map[sd_dev] = sg_dev

	Debug("map_sd_to_sg:: map = " + str(map))

	return(map)


def map_WWN_to_Dev():

        """
        Return a map of virtual disk WWN -> /dev/whatever
        """

        Debug("def map_VD_wwn_to_Dev() entry")

        Map = {}

        output_saslist = SysExec("ls -alh /dev/disk/by-id")

        for line in output_saslist.splitlines():

                if not re.search("wwn-", line):
                        continue

                if re.search("part", line):
                        continue

                This_Dev = line.split(" ")[-1]
                This_Dev = This_Dev.split("/")[2]
                This_Dev = re.sub("[0-9]*$", "", This_Dev)
                This_Dev = "/dev/" + This_Dev

                This_SAS = line.split(" ")[-3]
                This_SAS = This_SAS.split("-")[1]
                This_SAS = This_SAS.split("x")[1]

                Debug("map_VD_wwn_to_Dev()::  Adding Dev " + This_Dev + " SAS " + This_SAS)
                Map[This_SAS] = This_Dev

        return(Map)


def map_pd_to_vd_with_storcli():

	"""
	Find the mapping between virtual disk and physical disk on computers with a "storcli64" accesssible HBA
	"""

	Debug("map_pd_to_vd_with_storcli():: Function entry")

	map_vd_dev = map_WWN_to_Dev()

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

	PD_to_VD_Map = []
	for VD, list in VD_to_PD_Map.items():
		PD_List = VD_to_PD_Map[VD]["PD_List"]
		for i in PD_List:

			e = i.split(":")[0]
			s = i.split(":")[1]

			for line in SysExec("storcli64 /c0/e" + str(e) + "/s" + str(s) + " show all").splitlines():

				if re.search("^WWN", line):
					WWN = line.split("=")[1].strip()

				if re.search("^SN", line):
					Serial = line.split("=")[1].strip()

				if re.search("Manufacturer Id", line):
					Mfg_Id = line.split("=")[1].strip()

				if re.search("Model Number", line):
					Model = line.split("=")[1].strip()

			PD_to_VD_Map.append([i, e, s, map_vd_dev[VD_to_PD_Map[VD]["scsi_naa_id"]], WWN.lower(), Mfg_Id, Model, Serial, VD, VD_to_PD_Map[VD]["scsi_naa_id"]])

	Debug("map_pd_to_vd_with_storcli():: PD_to_VD_Map = " + str(PD_to_VD_Map))

	Debug("map_pd_to_vd_with_storcli():: Function exit")

	return(PD_to_VD_Map)


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

		Debug("map_intermediate_SAS_to_WWN_with_sas2ircu()::  val_device = " + str(val_device) + " val_sas = " + str(val_sas) + " val_wwn = " + str(val_wwn))

		if val_device and val_sas and val_wwn:
			if val_device == "Hard disk":
				Map[val_wwn] = val_sas

			val_device    = None
			val_sas       = None
			val_wwn       = None

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
        #        print("INFO: The LSI 'MegaCli64' utility was not found.  Mapping drives to enclosure/slot might not work.")
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
                        if val_sas.startswith("5"):
                                val_wwn = hex(int(val_sas, 16) + 2).split("x")[1].lower()

                        Debug("map_intermediate_SAS_to_WWN_with_MegaCli()::  SAS " + str(val_sas) + " maps to WWN " + str(val_wwn))
                        Map[val_wwn] = val_sas

                        val_wwn = None
                        val_sas = None

        Debug("def map_intermediate_SAS_to_WWN_with_Megacli():: Map = " + str(Map))
        Debug("def map_intermediate_SAS_to_WWN_with_MegaCli() exit")

        return Map


def dict_VD_to_PD():
	"""
	Return a simple dict of virtual disk wwn -> physical disk wwn
	"""

	Dict_VD_to_PD = {}

	for i in map_pd_to_vd_with_storcli():
		Dict_VD_to_PD[i[9]] = hex(int(i[4], 16) + 1).split("x")[1].lower()

	return(Dict_VD_to_PD)


def dict_ES_to_Serial():
	"""
	Return a simple dict of E:S -> Serial # for virtual disks since they obscure the actual serial #
	"""

	Dict_ES_to_Serial = {}

	for i in map_pd_to_vd_with_storcli():
		Dict_ES_to_Serial[i[0]] = i[7]

	Debug("dict_ES_to_Serial():: Map = " + str(Dict_ES_to_Serial))

	return(Dict_ES_to_Serial)


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
		if re.search("/dev/zram", i) or re.search("/dev/ram", i):
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

        return LedState_Descr


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

#	Debug("HumanFriendlySerial():: Start Serial = " + str(Serial))

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

#	Debug("HumanFriendlySerial():: End Serial = " + str(Serial))

	return Serial

def standardize_Serial(SCSI_IDENT_SERIAL, ID_SCSI_SERIAL):
	"""
	The HBA/backplane/drive stack seemingly randomly returns either the human-visble
	serial num on the drive label, or the "05" SATA/SAS serial.   I want to standardize
	this to the extent possible.   Look at the serial #.   If it starts with "5" or "0x5",
	call it the "HBA_SERIAL".   Otherwise call it the HR_SERIAL (Human-Readable Serial).
	This is inherently a "best effort" attempt.
	"""
	HR_Serial  = "None"
	HBA_Serial = "None"

#	Debug("standardize_Serial():: Start serial = " + str(SCSI_IDENT_SERIAL) + " and "  + str(ID_SCSI_SERIAL))

	# Bail out on virtual disks quick...
	if len(ID_SCSI_SERIAL) == 32 and ID_SCSI_SERIAL.endswith("00506"):
		return(SCSI_IDENT_SERIAL, ID_SCSI_SERIAL)

	if SCSI_IDENT_SERIAL == ID_SCSI_SERIAL:
		if re.search("^5", SCSI_IDENT_SERIAL) or re.search("0x5", SCSI_IDENT_SERIAL):
			HBA_Serial = SCSI_IDENT_SERIAL
			HR_Serial = "Unknown"
		else:
			HR_Serial = SCSI_IDENT_SERIAL
			HBA_Serial = "Unknown"

#	Debug("standardize_Serial():: Intermediate 1 = " + str(HR_Serial) + " and "  + str(HBA_Serial))

	if re.search("^5", SCSI_IDENT_SERIAL) or re.search("0x5", SCSI_IDENT_SERIAL):
		HBA_Serial = SCSI_IDENT_SERIAL
	else:
		HR_Serial  = SCSI_IDENT_SERIAL

#	Debug("standardize_Serial():: Intermediate 2 = " + str(HR_Serial) + " and "  + str(HBA_Serial))

	if re.search("^5", ID_SCSI_SERIAL) or re.search("0x5", ID_SCSI_SERIAL):
		HBA_Serial = ID_SCSI_SERIAL
	else:
		HR_Serial  = ID_SCSI_SERIAL

#	Debug("standardize_Serial():: Intermediate 3 = " + str(HR_Serial) + " and "  + str(HBA_Serial))

	if HR_Serial == "None" or HR_Serial == "Unknown":
		HR_Serial = HBA_Serial

#	Debug("standardize_Serial():: Final serial = " + str(HR_Serial) + " and "  + str(HBA_Serial))

	return (HR_Serial, HBA_Serial)


#####################################################################################
### Start of program
#####################################################################################

LSPCI_BIN = Bin_Requires("lspci")
LSSCSI_BIN = Bin_Requires("lsscsi")
SG_SES_BIN = Bin_Recommends("sg_ses")
UDEVADM_BIN = Bin_Requires("udevadm")
SMARTCTL_BIN = Bin_Requires("smartctl")

Controller = Get_SASController()
for i in Controller:

	# For Falcon controllers, we need an assist from sas2ircu to map SATA drives to backplane/slot
	if re.search("Falcon", i):
		fal_map = map_intermediate_SAS_to_WWN_with_sas2ircu()
		Falcon = True

	# For Thunderbolt/Invader, we need MegaCLI
	if re.search("Thunderbolt", i) or re.search("Invader", i):
		thu_map = map_intermediate_SAS_to_WWN_with_MegaCli()
		Thunderbolt = True

enclosures = Get_Enclosure_Info()
Debug("enclosures = " + str(enclosures))

map_enclosure_sgdev_to_alias = {}
for i in enclosures:
	map_enclosure_sgdev_to_alias[i[0]] = i[4]
Debug("map_enclosure_sgdev_to_alias = " + str(map_enclosure_sgdev_to_alias))

#map_enclosure_e_to_alias = {}
#for i in enclosures:
#	map_enclosure_e_to_alias[i[2].split(":")[2]] = i[4]
#Debug("map_enclosure_e_to_alias = " + str(map_enclosure_e_to_alias))

#Output.append([SG_Dev, Num_Slots, SG_Bus, SAS_Addr, Alias])

map_enclosure_e_to_sgdev = {}
for i in enclosures:
	map_enclosure_e_to_sgdev[i[2].split(":")[2]] = i[0]
Debug("map_enclosure_e_to_sgdev = " + str(map_enclosure_e_to_sgdev))

# Blank dictionary to hold parsed output from the "sg_ses" command
sg_ses_dict = {}

# Iterate over all enclosures...
if enclosures:

	for i in enclosures:
		e         = i[0] # "/dev/sg13"
		num_slots = i[1] # "12"
		sg_bus    = i[2] # "0:0:12:0"
		sg_wwn    = i[3] # "50015b21401add7f"
		alias     = i[4] # "Front"

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

Debug("sg_ses_dict = " + str(sg_ses_dict))


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
	"ID_SERIAL_SHORT",\
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
		udevadm_dict[bd]["MEDIA_TYPE"] = "SSD"
	else:
		udevadm_dict[bd]["MEDIA_TYPE"] = "HD"

	# Parse "udevadm" output
	udevadm_output = SysExec("udevadm info --query=property --name=" + bd)
	for line in udevadm_output.splitlines():
		line = ' '.join(line.split()).strip()

		key = line.split("=")[0]
		val = line.split("=")[1]

		udevadm_dict[bd][key] = val

sorted_keys = sorted(udevadm_dict.keys())
udevadm_dict = {key:udevadm_dict[key] for key in sorted_keys}

#Debug("Main:: udevadm_dict = " + str(udevadm_dict))

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
				udevadm_dict[bd]['ID_BUS'] = "NVME"
	else:
		if udevadm_dict[bd]['ID_BUS'] == "scsi":
			udevadm_dict[bd]['ID_BUS'] =  "SAS"
		elif udevadm_dict[bd]['ID_BUS'] == "ata":
			udevadm_dict[bd]['ID_BUS'] = "SATA"
		else:
			udevadm_dict[bd]['ID_BUS'] = udevadm_dict[bd]['ID_BUS'].upper()

	if not "SCSI_VENDOR" in udevadm_dict[bd]:
		udevadm_dict[bd]["SCSI_VENDOR"] = " "

	# Virtual disks on LSI HBA's
	if len(udevadm_dict[bd]["SCSI_IDENT_SERIAL"]) == 32 and udevadm_dict[bd]["SCSI_IDENT_SERIAL"].endswith("00506"):
		if not "map_dev_to_serial" in globals():
			Virtual_Disks_Present = True
			map_dev_to_serial = map_pd_to_vd_with_storcli()

			map_tmp_mfg = {}
			map_tmp_model = {}
			map_tmp_serial = {}
			for i in map_dev_to_serial:
				map_tmp_mfg[i[3]]    = i[5]
				map_tmp_model[i[3]]  = i[6]
				map_tmp_serial[i[3]] = i[7]

		udevadm_dict[bd]["SCSI_IDENT_SERIAL"] = map_tmp_serial[bd]
		udevadm_dict[bd]["ID_MODEL"]          = map_tmp_model[bd]
		udevadm_dict[bd]["SCSI_VENDOR"]       = map_tmp_mfg[bd]

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

	# Trim Seagate serial #'s to the first 8 characters
	if udevadm_dict[bd]["SCSI_VENDOR"] == "Seagate":
		udevadm_dict[bd]["SCSI_IDENT_SERIAL"] = udevadm_dict[bd]["SCSI_IDENT_SERIAL"][0:8]

	# Trim the leading "WD-" on WDC Serial #'s
	if udevadm_dict[bd]["SCSI_VENDOR"] == "WDC":
		udevadm_dict[bd]["SCSI_IDENT_SERIAL"] = re.sub("^WD-", "", udevadm_dict[bd]["SCSI_IDENT_SERIAL"])


### Remove all entries except the ones in the whitelist
tmp = {}
for bd in udevadm_dict:
	tmp[bd] = {}
	for key in keys_whitelist:
		if key in udevadm_dict[bd]:
			tmp[bd][key] = udevadm_dict[bd][key]
		else:
			tmp[bd][key] = ""
udevadm_dict = tmp

##############################################################################
### Join sg_ses_dict to udevadm_dict
##############################################################################
sd_to_sg_map = map_sd_to_sg()

for bd in udevadm_dict:

	# This is result on drives attached via SATA, NVME, and other non-enclosure topologies
	search = "unknown"

	# Find the search term to match with the sg_ses_dict
	if "SCSI_IDENT_PORT_NAA_REG" in udevadm_dict[bd]:
		if re.search("^5", udevadm_dict[bd]["SCSI_IDENT_PORT_NAA_REG"]):
			search = udevadm_dict[bd]["SCSI_IDENT_PORT_NAA_REG"]

	if search == "unknown" and "SCSI_IDENT_SERIAL" in udevadm_dict[bd]:
		if re.search("^5", udevadm_dict[bd]["SCSI_IDENT_SERIAL"]) and len(udevadm_dict[bd]["SCSI_IDENT_SERIAL"]) == 32:
			# We want to subtract 2 from whatever value is here
			search = udevadm_dict[bd]["SCSI_IDENT_SERIAL"]
			print("DEBUG:  search = " + str(search))

			search = hex(int(search, 16) - 2)
			search = re.sub("^0x", "", search)

	if search == "unknown" and "ID_SERIAL_SHORT" in udevadm_dict[bd]:
		if re.search("^5", udevadm_dict[bd]["ID_SERIAL_SHORT"]) and len(udevadm_dict[bd]["ID_SERIAL_SHORT"]) == 32:
			# We want to subtract 2 from whatever value is here
			search = udevadm_dict[bd]["ID_SERIAL_SHORT"]
			search = hex(int(search, 16) - 2)
			search = re.sub("^0x", "", search)

	# Get WWN map using sas2irc
	if "Falcon" in vars():
		if "ID_WWN" in udevadm_dict[bd]:
			st = re.sub("0x", "", udevadm_dict[bd]["ID_WWN"])
			if st in fal_map:
				search = fal_map[st]

	# Get WWN map using MegaCLI
	if "Thunderbolt" in vars():
		if "ID_WWN" in udevadm_dict[bd]:
			st = re.sub("0x", "", udevadm_dict[bd]["ID_WWN"])
			if st in thu_map:
				search = thu_map[st]

	# If there are no enclosures, there's nothing to map to sg_ses...
	if search != "unknown" and enclosures:
		for e in sg_ses_dict:
			for s in sg_ses_dict[e]:
				if sg_ses_dict[e][s]["media_wwn"] == "0x" + search:
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

	Debug("s_ident for bd " + str(bd) + " = " + str(udevadm_dict[bd]["s_ident"]))

	udevadm_dict[bd]["DISK_SIZE"] = HumanFriendlyBytes(findRawSize(bd), 1000, 0)

	# Get enclosure/slots/led status for virtual disks
	if "Virtual_Disks_Present" in vars():
		map_tmp_enclosure = {}
		map_tmp_slot = {}
		for i in map_dev_to_serial:
			map_tmp_enclosure[i[3]] = i[1]
			map_tmp_slot[i[3]]      = i[2]

# map_enclosure_e_to_sgdev

		if bd in map_tmp_enclosure:
			udevadm_dict[bd]["enclosure"] = map_enclosure_e_to_sgdev[map_tmp_enclosure[bd]]
			Debug("enclosure = " + str(udevadm_dict[bd]["enclosure"]))

		if bd in map_tmp_slot:
			udevadm_dict[bd]["slot"]      = map_tmp_slot[bd]
			Debug("slot = " + udevadm_dict[bd]["slot"])

	udevadm_dict[bd]["Enclosure_Alias"] = "None"
	if udevadm_dict[bd]["enclosure"] in map_enclosure_sgdev_to_alias:
		udevadm_dict[bd]["Enclosure_Alias"] = map_enclosure_sgdev_to_alias[udevadm_dict[bd]["enclosure"]]


	if udevadm_dict[bd]["enclosure"] != "None":
#		udevadm_dict[bd]["s_ident"] = sg_ses_dict[udevadm_dict[bd]["enclosure"]][str(int(udevadm_dict[bd]["slot"]) - 1)]["s_ident"]

		# The offset has to be changed on a per-card basis.  :-/
		udevadm_dict[bd]["slot"] = str(int(udevadm_dict[bd]["slot"]) - 1)
		udevadm_dict[bd]["s_ident"] = sg_ses_dict[udevadm_dict[bd]["enclosure"]][udevadm_dict[bd]["slot"]]["s_ident"]


#	if udevadm_dict[bd]["enclosure"] in map_enclosure_e_to_alias:
#		udevadm_dict[bd]["Enclosure_Alias"] = map_enclosure_e_to_alias[udevadm_dict[bd]["enclosure"]]

# sg_ses_dict[e][s]["s_ident"] = val_txt


	if bd in sd_to_sg_map:
		udevadm_dict[bd]["SG_DEV"]    = sd_to_sg_map[bd]
	else:
		udevadm_dict[bd]["SG_DEV"]    = "None"

	if re.search("/dev/nvme", bd):
		udevadm_dict[bd]["SG_DEV"]    = "None"
		udevadm_dict[bd]["enclosure"] = "None"
		udevadm_dict[bd]["slot"]      = "NA"
		udevadm_dict[bd]["s_ident"]   = "None"

	# This model lies about its size
	if udevadm_dict[bd]["ID_MODEL"] == "ST8000NM0065":
		udevadm_dict[bd]["DISK_SIZE"] = "8 TB"
# PARTON
#for bd in udevadm_dict:
#	udevadm_dict[bd]["slot"] = str(int(udevadm_dict[bd]["slot"]) - 1)

Debug("udevadm_dict = " + str(udevadm_dict))

##############################################################################
### PrettyPrint the dict and exit
##############################################################################

# Rename these columns to something human-readible when we print
pretty_name = {
	#  Old_Name             New_Name  \
	"DEVNAME":           "SD_Dev",   \
#	"SG_DEV":            "SG_Dev",   \
	"SCSI_VENDOR":       "Vendor",   \
	"ID_MODEL":          "Model",    \
	"SCSI_IDENT_SERIAL": "Serial",   \
	"SCSI_REVISION":     "Firmware", \
	"ID_BUS":            "Bus",      \
	"MEDIA_TYPE":        "Media",    \
	"DISK_SIZE":         "Size",     \
	"enclosure":         "Enclosure_SGDev",\
	"Enclosure_Alias":   "Enclosure", \
	"slot":              "Slot",     \
	"s_ident":           "Locate_LED"
}
print_list  = pretty_name.keys()
pretty_list = pretty_name.values()

# Rename columns to their pretty_name equivalents
for bd in udevadm_dict:
	for o_key, n_key in pretty_name.items():
		udevadm_dict[bd][n_key] = udevadm_dict[bd].pop(o_key)


# Measure the width of the column titles
ParamLength = {}
for bd, dict in udevadm_dict.items():
	for key, val in dict.items():
		if not key in pretty_list:
			continue

		ParamLength[key] = key.__len__()

# Measure the width of the data entries
for bd, dict in udevadm_dict.items():
	for key, val in dict.items():
		if not key in pretty_list:
			continue

		if isinstance(val, str):
			ValueLength = val.__len__()
		elif isinstance(val, int):
			ValueLength = math.log10(float(t) + 0.001)
			if ValueLength < 0:
				ValueLength = 1
			ValueLength = int(math.floor(ValueLength))

		ParamLength[key] = max(ValueLength, ParamLength[key])

# Create a format statement of the appropriate length
TOTALLENGTH = 0
FORMAT=""
for param in ParamLength:
	FORMAT = FORMAT + " %-" + str(ParamLength[param] + 2) + "s "
	TOTALLENGTH = TOTALLENGTH + ParamLength[param] + 4
TOTALLENGTH = TOTALLENGTH - 2

# Print it and done...
print("")
print(FORMAT % tuple(pretty_list))
print("=" * TOTALLENGTH)

for bd, dict in udevadm_dict.items():
	printline = []
	for key, val in dict.items():
		if not key in pretty_list:
			continue
		printline.append(val)
	print(FORMAT % tuple(printline))
print("")
