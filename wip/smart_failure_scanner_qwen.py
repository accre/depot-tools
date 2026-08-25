#!/usr/bin/env python3

# smart_failure_scanner_qwen.py - fixes applied to smart_failure_scanner.py:
#   #1 findSerial() no longer crashes on SATA/NVMe (guarded readSerial())
#   #2 findVendor()/findModel() no longer crash on NVMe (safe* variants,
#      NVMe model/serial read from /sys/class/nvme/<controller>/)
#   #3 self-test status parsing no longer IndexErrors on the status line and
#      no longer drops column-0 failure text (window-based parse)
#   #4 NVMe drives are now actually scanned (new NVMe branch, reliable
#      detection, NVMe classified up front in the enumeration loop)

import os
import re
import sys
import time
import math
import threading
import socket

from subprocess import Popen, PIPE, STDOUT, call, check_output
from time import gmtime, strftime, sleep

# Arrays for SysExec caching
CacheDataArray = {}
CacheTimeArray = {}

# Set "True" to print debugging info
Print_Debug = False

# Do we want to be "Picky" or "Practical".
# "Picky" sets reporting thresholds to 0, so a single error will report a message
# "Practical" sets reporting thresholds to minimize minor messages
Reports = "Practical"
#Reports = "Picky"

if Reports == "Picky":
	Thresh_197 = 0
	Grown_Defect_Thresh = 0
	Smart_Attribute_Thresh = 0
	total_read_thresh = 0
	total_write_thresh = 0
	read_correction_thresh = 0
	write_correction_thresh = 0
	blocks_reassigned_thresh = 0

elif Reports == "Practical":
	Thresh_197 = 500
	Grown_Defect_Thresh = 10
	Smart_Attribute_Thresh = 10
	total_read_thresh = 10
	total_write_thresh = 10
	read_correction_thresh = 10
	write_correction_thresh = 10
	blocks_reassigned_thresh = 2

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

	# Cache the output of the command for the given number of seconds
	Cache_Expires = 60

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


def ComputerFriendlyBytes(bytes, scale, units, optional_scale = None):

	"""
	Convert a size ("72 TB") into actual bytes
	Base 1000 units = KB, MB, GB, TB, etc.
	Base 1024 units = KiB, MiB, GiB, TiB, etc.
	"""

	if optional_scale == None:
		optional_scale = scale

	AcceptableScales = [ 1000, 1024 ]

	if not scale in AcceptableScales:
		return "ERROR"

	if bytes == 0:
		return "0B"

	if optional_scale == 1000:
		UNITS = [ "B",  "KB",  "MB",  "GB",  "TB",  "PB",  "EB",  "ZB",  "YB" ]
	if optional_scale == 1024:
		UNITS = [ "B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB" ]

	unit_power = UNITS.index(units)

	multiplier = pow(scale, unit_power)

	return (bytes * multiplier)


def HumanFriendlyBytes(bytes, scale, decimals):

	"""
	Convert a integer number of bytes into something legible (10 GB or 25 TiB)
	Base 1000 units = KB, MB, GB, TB, etc.
	Base 1024 units = KiB, MiB, GiB, TiB, etc.
	"""

	AcceptableScales = [ 1000, 1024 ]

	if not scale in AcceptableScales:
		return "ERROR"

	if bytes == 0:
		return "0B"

	unit_i = int(math.floor(math.log(bytes, scale)))

	if scale == 1000:
		UNITS = [ "B",  "KB",  "MB",  "GB",  "TB",  "PB",  "EB",  "ZB",  "YB" ]
	if scale == 1024:
		UNITS = [ "B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB" ]

	scaled_units = UNITS[unit_i]
	scaled_size = round(bytes / math.pow(scale, unit_i), decimals)

	return(str(scaled_size) + " " + scaled_units)


