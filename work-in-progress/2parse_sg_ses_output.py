#!/usr/bin/env python3

"""
Enumerate_Backplanes - create an easy-to-use table to reference backplanes
"""

import re
import os
import sys
import math
import time

from subprocess import Popen, PIPE, STDOUT
from prettytable import PrettyTable

# Enable/disable debugging messages
Print_Debug = False

# Cache info from SysExec
CacheDataArray = {}
CacheTimeArray = {}

def Debug(text):

        """
        A wrapper to print debugging info on a single line.
        """

        if Print_Debug:
                print("DEBUG: " + text)
        return()


def SysExec(cmd):

        """
        Run the given command and return the output
        """

        # Cache the output of the command for 20 seconds
        Cache_Expires = 20

        # Computed once, used twice
        Cache_Keys = list(CacheDataArray.keys())
        if cmd in Cache_Keys:
                Cache_Age  = time.time() - CacheTimeArray[cmd]
        else:
                Cache_Age  = 0

        Return_Val = "ERROR"

        # If we have valid data cached, return it
        if cmd in Cache_Keys and Cache_Age < Cache_Expires:
                Return_Val = CacheDataArray[cmd]

        # If the cmd is "cat", use fopen/fread/fclose to open it and
        # cache it as we go
        elif not cmd in Cache_Keys and cmd.split()[0] == "cat":
                f = open(cmd.split()[1], "r")
                CacheDataArray[cmd] = f.read()
                CacheTimeArray[cmd] = time.time()
                f.close()
                Return_Val = CacheDataArray[cmd]

        # If we don't have cached data, or it's too old, regenerate it
        elif not cmd in Cache_Keys or Cache_Age > Cache_Expires:
                CacheDataArray[cmd] = Popen(cmd.split(), stdout=PIPE, stderr=STDOUT).communicate()[0]
                CacheTimeArray[cmd] = time.time()
                Return_Val = CacheDataArray[cmd]

        if str(type(Return_Val)) == "<class 'bytes'>":
                Return_Val = Return_Val.decode("utf-8")

        return(Return_Val)


def List_Enclosures():
	"""
        List the available enclosures on this server
	"""

	enclosures_list_cmd = SysExec("lsscsi -g")
	enclosures = []
	for line in enclosures_list_cmd.splitlines():
		if not re.search("enclosu", line):
			continue
		if re.search("VirtualSES", line):
			continue

		enclosures.append(line.split(" ")[-1])

	Debug("List_Enclosures:: enclosures = " + str(enclosures))

	return(enclosures)


def List_Slots(e):
	"""
	List the available slots on this enclosure
	"""
	### Get the number of slots for this enclosure
	slots_list_cmd = SysExec("sg_ses --page=aes " + e)
	slots = []
	for l in slots_list_cmd.splitlines():
		if not re.search("Element index: ", l):
			continue
		slots.append(l.split(":")[1].strip().split(" ")[0])

	Debug("List_Slots:: slots for enclosure " + e + " = " + str(slots))

	return(slots)


# Blank dictionary to hold parsed output from the "sg_ses" command
sg_ses_dict = {}

# Iterate over all enclosures...
enclosures = List_Enclosures()
for e in enclosures:

	# Blank dictionary for this enclosure
	sg_ses_dict[e] = {}

	slots = List_Slots(e)

	for s in slots:

		sg_ses_dict[e][s] = {}
		sg_ses_dict[e][s]["enclosure"] = e
		sg_ses_dict[e][s]["slot"]      = s

		# Parse the "aes" page
		sg_ses_output = SysExec("sg_ses -p aes --index=" + s + " " + e)
		sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()
		for line in sg_ses_output.splitlines():
			line = ' '.join(line.split()).strip()
			if re.search("target port for:", line):
				if re.search("SSP", line):
					sg_ses_dict[e][s]["media_type"] = "SAS"
				elif re.search("SATA_device", line):
					sg_ses_dict[e][s]["media_type"] = "SATA"
				else:
					sg_ses_dict[e][s]["media_type"] = "UNKNOWN"
			if re.search("SAS address:", line) and not re.search("attached SAS address", line):
					sg_ses_dict[e][s]["media_wwn"] = line.split(":")[1].strip()

		# Parse the "ed" page
		sg_ses_output = SysExec("sg_ses -p ed --index=" + s + " " + e)
		sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()
		for line in sg_ses_output.splitlines():
			line = ' '.join(line.split()).strip()
			if re.search("Element " + str(s) + " descriptor:", line):
				sg_ses_dict[e][s]["descriptor"] = line.split(":")[1].strip()

		# Parse the "ec" page
		sg_ses_output = SysExec("sg_ses -p ec --index=" + s + " " + e)
		sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()
		for line in sg_ses_output.splitlines():
			line = ' '.join(line.split()).strip()

			# Rather than writing a thousand rules, just parse anything that looks like "foo=bar" as a key/value pair
			if re.search("=", line):

				tmp_line = line.lower()
				tmp_line = re.sub("/", "_", tmp_line)
				tmp_line = re.sub(" ", "_", tmp_line)

				key = "s_" + tmp_line.split("=")[0].strip()
				val =        tmp_line.split("=")[1].strip()

				if val == "0":
					val = ""

				sg_ses_dict[e][s][key] = val



#			if re.search("enclosure logical identifier", line):
#				sg_ses_dict[e][s]["enclosure_logical_identifier"] = line.split(" ")[-1]

#			if re.search("enclosure vendor", line):
#				sg_ses_dict[e][s]["enclosure_vendor"]  = line.split(":")[1].rsplit(' ', 1)[0].strip()
#				sg_ses_dict[e][s]["enclosure_product"] = line.split(":")[2].rsplit(' ', 1)[0].strip()
#				sg_ses_dict[e][s]["enclosure_rev"]     = line.split(":")[3].strip()



Debug("sg_ses_dict = " + str(sg_ses_dict))

# Get the list of column names for PrettyTable
col = sg_ses_dict[enclosures[0]][slots[0]].keys()

Debug("col = " + str(col))

x = PrettyTable(col)
x.padding_width = 1
for e in sg_ses_dict:
	for s in sg_ses_dict[e]:
		x.add_row(sg_ses_dict[e][s].values())
print(x)
