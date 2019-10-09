#!/usr/bin/env python3

import os
import re
import sys
import configparser

from ridlib import *

def Help_Set_Ini_Option():
	print("")
	print(sys.argv[0] + " - Set the Windows-style .ini config values for a file.")
	print("")
	print("USAGE:  " + sys.argv[0] + " <ini_file> <section> <key> <value>")
	print("")
	sys.exit(1)

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
	if re.search("pychecker", i):
		sys.argv.remove(i)

if len(sys.argv) != 5:
	Help_Set_Ini_Option()

File    = sys.argv[1]
Section = sys.argv[2]
Key     = sys.argv[3]
Value   = sys.argv[4]

# Should we do any sanity checking before calling?

Set_Ini_Option(File, Section, Key, Value)