def findRawSize(SD_Device):

	"""
	Fetch raw device size (in bytes) by multiplying "/sys/block/DEV/queue/hw_sector_size"
	by /sys/block/DEV/size
	"""

	if not re.search("^/c", SD_Device):

		secsize = "0"
		numsec  = "0"

		tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/size"
		if os.path.isfile(tfile):
			numsec = SysExec("cat " + tfile).strip()

		tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/queue/hw_sector_size"
		if os.path.isfile(tfile):
			secsize = SysExec("cat " + tfile).strip()

		return int(numsec) * int(secsize)

	if re.search("^/c", SD_Device):

		f = SysExec("storcli64 " + SD_Device + " show all")

		for l in f.splitlines():

			if not re.search("^Raw", l):
				continue

			size = l.split("=")[1].split("[")[0].strip().split(" ")
			return ComputerFriendlyBytes(float(size[0]), 1024, size[1], 1000)


def map_dev_to_rid():

	Dict_Dev_to_Rid = {}

	if os.path.isdir("/dev/disk/by-label"):

		for line in os.listdir("/dev/disk/by-label"):
			if not re.search("rid-data", line):
				continue

			rid = line.split("-")[2]
			dev = os.path.realpath("/dev/disk/by-label/" + line)
			dev = re.sub("[0-9]*$", "", dev)

			Dict_Dev_to_Rid[dev] = rid

	Debug("map_dev_to_rid():: map = " + str(Dict_Dev_to_Rid))

	return(Dict_Dev_to_Rid)


def findVendor(SD_Device):
	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/vendor"
	f = open(file, "r")
	vendor = f.read()
	f.close()
	return(vendor.strip())

def findMBVendor():
	file = "/sys/devices/virtual/dmi/id/board_vendor"
	f = open(file, "r")
	vendor = f.read()
	f.close()
	return(vendor.strip())

def findModel(SD_Device):
	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/model"
	f = open(file, "r")
	model = f.read()
	f.close()
	return(model.strip())

def findSerial(SD_Device):
	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/vpd_pg80"

	f = open(file, "rb")
	f.seek(4)
	serial = f.read()
	f.close()
	serial = serial.decode("utf-8")

	return(serial.strip())

def _readSysfsText(path):
	"""
	Read a sysfs text file, returning "" if it does not exist or cannot be read.
	Never raises.
	"""

	try:
		with open(path, "r") as f:
			return f.read().strip()
	except Exception:
		return ""

def _nvmeControllerName(DevName):
	"""
	Map an NVMe block device name (e.g. "nvme0n1") to its controller
	name (e.g. "nvme0").  Returns None for non-NVMe names.
	Model/serial live under /sys/class/nvme/<controller>/, not under the
	namespace block device.
	"""

	m = re.search("^(nvme[0-9]+)", DevName)
	if m:
		return m.group(1)
	return None

def readSerial(SD_Device):
	"""
	Return the drive serial number, or "" if it cannot be determined.

	SAS drives:   /sys/block/DEV/device/vpd_pg80 (serial starts at offset 4)
	NVMe drives:  /sys/class/nvme/nvmeN/serial
	SATA drives:  no sysfs serial available (smartctl -x has it, but parsing
	               it here is out of scope), so return "".

	Never raises: a missing serial must not abort the whole scan.
	"""

	name = SD_Device.split("/")[-1]

	# NVMe drives: serial lives in the nvme class, not under /sys/block/DEV/device
	ctrl = _nvmeControllerName(name)
	if ctrl:
		return _readSysfsText("/sys/class/nvme/" + ctrl + "/serial")

	# SAS VPD page 80: 4-byte header, then the serial number
	try:
		with open("/sys/block/" + name + "/device/vpd_pg80", "rb") as f:
			f.seek(4)
			return f.read().decode("utf-8", errors="replace").strip()
	except Exception:
		# SATA and some virtual drives have no vpd_pg80 - that is normal
		return ""

def findVendor(SD_Device):
	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/vendor"
	f = open(file, "r")
	vendor = f.read()
	f.close()
	return(vendor.strip())

