#!/usr/bin/env python

"""
	Import a resource's metadata from the data drive to local SSD
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

def Help_RID_Import():
	print("")
	print(sys.argv[0] + " - Import the Rid metadata to local SSD")
	print("")
	print("Usage:  " + sys.argv[0] + " <Rid> [MD_Dev]")
	print("")
	sys.exit(1)

if len(sys.argv) < 2 or len(sys.argv) > 3:
	Help_RID_Import()

Rid = sys.argv[1]

if len (sys.argv) == 3:
	md_dir = sys.argv[2]
else:
	md_dir = depot_dir + "/import"

logging.debug("Rid = " + Rid + " and md_dir = " + md_dir)

RID_Import(Rid, md_dir)
