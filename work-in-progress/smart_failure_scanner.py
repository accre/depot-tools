#!/usr/bin/env python3

import os
import re
import sys
import time
import math
import threading

from subprocess import Popen, PIPE, STDOUT, call, check_output
from time import gmtime, strftime, sleep

# Arrays for SysExec caching
CacheDataArray = {}
CacheTimeArray = {}

# Set "True" to print debugging info
Print_Debug = True

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

#        Debug("SysExec():: cmd = '" + cmd + "'")

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
#                Debug("Returning cmd from cache:  " + cmd)
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

	return str(scaled_size) + " " + scaled_units


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

def findModel(SD_Device):

	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/model"
	f = open(file, "r")
	model = f.read()
	f.close()

	return model

def findVendor(SD_Device):

	file = "/sys/block/" + SD_Device.split("/")[-1] + "/device/vendor"
	f = open(file, "r")
	vendor = f.read()
	f.close()

	return vendor


################################################################################
# Main()::
################################################################################

# Get a list of block devices
Devs = []
Output = os.listdir("/sys/block")
for line in Output:

	# Skip various non-block devices
	if re.search("^loop|^ram|^dm|^zram", line):
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

	if Drive_Transport[Dev] == "SATA":

		# Pass 1:  SMART attribute values
		for line in SysExec("smartctl -x " + Dev).splitlines():

			line = line.strip() # Remove leading spaces

#			Debug("Dev " + Dev + " " + line)

			# SMART attribute lines all start with numbers (after stripping leading spaces)
			if not re.search("^[0-9]", line):
				continue

			# ...but other unwanted lines also start with numbers, so filter them out
			if re.search("^0x", line):
				continue

			if re.search("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]", line):
				continue

			if re.search("Not_testing", line):
				continue

			if re.search("% of test", line):
				continue

			if re.search("[0-9a-f][0-9a-f] [0-9a-f][0-9a-f] [0-9a-f][0-9a-f]", line):
				continue

			# At this point, the only thing left should be actual SMART attributes, so pluck them out
			smart_attributes = dict(zip(smart_attributes_headers, line.split()))

#			Debug("Dev " + Dev + " smart_attributes = " + str(smart_attributes))

			# This is a corner case where value, worst and thresh are all 0.  Just ignore
			if smart_attributes["value"] == 0 and smart_attributes["worst"] == 0 and smart_attributes["thresh"] == 0:
				# There's no good way to know if the drive is actually failing, or if this test is screwy.  Just skip.
				continue

			# One Intel SSD has a buggy 233 Media_Wearout_Indicator, so ignore that special case
			if smart_attributes["id"] == "233" and findModel(Dev) == "SSDSA2M040G2GC":
				continue

			# Now test for bad drives

			# This is a drive with a large number of failed sectors that isn't yet failing SMART
			Thresh_197 = 500
			if smart_attributes["id"] == "197":
				if int(smart_attributes["value"]) > Thresh_197:
					print("Dev " + Dev + " has a 197 Current_Pending_Sector value over " + Thresh_197)

			Delta = int(smart_attributes["value"]) - int(smart_attributes["thresh"])

			if Delta <= 0:
				print("Dev " + Dev + " is failing on SMART attribute " + smart_attributes["id"] + " " + smart_attributes["attribute_name"])

			if Delta < 10 and Delta > 0 and int(smart_attributes["thresh"]) < 50:
				print("Dev " + Dev + " is marginal on SMART attribute " + smart_attributes["id"] + " " + smart_attributes["attribute_name"])

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
					print("Dev " + Dev + " is failing a read-element test.")

				if re.search("The previous self-test completed having a test element that failed", msg):
					print("Dev " + Dev + " is failing a test-element test.")


#	elif Drive_Transport[Dev] == "SAS":
#		Defects=`smart_attributes ${dev} | grep 9000_SAS_Grown_Defect_List | awk '{ print $2 }'`
#
#		if [ -n "${Defects}" ]; then
#
#			if [ "${Defects}" -gt "0" ]; then
#
#				if [ "${Defects}" -gt "50" ]; then
#					printf "Dev %-9s Rid ${rid} has a critically-high number of defects (${Defects} defects)\n" ${dev}
#				else
#					printf "Dev %-9s Rid ${rid} has a non-zero number of defects (${Defects} defects)\n" ${dev}
#				fi
#			fi
#		fi
#
#	fi
#done
#
#rm -f ${attr} ${lsslot} ${lsblock} ${blkid}
