#!/usr/bin/env python

"""
        Export a resource's metadata back to the data drive
"""

import os
import sys
import re
import stat
import shutil
import logging

from ridlib import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

depot_dir = "/depot"
md_dir = depot_dir + "/import"

def Help_RID_Export():
	print("")
	print(sys.argv[0] + " - Export the Rid metadata from the local SSD back to the data drive")
	print("")
	print("Usage:  " + sys.argv[0] + " <Rid>")
	print("")
	sys.exit(1)

if len(sys.argv) != 2:
	Help_RID_Export()

Rid = sys.argv[1]

if len (sys.argv) == 3:
	md_dir = sys.argv[2]
else:
	md_dir = depot_dir + "/import"

#logging.info("Rid = " + Rid + " and md_dir = " + md_dir)

RID_Export(Rid, md_dir)
