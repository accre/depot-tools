#!/usr/bin/env python3

"""
	"mount_resource.py <rid>" will mount rid <rid>
"""

import psutil
import re
import os
import sys
import logging
import tempfile
import time

from ridlib import *

def Help_RID_Mount():
	print("")
	print(sys.argv[0] + " - Mount a given rid")
	print("")
	print("Usage:  " + sys.argv[0] + " <rid>")
	print("")
	sys.exit(0)

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
	if re.search("pychecker", i):
		sys.argv.remove(i)

if len(sys.argv) < 2:
	Help_RID_Mount()

RID_Mount(sys.argv[1])