def safeFindVendor(SD_Device):
	"""
	Like findVendor(), but returns "" instead of raising when the sysfs file is
	missing (e.g. NVMe drives, which have no /sys/block/DEV/device symlink).
	"""

	name = SD_Device.split("/")[-1]
	vendor = _readSysfsText("/sys/block/" + name + "/device/vendor")
	if vendor:
		return vendor
	if _nvmeControllerName(name):
		# Vendor is not exposed in sysfs for NVMe
		return "NVMe"
	return ""

def findModel(SD_Device):
	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/model"
	f = open(file, "r")
	model = f.read()
	f.close()
	return(model.strip())

def safeFindModel(SD_Device):
	"""
	Like findModel(), but returns "" instead of raising when the sysfs file is
	missing (e.g. NVMe drives, which have no /sys/block/DEV/device symlink).
	NVMe model lives under /sys/class/nvme/<controller>/.
	"""

	name = SD_Device.split("/")[-1]
	model = _readSysfsText("/sys/block/" + name + "/device/model")
	if model:
		return model
	ctrl = _nvmeControllerName(name)
	if ctrl:
		model = _readSysfsText("/sys/class/nvme/" + ctrl + "/model")
		if model:
			return model
	return ""

def printDev(Dev, Str):

	Debug("printDev::Dev = " + str(Dev))
	Debug("printDev::Str = " + str(Str))

	Vendor = safeFindVendor(Dev)
	Model = safeFindModel(Dev)
	Serial = readSerial(Dev)

	rid_dev_map = map_dev_to_rid()

	if Vendor == "SEAGATE":
		Serial = Serial[0:8]

	Ridstr = ""
	if Dev in rid_dev_map:
		Rid = rid_dev_map[Dev]
		Ridstr = str(Rid)

	Size = HumanFriendlyBytes(findRawSize(Dev), 1000, 0)
	Size = re.sub("\\.0", "", Size)
	Size = re.sub(" ", "", Size)

	print('{:20s}|{:4s}|{:15s}|{:7s}|{:2s}|{:22s}|{:4s}|{:30s}' . format(socket.gethostname(), Ridstr, Serial, " ", " ", Vendor + " " + Model, Size, Str))


def printDevVirt_storcli(Dev, Vendor, Model, Serial, Str):

	if Vendor == "SEAGATE":
		if Serial:
			Serial = Serial[0:8]

	Size = HumanFriendlyBytes(findRawSize(Dev), 1000, 0)
	Size = re.sub("\\.0", "", Size)
	Size = re.sub(" ", "", Size)

	print('{:20s}|{:4s}|{:15s}|{:7s}|{:2s}|{:22s}|{:4s}|{:30s}' . format(socket.gethostname(), Dev, Serial, " ", " ", Vendor + " " + Model, Size, Dev + ":" + Str))


def Get_SASController():

	"""
	Return the SAS controller model in this depot.
	"""

	Debug("Get_SASController():: function entry")

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

	SAS_Controller_List = []

	if any(re.search("Invader", entry) for entry in SAS_Controller):
		SAS_Controller_List.append("LSI_Invader")

	if any(re.search("Falcon", entry) for entry in SAS_Controller):
		SAS_Controller_List.append("LSI_Falcon")

	if any(re.search("Thunderbolt", entry) for entry in SAS_Controller):
		SAS_Controller_List.append("LSI_Thunderbolt")

	if any(re.search("Tri-Mode", entry) for entry in SAS_Controller):
		SAS_Controller_List.append("LSI_Trimode")

	Debug("Get_SASController():: function exit")

	return(SAS_Controller_List)


