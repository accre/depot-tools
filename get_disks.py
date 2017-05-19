#!/usr/bin/env python

import os
import re
import sys

List = []

for file in os.listdir("/dev/disk/by-label"):
	if re.search("rid-data", file):
		dev = os.readlink("/dev/disk/by-label/" + file)
		dev = dev.split("/")[-1]

		dev = re.sub("1$", "", dev)
		dev = re.sub("2$", "", dev)

		List.append("/dev/" + dev)
List.sort()

for dev in List:
	print(dev)
