#!/usr/bin/env python

import os
import sys
import re
import logging
import tempfile

from time import gmtime, strftime

from ridlib import *

def Help_RID_Unsequester():
	print("")
	print(sys.argv[0] + " -  Unsequesters a RID so it will be mounted automatically by other scripts.")
	print("")
	print("USAGE:  " + sys.argv[0] + " <Rid> \"<Comment>\"")
	print("")
	sys.exit(1)

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
        if re.search("pychecker", i):
                sys.argv.remove(i)

#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

logging.debug("len(sys.argv) = " + str(len(sys.argv)))
logging.debug("sys.argv = " + str(sys.argv))

if len(sys.argv) != 3:
	Help_RID_Unsequester()

Rid = sys.argv[1]
Msg = sys.argv[2]

# Make sure it's a valid rid
Dict_Rid_To_Dev = Generate_Rid_to_Dev_Dict()
if Rid not in Dict_Rid_To_Dev:
	logging.error("Rid " + Rid + " does not appear to be a valid Rid on this depot.")
	sys.exit(1)

# Then...
RID_Unsequester(Rid, Msg)
