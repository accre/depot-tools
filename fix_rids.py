#!/usr/bin/env python

import os
import re
import sys
import time
import socket

from ridlib import *

"""

Determine if any RIDS have bounced, blipped, or otherwise vanished.

It does this by looking at three quantities:

* Num_NS  = number of rids the depot is supposed to have according to /etc/number_of_storage_drives
* Num_IBP = number of rids visible to ibp_server
* Num_BLK = number of rids according to /sys/block

Complain if there is a discrepancy.

"""

def RID_Detach(Rid, Hostname, Port = "6714", Msg = "Detaching Rid"):
	SysExec("ibp_detach_rid " + Hostname + " " + Port + " " + Rid + " 1 " + Msg)

def RID_Attach(Rid, Hostname, Port = "6714", Msg = "Attaching Rid"):
	SysExec("ibp_attach_rid " + Hostname + " " + Port + " " + Rid + " " + Msg)

Num_NS = int(SysExec("cat /etc/number_of_storage_drives"))

# Get a list of RIDs attached to the IBP Server daemon
IBP_Rids = []
Count_Pending = 0

for line in SysExec("get_version -a").splitlines():

	if re.search("^RID: ", line):
		IBP_Rids.append(line.split(" ")[1])

	if re.search("Pending RID count", line):

		Rids = line.split(":")[1].strip().split(" ")

		if Rids[0] == "0":
			continue

		for Rid in Rids:
			IBP_Rids.append(int(Rid))
			Count_Pending += 1
IBP_Rids.sort()
Num_IBP = len(IBP_Rids)


# Get a list of RIDs visible to the OS via /sys/block
OS_Rids = []
LS = os.listdir("/dev/disk/by-label/")
for disk in LS:

	if not re.search("rid-data", disk):
		continue

	OS_Rids.append(disk.split("-")[2])
OS_Rids.sort()
Num_BLK = len(OS_Rids)

# See if there descrepancies between OS and IBP Server
Diff_Rids = list(set(OS_Rids) - set(IBP_Rids))

# If so, see if they are sequestered
Count_Seq = 0
if Diff_Rids:
	for Rid in Diff_Rids:
		Status = RID_Check_Sequester(Rid)
		if Status.startswith("SEQUESTERED"):
			Count_Seq += 1
			Diff_Rids.remove(Rid)

if Num_NS == Num_IBP and Num_NS == Num_BLK:

	if Count_Pending == 0:
		print("All Drives = " + str(Num_NS))
	else:
		print("All Drives = " + str(Num_NS) + " (including " + str(Count_Seq) + " sequestered drives)")

else:
	if Diff_Rids:

		Hostname = socket.gethostname()

		for rid in Diff_Rids:

			print("DEBUG:  Running fix_rid on Rid " + rid)

			if not partition_exists("/dev/disk/by-label/rid-data-" + rid):
#			if not os.path.isfile("/dev/disk/by-label/rid-data-" + rid):
				print("")
				print("ERROR:  Cannot find Rid " + rid + ".  Please make sure it is visible to the OS.")
				print("        The server may require a reboot if the drive has vanished.")
				print("")
				sys.exit(1)

			if is_rid_attached_to_ibpserver(rid):
				print("DEBUG:  Rid " + rid + " is attached to running IBP server.  Detaching rid...")
				RID_Detach(rid, Hostname)

			if is_rid_mounted(rid):
				print("DEBUG:  Rid " + rid + " is currently mounted.  Unmounting...")
				RID_Umount(rid)

			print("DEBUG:  Conducting fsck on Rid " + rid + "...")
			RID_Fsck(rid)

			print("DEBUG:  Mounting Rid " + rid + "...")
			RID_Mount(rid)

			print("DEBUG:  Readding rid to running IBP server...")
			RID_Merge_Config()
			RID_Attach(rid, Hostname)
