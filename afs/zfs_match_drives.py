#!/usr/bin/env python3

###
### List all ZFS drives, aliases, etc.   Initial conversion of BASH script
###

import re
import os
import sys
import math
import time

from prettytable import PrettyTable

### Note:  Any time you can avoid using Popen is a huge win time-wise
from subprocess import Popen, PIPE, STDOUT

CacheDataArray = {}
CacheTimeArray = {}

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


#ls -alh /dev/disk/by-path/ | grep sas | grep -v part | rev | cut -d " " -f 3,1 | rev
### Get a list of paired /dev entries on servers with multipathing
#multipath_dev = []
#for line in SysExec("ls -alh /dev/disk/by-path")
sn_to_dev = {}
dev_to_sn = {}
for line in SysExec("lsblk -S -o SERIAL,NAME,ROTA").splitlines():

	if not re.search("1$", line):
		continue

	line = " ".join(line.split())
	sn  = line.split()[0]
	dev = line.split()[1]

	if not sn in sn_to_dev:
		sn_to_dev[sn] = []

	if not dev in dev_to_sn:
		dev_to_sn[dev] = []

	sn_to_dev[sn].append(dev)
	dev_to_sn[dev].append(sn)


### Get a list of "zpool" online drives
zpool_online = []
for line in SysExec("zpool status -P").splitlines():

	if not re.search("/dev/", line):
		continue

	if not re.search("ONLINE", line):
		continue

	line = " ".join(line.split())

	zdev = line.split()[0]
	zdev = zdev.split("/")[-1]
	zdev = re.sub("-part[0-9]*$", "", zdev)

	zpool_online.append(zdev)


### Get a list of "scsi-" style paths
dev_to_scsi = {}
for line in SysExec("ls -alh /dev/disk/by-id").splitlines():

	scsi = ""
	dev = ""

	if not re.search("scsi-[0-9]", line):
		continue

	if re.search("part[0-9]", line):
		continue

	line = " ".join(line.split())

	for i in line.split():

		if re.search("scsi", i):
			scsi = i

		if re.search("../../", i):
			dev = i.split("/")[2]

	if scsi and dev:
		dev_to_scsi[dev] = scsi
		scsi = ""
		dev = ""


### Get a list of "wwn-" style paths
dev_to_wwn = {}
for line in SysExec("ls -alh /dev/disk/by-id").splitlines():

	wwn = ""
	dev = ""

	if not re.search("wwn", line):
		continue

	if re.search("part[0-9]", line):
		continue

	line = " ".join(line.split())

	for i in line.split():

		if re.search("wwn", i):
			wwn = i

		if re.search("../../", i):
			dev = i.split("/")[2]

	if wwn and dev:
		dev_to_wwn[dev] = wwn
		wwn = ""
		dev = ""


# Get a list of "path-" style paths
dev_to_pci = {}
for line in SysExec("ls -alh /dev/disk/by-path").splitlines():

	pci = ""
	dev = ""
	phy = ""

	if not re.search("pci", line):
		continue

	if re.search("part[0-9]", line):
		continue

	line = " ".join(line.split())

	for i in line.split():

		if re.search("pci", i):
			pci = i

		if re.search("../../", i):
			dev = i.split("/")[2]

	if pci and dev:
		dev_to_pci[dev] = pci
		pci = ""
		dev = ""


### Get a list of ZFS name to wwn/pci path
path_to_zfs = {}
for line in SysExec("cat /etc/zfs/vdev_id.conf").splitlines():

	# Remove any comments at the end of the line
	line = line.split("#")[0]
	line = " ".join(line.split())

	if not re.search("^alias", line):
		continue

	zfs = line.split()[1]
	path = line.split()[2].split("/")[-1]

	path_to_zfs[path] = zfs


### Get a list of all devs with wwn/pci paths
all_devs = list(set(dev_to_wwn.keys()).union(set(dev_to_pci.keys())))

