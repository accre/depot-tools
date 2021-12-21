#!/usr/bin/env python3

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
Reports = "Picky"

if Reports == "Picky":
	Enable_Picky = True
	Thresh_197 = 0
	Grown_Defect_Thresh = 0
	Smart_Attribute_Thresh = 0
	total_read_thresh = 0
	total_write_thresh = 0
	read_correction_thresh = 0
	write_correction_thresh = 0

elif Reports == "Practical":
	Enable_Picky = False
	Thresh_197 = 500
	Grown_Defect_Thresh = 10
	Smart_Attribute_Thresh = 10
	total_read_thresh = 10
	total_write_thresh = 10
	read_correction_thresh = 10
	write_correction_thresh = 10


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


def HumanFriendlyBytes(bytes, scale, decimals):

	"""
	Convert a integer number of bytes into something legible (10 GB or 25 TiB)
	Base 1000 units = KB, MB, GB, TB, etc.
	Base 1024 units = KiB, MiB, GiB, TiB, etc.
	"""

	AcceptableScales = [ 1000, 1024 ]

	if not scale in AcceptableScales:
		return "ERROR"

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

	secsize = "0"
	numsec  = "0"

	tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/size"
	if os.path.isfile(tfile):
		numsec = SysExec("cat " + tfile).strip()

	tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/queue/hw_sector_size"
	if os.path.isfile(tfile):
		secsize = SysExec("cat " + tfile).strip()

	return int(numsec) * int(secsize)


def findVendor(SD_Device):

	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/vendor"
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

def printDev(Dev, Str):

	Vendor = findVendor(Dev)
	Model = findModel(Dev)
	Serial = findSerial(Dev)

	if Vendor == "SEAGATE":
		Serial = Serial[0:8]

	Size = HumanFriendlyBytes(findRawSize(Dev), 1000, 0)
	Size = re.sub("\.0", "", Size)
	Size = re.sub(" ", "", Size)

	print(socket.gethostname() + " " + Dev + " [" + Vendor + " " + Model + " " + Size + ", serial " + Serial + "] - " + Str)


################################################################################
# Main()::
################################################################################

# Get a list of block devices
Devs = []
Output = os.listdir("/sys/block")
for line in Output:

	# Skip various non-block devices
	if re.search("^loop|^ram|^dm|^zram|^md|^sr|^drbd|^vd", line):
		continue

	Devs.append("/dev/" + line)

Debug("Block devices found: " + str(Devs))

# SysExec() caches the output of all commands it runs.  Run "smartctl -a " on
# all drives in parallel then wait for them to complete to speed up access later
jobs = []
for Dev in Devs:
	Debug("Spawning SysExec 'smartctl -x' process on Dev " + Dev)
	p = threading.Thread(target = SysExec, args = ("smartctl -x " + Dev, ))
	jobs.append(p)
	p.start()

Debug("Waiting for SysExec() jobs to complete...")
for job in jobs:
	job.join(30)


# Determine the drive transport (SAS, SAS, NVME, Virtual) for each disk
Drive_Transport = {}
for Dev in Devs:

	HD_Size  = findRawSize(Dev)
	HD_Model = findModel(Dev)
	HD_Capacity = HumanFriendlyBytes(HD_Size, 1000, 0)

	# Find out if the drive is SATA or SAS
	Drive_Transport[Dev] = "SATA"   # By default
	for line in SysExec("smartctl -x " + Dev).splitlines():

		# This line appears to be standard on SAS drives
		if re.search("Transport protocol", line) and re.search("SAS", line):
			Drive_Transport[Dev] = "SAS"
			break

		# Detect NVME flash drives
		if re.search(" NVM ", line):
			Drive_Transport[Dev] = "NVME"
			break

		# Used by the virtual disks exported by our LSI HBA's
		if re.search("Vendor:", line) and re.search("AVAGO", line):
			Drive_Transport[Dev] = "Virtual"
			break

	Debug("Drive transport for " + Dev + " is " + Drive_Transport[Dev])


# Start iterating over Devs and searching for errors
smart_attributes_headers = [ "id", "attribute_name", "flags", "value", "worst", "thresh", "fail", "raw_value" ]

