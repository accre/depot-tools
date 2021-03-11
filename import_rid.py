#!/usr/bin/env python3

"""
	Import a resource's metadata from the data drive to local SSD
"""

import os
import sys
import re
import stat
import shutil
import logging
import argparse

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

depot_dir = "/depot"
md_dir = depot_dir + "/import"

parser = argparse.ArgumentParser(description = ' - Import the Rid metadata from the data disk to the local SSD')

parser.add_argument('--snap', help='Import snapshot metadata rather than whole metadata', action='store_true')
parser.add_argument('rid',    metavar = 'rid', type=ascii, help='The RID you want to import')
parser.add_argument('--md_dir', metavar = '<md_dir>', type=ascii, help='The path to the metadata directory', default = md_dir)

args = parser.parse_args()

snap   = args.snap
rid    = re.sub("'", "", args.rid)
md_dir = re.sub("'", "", args.md_dir)

logging.debug("import_rid.py::  rid = " + rid + " and md_dir = " + md_dir + " and snap = " + str(snap))

RID_Import(rid, md_dir, Snap = snap)