### Iterate over data once, matching up multipathed drives if they exist.
### This will sometimes leave some holes, which we will with a 2nd iteration
output = {}
for dev in all_devs:

	# See if it's an SSD.   At the moment, ZFS data drives are hard drives,
	# so it's a simple filter to avoid printing the OS drive
	rota = SysExec("cat /sys/block/" + str(dev) + "/queue/rotational")
	if int(rota) == 0:
		continue

	output[dev] = {}

	scsi    = "<NONE>"
	wwn     = "<NONE>"
	pci     = "<NONE>"
	zfs     = "<NONE>"
	online  = "No"
	dev_alt = "[]"

	# Fetch map of Serial Number to /dev/
	sn = dev_to_sn[dev][0]

	# If the SN was found, check for the presence of multipath drives.
	if sn in sn_to_dev:
		dev_alt = sn_to_dev[sn]
	output[dev]["dev_alt"] = dev_alt

	# Filter out the current dev from dev_alt
	dev_alt_short = [s for s in dev_alt if dev not in s]

	# Fetch "scsi" from the current drive or, if it exists, another multipath drive alias
	if dev in dev_to_scsi:
		scsi = dev_to_scsi[dev]
	elif dev_alt and scsi == "<NONE>":
		for dev_a in dev_alt_short:
			if dev_a in dev_to_scsi:
				scsi = dev_to_scsi[dev_a]
				break
	output[dev]["scsi"] = scsi

	# Fetch "wwn" from the current drive or, if it exists, another multipath drive alias
	if dev in dev_to_wwn:
		wwn = dev_to_wwn[dev]
	elif dev_alt and wwn == "<NONE>":
		for dev_a in dev_alt_short:
			if dev_a in dev_to_wwn:
				wwn = dev_to_wwn[dev_a]
				break
	output[dev]["wwn"] = wwn

	# Fetch "pci" from the current drive or, if it exists, another multipath drive alias
	if dev in dev_to_pci:
		pci = dev_to_pci[dev]
	elif dev_alt and pci == "<NONE>":
		for dev_a in dev_alt_short:
			if dev_a in dev_to_pci:
				pci = dev_to_pci[dev_a]
				break
	output[dev]["pci"] = pci

	if wwn in path_to_zfs:
		zfs = path_to_zfs[wwn]

	if pci in path_to_zfs:
		zfs = path_to_zfs[pci]

	if scsi in path_to_zfs:
		zfs = path_to_zfs[scsi]

	output[dev]["zfs"] = zfs

	if scsi in zpool_online or wwn in zpool_online or pci in zpool_online or zfs in zpool_online:
		online = "Yes"

	output[dev]["online"] = online

### 2nd iteration to fill in any gaps
for dev in output:

	scsi    = output[dev]["scsi"]
	wwn     = output[dev]["wwn"]
	pci     = output[dev]["pci"]
	zfs     = output[dev]["zfs"]
	online  = output[dev]["online"]
	dev_alt = output[dev]["dev_alt"]

	dev_alt_short = [s for s in dev_alt if dev not in s]

	if scsi == "<NONE>" and dev_alt_short:
		for dev_a in dev_alt_short:
			if dev_a in dev_to_scsi and dev_to_scsi[dev_a] != "<NONE>":
				output[dev]["scsi"] = dev_to_scsi[dev_a]

	if wwn == "<NONE>" and dev_alt_short:
		for dev_a in dev_alt_short:
			if dev_a in dev_to_wwn and dev_to_wwn[dev_a] != "<NONE>":
				output[dev]["wwn"] = dev_to_wwn[dev_a]

	if pci == "<NONE>" and dev_alt_short:
		for dev_a in dev_alt_short:
			if dev_a in dev_to_pci and dev_to_pci[dev_a] != "<NONE>":
				output[dev]["pci"] = dev_to_pci[dev_a]

	if zfs == "<NONE>" and dev_alt_short:
		for dev_a in dev_alt_short:
			if dev_a in output:
				if "zfs" in output[dev_a] and output[dev_a]["zfs"] != "<NONE>":
					output[dev]["zfs"] = output[dev_a]["zfs"]

	if online == "No" and dev_alt_short:
		for dev_a in dev_alt_short:
			if dev_a in output:
				if "online" in output[dev_a] and output[dev_a]["online"] != "No":
					output[dev]["online"] = output[dev_a]["online"]

### Fetch the info and assemble a table for later prettyprinting
labels = [ "Dev", "VDev", "WWN_Path", "SCSI_PATH", "PCI_PATH", "ONLINE" ]
table = PrettyTable(labels)
drives_printed = []
for dev in output:

	# If we've already printed this drive, continue
	if dev in drives_printed:
		continue

	if sn in sn_to_dev:
		dev_alt = sn_to_dev[sn]

	scsi    = output[dev]["scsi"]
	wwn     = output[dev]["wwn"]
	pci     = output[dev]["pci"]
	zfs     = output[dev]["zfs"]
	online  = output[dev]["online"]
	dev_alt = output[dev]["dev_alt"]

	drives_printed.extend(dev_alt)

	dev_alt = ",".join(dev_alt)

	table.add_row( [dev_alt, zfs, wwn, scsi, pci, online] )

print(table.get_string(sortby="Dev"))
