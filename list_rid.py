#!/usr/bin/env python3

"""
   Lists all mounted ibp resources
"""

import re
import os
import sys
import stat

from ridlib import *

def Help_RID_List():
	print("")
	print(sys.argv[0] + " - List all available RIDs")
	print("")
	print("USAGE:  " + sys.argv[0] + " [-rid-only]")
	print("")
	sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] != "-rid-only":
	Help_RID_List()

RID_List()
