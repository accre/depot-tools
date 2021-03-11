#!/usr/bin/env python3

"""
Create and format a RID
"""

import os
import re
import sys
import math
import stat
import logging

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

def Help_RID_Create():
	print("")
	print(sys.argv[0] + " - Create and format a RID")
	print("")
	print("USAGE:  " + sys.argv[0] + " <Rid> <dev>")
	print("")
	sys.exit(1)


depot_dir = "/depot" # From . depot_common

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
        if re.search("pychecker", i):
                sys.argv.remove(i)

        if re.search("time", i):
                sys.argv.remove(i)


if len(sys.argv) != 3:
	Help_RID_Create()

Rid = sys.argv[1]
Dev = sys.argv[2]

RID_Create(Rid, Dev, AssumeYes = True)