def get_errors_from_storcli():

	"""
	Return a reduced output of errors found for any virtual disks attached
	to a LSI controller that uses storcli64
	"""

	if re.search("Dell", findMBVendor()):
		STORCLI_Bin = "/opt/MegaRAID/perccli/perccli64"
	else:
		STORCLI_Bin = "storcli64"

	Debug("get_errors_from_storcli():: STORCLI_Bin = " + str(STORCLI_Bin))

	output = SysExec(STORCLI_Bin + " /cALL/eALL/sALL show all")

	for line in output.splitlines():

		if not re.search("^Drive|Shield Counter|Error Count|Failure Count|S.M.A.R.T.|^SN|^Manufacturer|^Model", line):
			continue

		if re.search("Drive position|Policies/Settings|Device attributes|Detailed Information|State|Temperature", line):
			continue

		# If we have Drive (first line) and Model (last line), assume we've completed one pass through
		if "Drive" in locals() and "Model" in locals():
			if Drive is not None and Model is not None:

				Debug(str(Drive) + " " + str(Vendor) + " " + str(Model) + " " + str(Serial) + " " + str(Shield_Counter) + " " + str(Media_Error_Count) + " " + str(Other_Error_Count) + " " + str(Predictive_Failure_Count) + " " + str(SMART_alert))

				if Shield_Counter != 0 and Shield_Counter != "N/A":
					printDevVirt_storcli(Drive, Vendor, Model, Serial, "Shield Counter = " + str(Shield_Counter))
				Shield_Counter = None

				if Media_Error_Count != 0 and Media_Error_Count != "N/A":
					printDevVirt_storcli(Drive, Vendor, Model, Serial, "Media Error Count = " + str(Media_Error_Count))
				Media_Error_Count = None

				if Other_Error_Count != 0 and Other_Error_Count != "N/A":
					printDevVirt_storcli(Drive, Vendor, Model, Serial, "Other Error Count = " + str(Other_Error_Count))
				Other_Error_Count = None

				if Predictive_Failure_Count != 0 and Predictive_Failure_Count != "N/A":
					printDevVirt_storcli(Drive, Vendor, Model, Serial, "Predictive Failure Count = " + str(Predictive_Failure_Count))
				Predictive_Failure_Count = None

				if SMART_alert != "No" and SMART_alert != "N/A":
					printDevVirt_storcli(Drive, Vendor, Model, Serial, "SMART alert flagged by drive = " + str(SMART_alert))
				SMART_alert = None

				Drive = None
				Serial = None
				Vendor = None
				Model = None

		if re.search("Drive", line):
			Drive = line.split()[1]

		if re.search("Shield Counter", line):
			if re.search("N/A", line):
				Shield_Counter = "N/A"
			else:
				Shield_Counter = int(line.split("=")[1].strip())

		if re.search("Media Error Count", line):
			if re.search("N/A", line):
				Media_Error_Count = "N/A"
			else:
				Media_Error_Count = int(line.split("=")[1].strip())

		if re.search("Other Error Count", line):
			if re.search("N/A", line):
				Other_Error_Count = "N/A"
			else:
				Other_Error_Count = int(line.split("=")[1].strip())

		if re.search("Predictive Failure Count", line):
			if re.search("N/A", line):
				Predictive_Failure_Count = "N/A"
			else:
				Predictive_Failure_Count = int(line.split("=")[1].strip())

		if re.search("S.M.A.R.T alert flagged by drive", line):
			SMART_alert = line.split("=")[1].strip()

		if re.search("^SN", line):
			Serial = line.split("=")[1].strip()

		if re.search("^Manufacturer", line):
			Vendor = line.split("=")[1].strip()

		if re.search("^Model Number", line):
			Model = line.split("=")[1].strip()



################################################################################
# Main()::
################################################################################

# Get a list of block devices
Devs = []
Output = os.listdir("/sys/block")
for line in Output:

	# Skip various non-block devices
	if re.search("^loop|^ram|^dm|^zram|^md|^zd|^sr", line):
		continue

	Devs.append("/dev/" + line)

Debug("Block devices found: " + str(Devs))

# SysExec() caches the output of all commands it runs.  Run "smartctl -a " on
# all drives in parallel then wait for them to complete to speed up access later
jobs = []
for Dev in Devs:
	Debug("Spawning SysExec 'sudo smartctl -x' process on Dev " + Dev)
	p = threading.Thread(target = SysExec, args = ("sudo smartctl -x " + Dev, ))
	jobs.append(p)
	p.start()

Debug("Waiting for SysExec() jobs to complete...")
for job in jobs:
	job.join(30)

