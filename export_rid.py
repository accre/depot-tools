#!/usr/bin/env python3

"""
        Export a resource's metadata back to the data drive
"""

import os
import sys
import re
import stat
import shutil
import logging
import argparse

from ridlib import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

depot_dir = "/depot"
md_dir = depot_dir + "/import"

parser = argparse.ArgumentParser(description=' - Export the Rid metadata from the local SSD back to the data drive')

parser.add_argument('--snap', help='Export snapshot metadata rather than whole metadata', action='store_true')
parser.add_argument('rid',    metavar = 'rid', type=ascii, help='The RID you want to export')
parser.add_argument('--md_dir', metavar = '<md_dir>', type=ascii, help='The path to the metadata directory', default = md_dir)

args = parser.parse_args()

snap   = args.snap
rid    = re.sub("'", "", args.rid)
md_dir = re.sub("'", "", args.md_dir)

logging.debug("export_rid.py::  rid = " + rid + " and md_dir = " + md_dir + " and snap = " + str(snap))

RID_Export(rid, md_dir, Snap = snap)
