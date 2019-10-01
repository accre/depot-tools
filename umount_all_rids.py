#!/usr/bin/env python

"""
	"umount_all_rids.py" will mount all umounted rids
"""
import psutil
import os
import re
import sys
import stat
import logging
import tempfile
import time
import multiprocessing

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
	if re.search("pychecker", i):
		sys.argv.remove(i)

	if re.search("time", i):
		sys.argv.remove(i)

def Help_RID_Umount_All():
	print("")
	print(sys.argv[0] + " - Umount all mounted Rids")
	print("")
	print("Usage:  " + sys.argv[0])
	print("")
	sys.exit(0)

# Get a list of available rids
Rids = Generate_Rid_Dict()

logging.debug("Rids = " + str(Rids))

if __name__ == '__main__':
	jobs = []
	for This_Rid in Rids:
		logging.debug("Spawning mount process on RID " + This_Rid)
		p = multiprocessing.Process(target = RID_Umount, args=(This_Rid,))
		jobs.append(p)
		p.start()
