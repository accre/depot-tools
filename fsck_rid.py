#!/usr/bin/env python3

"""
   Fsck a given RID
"""

import os
import re
import sys
import stat

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

def Help_RID_Fsck():
	print("")
	print(sys.argv[0] + " - fsck all partitions belonging to a given rid.")
	print("")
	print("USAGE:  " + sys.argv[0] + " <RID>")
	print("")
	sys.exit(1)

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
	if re.search("pychecker", i):
		sys.argv.remove(i)

	if re.search("time", i):
		sys.argv.remove(i)

if len(sys.argv) != 2:
	Help_RID_Fsck()

Rid = sys.argv[1]

RID_Fsck(Rid)
