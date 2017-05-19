#!/usr/bin/env python

"""
This script merges ibp.settings and all the currently mounted
resources (depot.settings) into a ibp.conf file
"""

import sys
import os

from ridlib import *

RID_Merge_Config()
