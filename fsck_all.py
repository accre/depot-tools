#!/usr/bin/env python

import os
import re
import sys
import stat
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

# By default, assume a parallel fsck unless specifically told serial.  Ignore this bit until later.


# Get a list of available rids
Rids = Generate_Rid_Dict()
#Rids = [ "3660" ]

logging.debug("Rids = " + str(Rids))

if __name__ == '__main__':
	jobs = []
	for This_Rid in Rids:
		logging.debug("Spawning defrag process on RID " + This_Rid)
		p = multiprocessing.Process(target = RID_Fsck, args=(This_Rid,))
		jobs.append(p)
		p.start()