# Determine the drive transport (SAS, SAS, NVME, Virtual) for each disk
Drive_Transport = {}
for Dev in Devs:

	# NVMe drives have no /sys/block/DEV/device sysfs tree (findModel() would
	# crash on them), and findRawSize() relies on queue/hw_sector_size which
	# is not a reliable size source for NVMe.  Classify them up front (match
	# the basename, not the full /dev/ path) and scan them with the NVMe
	# branch below.
	if _nvmeControllerName(Dev.split("/")[-1]):
		size_text = _readSysfsText("/sys/block/" + Dev.split("/")[-1] + "/size")
		try:
			HD_Size = 512 * int(size_text)
		except ValueError:
			HD_Size = 0
		if HD_Size == 0:
			printDev(Dev, "Disk size = 0 bytes, apparent media failure")
		Drive_Transport[Dev] = "NVME"
		continue

	HD_Size  = findRawSize(Dev)
	HD_Model = safeFindModel(Dev)
	HD_Capacity = HumanFriendlyBytes(HD_Size, 1000, 0)

	# If the drive has a size of 0 bytes, it's fubar
	if HD_Size == 0:
		printDev(Dev, "Disk size = 0 bytes, apparent media failure")

	# Find out if the drive is SATA or SAS
	Drive_Transport[Dev] = "SATA"   # By default
	for line in SysExec("sudo smartctl -x " + Dev).splitlines():


		# Dell firmware is a lying SOB...
		if re.search("PERC", line):
			Drive_Transport[Dev] = "Virtual"
			break

		if re.search("DELL or MegaRaid controller, please try adding", line):
			Drive_Transport[Dev] = "Virtual"
			break

		# This line appears to be standard on SAS drives
		if re.search("Transport protocol", line) and re.search("SAS", line):
			Drive_Transport[Dev] = "SAS"
			break

		# Detect NVME flash drives.  smartctl prints "Device type:          nvme"
		# in the device section; the "NVMe Version:" line only appears in NVMe
		# output.  (The old " NVM " regex required a space on both sides and
		# missed most real output.)
		if re.search("Device type:\s*nvme", line) or re.search("NVMe Version", line):
			Drive_Transport[Dev] = "NVME"
			break

		# Used by the virtual disks exported by our LSI HBA's
		if re.search("Vendor:", line) and re.search("AVAGO", line):
			Drive_Transport[Dev] = "Virtual"
			break

#	Debug("Drive transport for " + Dev + " is " + Drive_Transport[Dev])
# Debug("Drive_Transports = " + str(Drive_Transport))

# Start iterating over Devs and searching for errors
smart_attributes_headers = [ "id", "attribute_name", "flags", "value", "worst", "thresh", "fail", "raw_value" ]

# Report any virtual drives, then remove any drives whose Drive_Transport == "Virtual" from Devs:
if "Virtual" in Drive_Transport.values():

	Debug("Virtual disks detected")
	SAS_Controller = Get_SASController()
	Debug("SAS_Controller = " + str(SAS_Controller))

	if "LSI_Invader" in SAS_Controller or "LSI_Trimode" in SAS_Controller or "LSI_Thunderbolt" in SAS_Controller:
		get_errors_from_storcli()


