#!/usr/bin/env python3

import os
import re
import sys
import logging

from ridlib import *

def Help_Query_Drives_Smart_Attributes():
	print("")
	print(sys.argv[0] + " - Query a SMART attribute on all drives in the depot.")
	print("")
	print("USAGE:  " + sys.argv[0] + " [Smart ID# or Attribute Name]")
	print("")
	print("Example:  " + sys.argv[0] + " 5                # Will return 5 Reallocated_Sector_Ct")
	print("          " + sys.argv[0] + " Start_Stop_Count # Will return 4 Start_Stop_Count")
	print("")
	sys.exit(1)

if len(sys.argv) != 2:
	Help_Query_Drives_Smart_Attributes()

Query = sys.argv[1]

Output_Dict = Query_Drives_Smart_Attributes(Query)

if Output_Dict:
	Print_Query_Drives_Smart_Attributes(Output_Dict)
