#!/usr/bin/env python3

"""
Returns the PID of the running ibp_server process.  Requires python-psutil to be installed.
"""

import psutil
import re
import os
import subprocess
import signal
import sys

from time import gmtime, strftime, sleep

from ridlib import *

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

IBP_Server_Stop()
