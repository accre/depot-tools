#!/usr/bin/env python3

"""
Parse the output of the "sg_ses" utility and print the useful stuff

Dependencies:  lsscsi, python "prettytable" package

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
    return


def SysExec(cmd):
    """
    Run the given command and return the output
    """
    Cache_Expires = 20

    Cache_Keys = list(CacheDataArray.keys())
    if cmd in Cache_Keys:
        Cache_Age = time.time() - CacheTimeArray[cmd]
    else:
        Cache_Age = 0

    Return_Val = "ERROR"

    if cmd in Cache_Keys and Cache_Age < Cache_Expires:
        Return_Val = CacheDataArray[cmd]
    elif cmd not in Cache_Keys and cmd.split()[0] == "cat":
        parts = cmd.split()
        if len(parts) < 2:
            Debug("SysExec: invalid cat command: " + cmd)
            return Return_Val
        filepath = parts[1]
        if not os.path.isfile(filepath):
            Debug("SysExec: file not found: " + filepath)
            return Return_Val
        try:
            with open(filepath, "r") as f:
                CacheDataArray[cmd] = f.read()
                CacheTimeArray[cmd] = time.time()
                Return_Val = CacheDataArray[cmd]
        except (IOError, OSError) as e:
            Debug("SysExec: error reading file: " + str(e))
            return Return_Val
    else:
        CacheDataArray[cmd] = Popen(cmd.split(), stdout=PIPE, stderr=STDOUT).communicate()[0]
        CacheTimeArray[cmd] = time.time()
        Return_Val = CacheDataArray[cmd]

    if isinstance(Return_Val, bytes):
        Return_Val = Return_Val.decode("utf-8")

    return Return_Val


def List_Enclosures():
    """
    List the available enclosures on this server
    """
    enclosures_list_cmd = SysExec("lsscsi -g")
    enclosures = []
    for line in enclosures_list_cmd.splitlines():
        line = line.strip()

        if not re.search("enclosu", line, re.IGNORECASE):
            continue
        if re.search("VirtualSES", line, re.IGNORECASE):
            continue

        parts = line.split()
        if parts:
            enclosures.append(parts[-1])

    Debug("List_Enclosures:: enclosures = " + str(enclosures))

    return enclosures


def List_Slots(e):
    """
    List the available slots on this enclosure
    """
    slots_list_cmd = SysExec("sg_ses --page=aes " + e)
    slots = []
    for l in slots_list_cmd.splitlines():

        if re.search("Element type: SAS expander", l, re.IGNORECASE):
            break

        if not re.search("Element index: ", l, re.IGNORECASE):
            continue
        parts = l.split(":")
        if len(parts) >= 2:
            slot_val = parts[1].strip().split(" ")[0]
            slots.append(slot_val)

    Debug("List_Slots:: slots for enclosure " + e + " = " + str(slots))

    return slots


sg_ses_dict = {}

enclosures = List_Enclosures()

tmp_enclosures = []
for e in enclosures:
    slots = List_Slots(e)
    if not slots:
        continue
    tmp_enclosures.append(e)
enclosures = tmp_enclosures

if not enclosures:
    print("ERROR: No enclosures detected, or enclosure does not have attached drives.")
    sys.exit(1)


for e in enclosures:

    sg_ses_dict[e] = {}

    slots = List_Slots(e)
    Debug("Slots for Enclosure " + e + " = " + str(slots))

    for s in slots:

        sg_ses_dict[e][s] = {}
        sg_ses_dict[e][s]["enclosure"] = e
        sg_ses_dict[e][s]["slot"] = s

        sg_ses_output = SysExec("sg_ses -p aes --index=" + s + " " + e)
        sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()
        for line in sg_ses_output.splitlines():
            line = ' '.join(line.split()).strip()

            if re.search("target port for:", line, re.IGNORECASE):
                dev_type = line.split(":")[1].strip()
                if dev_type == "SSP":
                    sg_ses_dict[e][s]["media_type"] = "SAS"
                elif dev_type == "SATA_device":
                    sg_ses_dict[e][s]["media_type"] = "SATA"
                elif dev_type == "":
                    sg_ses_dict[e][s]["media_type"] = "Empty"
                else:
                    sg_ses_dict[e][s]["media_type"] = "Unknown"
            elif re.search("SAS address:", line, re.IGNORECASE) and not re.search("attached SAS address", line, re.IGNORECASE):
                sg_ses_dict[e][s]["media_wwn"] = line.split(":")[1].strip()

        sg_ses_output = SysExec("sg_ses -p ed --index=" + s + " " + e)
        sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()
        for line in sg_ses_output.splitlines():
            line = ' '.join(line.split()).strip()
            if re.search("Element " + str(s) + " descriptor:", line, re.IGNORECASE):
                sg_ses_dict[e][s]["descriptor"] = line.split(":")[1].strip()

        sg_ses_output = SysExec("sg_ses -p ec --index=" + s + " " + e)
        sg_ses_output = re.sub(",", "\n", sg_ses_output).strip()

        whitelist = ["s_ident"]
        for line in sg_ses_output.splitlines():
            line = ' '.join(line.split()).strip()

            if re.search("=", line):

                tmp_line = line.lower()
                tmp_line = re.sub("/", "_", tmp_line)
                tmp_line = re.sub(" ", "_", tmp_line)

                key = "s_" + tmp_line.split("=")[0].strip()
                val = tmp_line.split("=")[1].strip()

                if key == "s_ident":
                    if val == "1":
                        val = "On"
                    else:
                        val = "Off"

                if val == "0":
                    val = ""

                sg_ses_dict[e][s][key] = val


sg_ses_dict = {k: v for k, v in sg_ses_dict.items() if v}


new_sg_ses_dict = {}
for e in sg_ses_dict:
    for s in sg_ses_dict[e]:
        key = e + ":" + s
        new_sg_ses_dict[key] = sg_ses_dict[e][s]


Debug("new_sg_ses_dict = " + str(new_sg_ses_dict))


if not enclosures or not sg_ses_dict:
    print("ERROR: No data to display")
    sys.exit(1)

first_enclosure = enclosures[0]
first_slot = None
if first_enclosure in sg_ses_dict and sg_ses_dict[first_enclosure]:
    first_slot = list(sg_ses_dict[first_enclosure].keys())[0]

if first_slot is None:
    print("ERROR: No slot data available")
    sys.exit(1)

col = list(sg_ses_dict[first_enclosure][first_slot].keys())
Debug("col = " + str(col))

x = PrettyTable(col)
x.padding_width = 1
for e in sg_ses_dict:
    for s in sg_ses_dict[e]:

        vals = list(sg_ses_dict[e][s].values())
        x.add_row(vals)
print(x)
