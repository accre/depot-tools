#!/usr/bin/env python3

import os
import sys
import re
import logging
import tempfile

from time import gmtime, strftime

from ridlib import *

#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

def Help_RID_Check_Sequester():
	print("")
	print(sys.argv[0] + " - Returns the current sequester status of a Rid")
	print("")
	print("USAGE:  " + sys.argv[0] + " <Rid>")
	print("")
	sys.exit(1)

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
        if re.search("pychecker", i):
                sys.argv.remove(i)

logging.debug("len(sys.argv) = " + str(len(sys.argv)))
logging.debug("sys.argv = " + str(sys.argv))

if len(sys.argv) != 2:
	Help_RID_Check_Sequester()

Rid = sys.argv[1]

# Make sure it's a valid rid
Dict_Rid_To_Dev = Generate_Rid_to_Dev_Dict()
if Rid not in Dict_Rid_To_Dev:
	logging.error("Rid " + Rid + " does not appear to be a valid Rid on this depot.")
	sys.exit(1)

# Then...
print(RID_Check_Sequester(Rid))