for Dev in Devs:

	# Reset Boolean tests each loop
	dont_warn_smart_test = False
	smart_segment = False
	smart_log_errors_detected = False

	if Drive_Transport[Dev] == "SATA":

		# Pass 1:  SMART attribute values
		for line in SysExec("smartctl -x " + Dev).splitlines():

			line = line.strip() # Remove leading spaces

			# SMART attribute lines all start with numbers (after stripping leading spaces)
			if not re.search("^[0-9]", line):
				continue

			# ...but other unwanted lines also start with numbers, so filter them out
			if re.search("^0x", line):
				continue

			if re.search("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]", line):
				continue

			if re.search("Not_testing|Read_scanning", line):
				continue

			if re.search("% of test|%", line):
				continue

			if re.search("[0-9a-f][0-9a-f] [0-9a-f][0-9a-f] [0-9a-f][0-9a-f]", line):
				continue

			Debug("line = " + line)

			# At this point, the only thing left should be actual SMART attributes, so pluck them out
			smart_attributes = dict(zip(smart_attributes_headers, line.split()))
			Debug("Dev " + Dev + " smart_attributes = " + str(smart_attributes))


			if smart_attributes["thresh"] == "---":
				smart_attributes["thresh"] = "000"

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

			Delta = int(smart_attributes["value"]) - int(smart_attributes["thresh"])

			if Delta <= 0:
				printDev(Dev, "failing on SMART attribute " + smart_attributes["id"] + " " + smart_attributes["attribute_name"])

			if Delta < Smart_Attribute_Thresh and Delta > 0 and int(smart_attributes["thresh"]) < 50:
				printDev(Dev, "marginal on SMART attribute " + smart_attributes["id"] + " " + smart_attributes["attribute_name"])


		# Pass 2:  Scan smartctl output for "Self-test execution status:"
		out_array = enumerate(SysExec("smartctl -x " + Dev).splitlines())
		for i, line in out_array:
			if re.search("Self-test execution status:", line):
				msg = line.split(")")[1]
				msg_finished = False
				while not msg_finished:
					line = next(out_array)[1]
					if re.search("^[a-zA-Z]", line):
						msg_finished = True
						msg = ' '.join(msg.split())
					else:
						msg = msg + line

				Debug("Self-test execution status: " + msg)

				if re.search("The previous self-test completed having the read element of the test failed", msg):
					printDev(Dev, "failing a read-element test.")

				if re.search("The previous self-test completed having a test element that failed", msg):
					printDev(Dev, "failing a test-element test.")

		# Pass 3:  Scan smartctl output for other stuff
		for line in SysExec("smartctl -x " + Dev).splitlines():

			if re.search("^Error", line) and re.search("occurred at disk power-on lifetime", line) and not smart_log_errors_detected:
				printDev(Dev, "SMART log errors detected, see smartctl -x output for more info")
				smart_log_errors_detected = True

			if re.search("Short offline|Extended offline", line) and \
                           not re.search("Completed without error|Interrupted \(host reset\)|Self-test routine in progress", line) and \
                           not dont_warn_smart_test:
				printDev(Dev, "SMART test errors detected, see smartctl -x output for more info")
				dont_warn_smart_test = True

			if re.search("Number of Reallocated Logical Sectors", line):
				num_reallocated_logical_sectors = int(line.split()[3])
				if num_reallocated_logical_sectors != 0:
					printDev(Dev, "Number of Reallocated Logical Sectors = " + str(num_reallocated_logical_sectors))

			if re.search("Number of Mechanical Start Failures", line):
				num_mechanical_start_failures = int(line.split()[3])
				if num_mechanical_start_failures != 0:
					printDev(Dev, "Number of Mechanical Start Failures = " + str(num_mechanical_start_failures))

			if re.search("Number of Reported Uncorrectable Errors", line):
				num_reported_uncorrectable_errors = int(line.split()[3])
				if num_reported_uncorrectable_errors != 0:
					printDev(Dev, "Number of Reported Uncorrectable Errors = " + str(num_reported_uncorrectable_errors))

			if re.search("Number of Hardware Resets", line):
				num_hardware_resets = int(line.split()[3])
				if num_hardware_resets != 0:
					printDev(Dev, "Number of Hardware Resets = " + str(num_hardware_resets))

			if re.search("Number of ASR Events", line):
				num_asr_events = int(line.split()[3])
				if num_asr_events != 0:
					printDev(Dev, "Number of ASR Events = " + str(num_asr_events))

			if re.search("Number of Interface CRC Errors", line):
				num_interface_crc_errors = int(line.split()[3])
				if num_interface_crc_errors != 0:
					printDev(Dev, "Number of Interface CRC Errors = " + str(num_interface_crc_errors))

	elif Drive_Transport[Dev] == "SAS":

		Defects = 0
		Non_Medium_Errors = 0
		Smart_Failing_Cmd = 0

		for line in SysExec("smartctl -x " + Dev).splitlines():

			if re.search("^SMART Health Status:", line):
				smart_health_status = re.sub("^SMART Health Status:", "", line).strip()
				if smart_health_status != "OK":
					printDev(Dev, "non-OK smart status " + smart_health_status)

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

			if re.search("Failed in segment", line) and not smart_segment:
				printDev(Dev, "SMART test failed in segment errors")
				smart_segment = True

			if re.search("Invalid DWORD count = ", line):
				invalid_dword_count = int(line.split("=")[1].strip())
				if invalid_dword_count > 2:
					printDev(Dev, "Invalid DWORD count = " + str(invalid_dword_count))

			if re.search("Running disparity error count = ", line):
				running_disparity_error_count = int(line.split("=")[1].strip())
				if running_disparity_error_count > 2:
					printDev(Dev, "Running disparity error count = " + str(running_disparity_error_count))

			if re.search("Loss of DWORD synchronization = ", line):
				loss_of_dword_synchronization = int(line.split("=")[1].strip())
				if loss_of_dword_synchronization != 0:
					printDev(Dev, "Loss of DWORD synchronization = " + str(loss_of_dword_synchronization))

			if re.search("Phy reset problem = ", line):
				phy_reset_problem = int(line.split("=")[1].strip())
				if phy_reset_problem != 0:
					printDev(Dev, "Phy reset problem = " + str(phy_reset_problem))