for Dev in Devs:

	Debug("Scanning drive " + str(Dev) + "...")

	Debug("Drive Transport for " + str(Dev) + " is " + str(Drive_Transport[Dev]))

	if Drive_Transport[Dev] == "SATA":

		# Pass 1:  SMART attribute values
		for line in SysExec("sudo smartctl -x " + Dev).splitlines():

			line = line.strip() # Remove leading spaces

			Debug("line = " + str(line))

			if re.search("INQUIRY failed", line):
				printDev(Dev, "failed smartctl inquiry")
				continue

			# SMART attribute lines all start with numbers (after stripping leading spaces)
			if not re.search("^[0-9]", line):
				continue
			# ...but other unwanted lines also start with numbers, so filter them out
			if re.search("^0x", line):
				continue

			if re.search("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]", line):
				continue

			if re.search("Not_testing|Read_scanning|% of test|failed self-tests are outdated", line):
				continue

			if re.search("[0-9a-f][0-9a-f] [0-9a-f][0-9a-f] [0-9a-f][0-9a-f]", line):
				continue

			# At this point, the only thing left should be actual SMART attributes, so pluck them out
			smart_attributes = dict(zip(smart_attributes_headers, line.split()))

			# This is a corner case where value, worst and thresh are all 0.  Just ignore
			if smart_attributes["value"] == "000" and smart_attributes["worst"] == "000" and smart_attributes["thresh"] == "000":
				# There's no good way to know if the drive is actually failing, or if this test is screwy.  Just skip.
				continue

			# One Intel SSD model has a buggy 233 Media_Wearout_Indicator, so ignore that special case
			if smart_attributes["id"] == "233" and findModel(Dev) == "SSDSA2M040G2GC":
				continue

			# Now test for bad drives

			# This is a drive with a large number of failed sectors that isn't yet failing SMART
			if smart_attributes["id"] == "197":
				if int(smart_attributes["raw_value"]) > Thresh_197:
					printDev(Dev, "197 Current_Pending_Sector value over " + str(Thresh_197))

			# Don't report "9 Power_On_Hours" errors, we're gonna use them until they die...
			if smart_attributes["id"] == "9":
				continue

			if not smart_attributes["value"].isnumeric():
				printDev(Dev, "value is not numeric: ", smart_attributes["value"])

			if not smart_attributes["thresh"].isnumeric():
				printDev(Dev, "thresh is not numeric: ", smart_attributes["thresh"])

			Delta = int(smart_attributes["value"]) - int(smart_attributes["thresh"])

			if Delta <= 0:
				printDev(Dev, "failing on SMART attribute " + smart_attributes["id"] + " " + smart_attributes["attribute_name"])

			if Delta < Smart_Attribute_Thresh and Delta > 0 and int(smart_attributes["thresh"]) < 50:
				printDev(Dev, "marginal on SMART attribute " + smart_attributes["id"] + " " + smart_attributes["attribute_name"])


		# Pass 2:  Scan smartctl output for "Self-test execution status:"
		st_lines = SysExec("sudo smartctl -x " + Dev).splitlines()
		for i, line in enumerate(st_lines):
			if not re.search("Self-test execution status:", line):
				continue

			# The status message can span continuation lines, e.g.:
			#   Self-test execution status:      (  0%)<TAB>The previous self-test completed having
			#   the read element of the test failed.
			# The old code did line.split(")")[1] (IndexError when the status
			# line has no ")") and then stopped accumulating at the first
			# letter-starting line - which is also where "the read element of
			# the test failed." starts, so failures were dropped.  Collect a
			# small window of lines after the status line and flatten it, so
			# the failure patterns below match however smartctl wrapped text.
			window = [ line.split(":", 1)[1] ]
			window.extend(st_lines[i+1:i+5])
			msg = ' '.join(' '.join(window).split())

			Debug("Self-test execution status: " + msg)

			if re.search("The previous self-test completed having the read element of the test failed", msg):
				printDev(Dev, "failing a read-element test.")

			if re.search("The previous self-test completed having a test element that failed", msg):
				printDev(Dev, "failing a test-element test.")


	elif Drive_Transport[Dev] == "SAS":

		Defects = 0
		Non_Medium_Errors = 0
		Smart_Failing_Cmd = 0

		for line in SysExec("sudo smartctl -x " + Dev).splitlines():

			if re.search("^SMART Health Status:", line):
				smart_health_status = line.split(":")[1].strip()
				if smart_health_status != "OK":
					printDev(Dev, "non-OK smart status " + smart_health_status)

			if re.search("^Total new blocks reassigned", line):
				blocks_reassigned = re.sub("Total new blocks reassigned", "", line)
				blocks_reassigned = re.sub("<not available>", "0", blocks_reassigned)
				blocks_reassigned = re.sub("=", "", blocks_reassigned)
				blocks_reassigned = int(blocks_reassigned.strip())
				if blocks_reassigned > blocks_reassigned_thresh:
					printDev(Dev, "Total New blocks reassigned = " + str(blocks_reassigned))

			if re.search("Elements in grown defect list", line):
				Defects = int(line.split(":")[1].strip())

				if Defects > 50:
					printDev(Dev, "critically-high number of defects (" + str(Defects) + " defects)")
				elif Defects > Grown_Defect_Thresh and Defects <= 50:
					printDev(Dev, "non-zero number of defects (" + str(Defects) + " defects)")

			# This shows the error count due to non-medium problems like bad HBA, bad cable, etc.
			# Disabled by default, but enable if you're trying to debug depots
			#
