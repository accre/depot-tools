#!/usr/bin/env python

import os
import re
import sys
import time
import random
import socket
import logging
import multiprocessing

from subprocess import Popen, PIPE, STDOUT
from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
	if re.search("pychecker", i):
		sys.argv.remove(i)

	if re.search("time", i):
		sys.argv.remove(i)

# At some point, rather than computing the rids based on the hostname,
# I need to replace this with fetching a file from a master server with
# a list of rids that belong to this server based on the hostname.  As
# I don't have that yet...

# Number of drives per depot
NumDrives = 36

# What's the first RID in depot1 (1501)
StartDepot = 1
StartRid = 1501

# This depot
Depot = re.sub("cms-depot", "", socket.gethostname().split(".")[0])
Depot = "73" # Testing this on lio-demo, so cheat here
ThisStartRid = 1501 + 36*int(Depot) - StartDepot

# Generate Rid <-> Dev dicts
Rid_to_Dev_Dict = Generate_Rid_to_Dev_Dict()
#logging.debug("Rid_to_Dev_Dict = " + str(Rid_to_Dev_Dict))

# Get a list of all valid RIDs for this depot
ValidRids = []
for i in range(1, NumDrives+1):
	ValidRids.append(str(ThisStartRid + i - 1))
#logging.debug("ValidRids = " + str(ValidRids) + " and len = " + str(len(ValidRids)))

# Get a list of visible block devices without a Rid
Available_BD = []
for line in SysExec("lsblock").splitlines():

	line = " ".join(line.split())

	if not re.search("disk:hd", line):
		continue

	if re.search("NORID", line):
		logging.debug("Adding ridless " + line.split()[0] + " to Available_BD")
		Available_BD.append(line.split()[0])

# Also, add any existing block device which has a Rid outside the
# valid range for this depots (usually happens when we recycle a drive
# without wiping it first)
for Rid, Dev in Rid_to_Dev_Dict.iteritems():
	if Rid not in ValidRids:
		logging.debug("Adding outsider rid " + Dev + " to Available_BD")
		Available_BD.append(Dev)

# Get a list of all free Rids (ie, Rids that are valid and do not currently exist on the depot)
FreeRid = []

Dict = Rid_to_Dev_Dict.keys()
logging.debug("Dict = " + str(Dict))

for Rid in ValidRids:
	if not Rid in Dict:
		FreeRid.append(Rid)

logging.info("Free block devices = " + str(Available_BD))
logging.info("Free Rids = " + str(FreeRid))

# Debugging, delete when done
#Available_BD = ['/dev/sdb', '/dev/sdc' ]
#FreeRid =  ['4128', '4129' ]
#Available_BD = ['/dev/sdb' ]
#FreeRid =  ['4128' ]

def RID_Format(Rid, Dev):

	logging.info("Starting RID_Format on Rid " + Rid + " and Dev " + Dev)

	logging.debug("Creating Rid " + str(Rid) + " on Dev " + Dev)
	output = RID_Create(Rid, Dev, AssumeYes = True)
	logging.debug("Output = " + str(output))

	# The metadata will always be in depot_dir/rid-<RID>/md.  On imported systems
	# this is a symlink to /depot/import/md-<RID>.   On exported systems it's a
	# physical mount point

	configfile = depot_dir + "/rid-" + str(Rid) + "/md/rid.settings"
	logging.debug("configfile = " + configfile)

	if not os.path.isfile(configfile):
		print("ERROR:  Could not find config file for Rid " + Rid)
		return

	logging.debug("set_rid_option " + str(Rid) + " rid enable_chksum 1")
	output = Set_Ini_Option(configfile, "resource " + str(Rid), "enable_chksum", "1")
	logging.debug("Output = " + str(output))

	logging.debug("set_rid_option " + str(Rid) + " rid minfree_size 40960")
	output = Set_Ini_Option(configfile, "resource " + str(Rid), "minfree_size", "40960")
	logging.debug("Output = " + str(output))

	logging.debug("import_resource " + str(Rid))
	output = RID_Import(Rid, "/depot/import")
	logging.debug("Output = " + str(output))

	return


if __name__ == '__main__':
        jobs = []

	for Dev in Available_BD:

		if FreeRid:
			Rid = FreeRid.pop()

			logging.debug("Dev = " + Dev + " and Rid = " + str(Rid))

	                logging.info("Spawning format process on RID " + Rid)
	                p = multiprocessing.Process(target = RID_Format, args=(Rid,Dev,))
	                jobs.append(p)
	                p.start()

		else:
			logging.debug("DEBUG:  No more available Rids, but still available block devices!  Quitting.")
			sys.exit(1)

logging.debug("DEBUG:  merge_config")
output = SysExec("merge_config")
logging.debug("Output = " + output)

