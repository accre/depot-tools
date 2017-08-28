#!/usr/bin/env python

"""

Defrag all the Rids on a depot

"""

import os
import re
import sys
import logging
import multiprocessing

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
        if re.search("pychecker", i):
                sys.argv.remove(i)

        if re.search("time", i):
                sys.argv.remove(i)


# Define log directory and create it if it doesn't exist.
LogDir = "/var/log/defrag"

# Get a list of available rids
Depot_Dir = "/depot"
Rids = []
for Dir in os.listdir(Depot_Dir):
	if not re.search("^rid-", Dir):
		continue
	Rids.append(Dir.split("-")[1])

logging.debug("Rids = " + str(Rids))

if __name__ == '__main__':
	jobs = []
	for Rid in Rids:
		logging.debug("Spawning defrag process on RID " + Rid)
		p = multiprocessing.Process(target = RID_Defrag, args=(Rid, LogDir,))
		jobs.append(p)
		p.start()
