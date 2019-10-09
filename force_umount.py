#!/usr/bin/env python3

import sys
import os
import re

from ridlib import SysExec, remove_obj

# If I'm running under pychecker, remove it from sys.argv so it will work normally
for i in sys.argv:
        if re.search("pychecker", i):
                sys.argv.remove(i)

if len(sys.argv) < 2:
	print("force_umount.py - Clean up a rids mountpoints after a failed unmount.")
	print("Usage:  force_umount.py <rid>")
	sys.exit(0)

rid = sys.argv[1]

# Use "lsof" to seeSee if lsof sees any files on this rid being used.   If so, fail.
lsof_md = SysExec("lsof /depot/import/md-" + str(Rid))
lsof_data = SysExec("lsof /depot/rid-" + str(Rid) + "/data")
if len(lsof_md) > 0 or len(lsof_data) > 0:
	logging.error("Can't umount RID.  Appears to be in use according to 'lsof'!")
	sys.exit(1)

remove_obj("/depot/rid-" + rid + "/data")
remove_obj("/depot/rid-" + rid + "/md")
remove_obj("/depot/rid-" + rid + "/rid.info")
remove_obj("/depot/rid-" + rid)