#			if re.search("^Non-medium error count", line):
#				Non_Medium_Errors = int(line.split(":")[1].strip())
#				if Non_Medium_Errors > 0:
#					printDev(Dev, "non-zero number of Non-medium errors (" + str(Non_Medium_Errors) + " errors)")

			if re.search("A mandatory SMART command failed", line):
				printDev(Dev, "failing mandatory SMART commands")

			if re.search("^read:", line):
				total_read_uncorrected_errors = int(line.split()[-1])

				if total_read_uncorrected_errors > total_read_thresh:
					printDev(Dev, "total read uncorrected errors > " + str(total_read_thresh) + " (" + str(total_read_uncorrected_errors) + " errors)")

				read_correction_algorithm_invocations = int(line.split()[-3])
				if read_correction_algorithm_invocations > read_correction_thresh:
					printDev(Dev, "read correction algorithm invocations greater than > " + str(read_correction_thresh) + " (" + str(read_correction_algorithm_invocations) + " invocations)")

			if re.search("^write:", line):
				total_write_uncorrected_errors = int(line.split()[-1])

				if total_write_uncorrected_errors > total_write_thresh:
					printDev(Dev, "total write uncorrected errors > " + str(total_write_thresh) + " (" + str(total_write_uncorrected_errors) + " errors)")

				write_correction_algorithm_invocations = int(line.split()[-3])
				if write_correction_algorithm_invocations > write_correction_thresh:
					printDev(Dev, "write correction algorithm invocations greater than > " + str(write_correction_thresh) + " (" + str(write_correction_algorithm_invocations) + " invocations)")

			if re.search("Failed in segment", line) and not "smart_segment" in globals():
				printDev(Dev, "SMART test failed in segment errors")
				smart_segment = True

	elif Drive_Transport[Dev] == "NVME":

		# NVMe drives use a completely different SMART layout ("NVMe SMART
		# Information" section) than SATA/SAS drives, so the attribute table
		# parsing above does not apply.  Check the key NVMe health fields.
		critical_warning = None
		error_log_entries = None
		available_spare = None
		spare_threshold = None

		for line in SysExec("sudo smartctl -x " + Dev).splitlines():

			m = re.search("Critical Warning:\s*(0x[0-9a-fA-F]+)", line)
			if m:
				critical_warning = int(m.group(1), 16)
				continue

			m = re.search("Number of Error Information Log Entries:\s*([0-9]+)", line)
			if m:
				error_log_entries = int(m.group(1))
				continue

			m = re.search("Available Spare:\s*([0-9]+)%", line)
			if m:
				available_spare = int(m.group(1))
				continue

			m = re.search("Available Spare Threshold:\s*([0-9]+)%", line)
			if m:
				spare_threshold = int(m.group(1))
				continue

		if critical_warning is None and error_log_entries is None:
			# smartctl returned no NVMe SMART data (e.g. device inquiry failed)
			printDev(Dev, "failed to read NVMe SMART data")
			continue

		if critical_warning is not None and critical_warning != 0:
			printDev(Dev, "NVMe critical warning flag set (0x%02x)" % critical_warning)

		if error_log_entries is not None and error_log_entries > 0:
			printDev(Dev, "NVMe error log entries = " + str(error_log_entries))

		if available_spare is not None and spare_threshold is not None and available_spare <= spare_threshold:
			printDev(Dev, "NVMe available spare (" + str(available_spare) + "%) at or below threshold (" + str(spare_threshold) + "%)")
