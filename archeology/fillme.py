#!/usr/bin/env python

import os
import re
import sys
import stat
import logging
import signal
import multiprocessing

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')


def Help_RID_Fillup():
        print("")
        print(sys.argv[0] + " - Repeatedly fill up a drive (used for burn-in).")
        print("")
        print("USAGE:  " + sys.argv[0] + " <RID>")
        print("")
        sys.exit(1)


def Exit_Gracefully(signal, frame):

	print("CTRL-C captured, trying to exit cleanly...")

	for f in os.listdir("/tmp/"):

		if not re.search("fillme-", f):
			continue

		lf = "/tmp/" + f

		print("DEBUG:  lockfile = " + lf)

		if os.path.isfile(lf):
			os.remove(lf)

	sys.exit(0)


def Dev_Mountpoints(Dev):

	"""
		Return a list of current mountpoints used by Dev.  As Lstore only uses
		partitions 1/2, only focus on those two.
	"""

	Dev_Mnts = []

	for line in SysExec("mount").splitlines():

		if not re.search(Dev + "1", line) and not re.search(Dev + "2", line):
			continue

		line = ' '.join(line.split())
		Dev_Mnts.append(line.split()[2])

	return Dev_Mnts


def RID_Fillup(Rid):

	Rid_to_Dev = Generate_Rid_to_Dev_Dict()

	# Does Rid exist?
	if not Rid in Rid_to_Dev:
		logging.error("Could not locate Rid " + Rid + " on this server.")
		sys.exit(1)

	Lockfile = "/tmp/fillme-lockfile." + Rid

	# If we've already running an instance, put this to sleep until it goes away
	while os.path.isfile(Lockfile):
		logging.debug("Sleeping 15 seconds because lockfile exists")
		time.sleep(15)

	# Lock it.
	logging.debug("Touching lockfile " + Lockfile)
	touch(Lockfile)

	# Is Rid mounted?  If not, mount it
	if not is_rid_mounted(Rid):
		logging.info("Rid " + Rid + " not mounted.   Attempting to mount...")
		RID_Mount(Rid)

	# We want to find the Dev_Mount point
	Dev = Rid_to_Dev[Rid]
	Dev_Mnts = Dev_Mountpoints(Dev)
	logging.debug("len(Dev_Mnts) = " + str(len(Dev_Mnts)))

	if len(Dev_Mnts) == 1:
		Dev_Mnt = Dev_Mnts[0]
	else:
		Dev_Mnt = Dev_Mnts[-1]
	logging.debug("Dev_Mnt = " + Dev_Mnt)

	# This is the mount of free space on the drive in units of 1K
	Space_Free = "Unknown"
	for line in SysExec("df").splitlines():

		if not re.search(Dev + "2", line):
			continue

		Space_Free = ' '.join(line.split())
		Space_Free = Space_Free.split()[3]
		logging.debug("Space_Free = " + Space_Free)

	# Determine the number of 1 GB files we need to create to fill the drive
	NF = (int(Space_Free) / (1024*1024)) + 1
	logging.info("Creating " + str(NF) + " files of 1 GB to fill free space of " + Space_Free + " on " + Rid)

	# Now create the files
	for i in range(1, NF):
		dd_cmd = "dd if=/dev/zero of=" + Dev_Mnt + "/fillme-testfile." + str(i) + " bs=1M count=1024 status=none"
		logging.debug("Executing cmd: " + dd_cmd)
		subprocess.call(dd_cmd.split())

	# Clean up the files
	for i in range(1, NF):
		testfile = Dev_Mnt + "/fillme-testfile." + str(i)
		if os.path.isfile(testfile):
			os.remove(testfile)

	# Erase the lockfile
	if os.path.isfile(Lockfile):
		os.remove(Lockfile)

"""
	Main Program
"""

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
	if re.search("pychecker", i):
		sys.argv.remove(i)

	if re.search("time", i):
		sys.argv.remove(i)

if len(sys.argv) != 1:
        Help_RID_Fillup()

Rid_Dict = Generate_Rid_Dict()

if __name__ == '__main__':
	signal.signal(signal.SIGINT, Exit_Gracefully)
	jobs = []
	for This_Rid in Rid_Dict:
		logging.debug("Spawning defrag process on RID " + This_Rid)
		p = multiprocessing.Process(target = RID_Fillup, args=(This_Rid,))
		jobs.append(p)
		p.start()
