#!/usr/bin/env python

"""
	A library of common functions for operating on a rid.
"""

import re
import os
import sys
import math
import time
import stat
import psutil
import shutil
import signal
import random
import logging
import resource
import tempfile
import subprocess
import collections
import ConfigParser
import multiprocessing

from subprocess import Popen, PIPE, STDOUT, call, check_output
from time import gmtime, strftime, sleep

depot_dir = "/depot"  # This was originally shared via the depot_common file.

CacheDataArray = {}
CacheTimeArray = {}

def SysExec(cmd, Debug = False):

        """
        Run the given command and return the output.  This command will cache the output
        of commands it has run recently.
        """

	if Debug == True:
		logging.info("SysExec:: cmd: " + cmd)

	# Cache the output of the command for 5 seconds
        Cache_Expires = 5

        # Determine the age of the cache
        Cache_Keys = list(CacheDataArray.keys())
        if cmd in Cache_Keys:
                Cache_Age  = time.time() - CacheTimeArray[cmd]
        else:
                Cache_Age  = 0

        # If we have valid data cached, return it
        if cmd in Cache_Keys and Cache_Age < Cache_Expires:
                return CacheDataArray[cmd]

        # If the cmd is "cat", use fopen/fread/fclose instead since they're much faster than a Popen call
        if cmd.split()[0] == "cat":

		if not os.path.isfile(cmd.split()[1]):
			logging.error("SysExec::  ERROR Cannot find file " + cmd.split()[1])
			return ""

                f = open(cmd.split()[1], "r")
                CacheDataArray[cmd] = f.read()
                CacheTimeArray[cmd] = time.time()
                f.close()
                return CacheDataArray[cmd]

        # If we don't have cached data, or it's too old, regenerate it
        if not cmd in Cache_Keys or Cache_Age > Cache_Expires:
                CacheDataArray[cmd] = Popen(cmd.split(), stdout=PIPE, stderr=STDOUT).communicate()[0]
                CacheTimeArray[cmd] = time.time()
                return CacheDataArray[cmd]

        return "ERROR"


def SysExecUncached(cmd):

	"""
	Run the given command and return the output.  This command will *not* cache the output
	of commands it has run recently.   You should use SysExec whenever possible as it is
	faster.
	"""

	return Popen(cmd.split(), stdout=PIPE, stderr=STDOUT).communicate()[0]


def Generate_Rid_Dict():

	Rid_Dict = []

	for line in os.listdir("/dev/disk/by-label"):

	        if not re.search("rid-data", line):
	                continue

	        Rid_Dict.append(line.split("-")[2])

	return Rid_Dict


def Generate_Rid_to_Dev_Dict():

	Dict_Rid_to_Dev = {}

	if os.path.isdir("/dev/disk/by-label"):

		for line in os.listdir("/dev/disk/by-label"):
		        if not re.search("rid-data", line):
		                continue

		        rid = line.split("-")[2]
		        dev = os.path.realpath("/dev/disk/by-label/" + line)
		        dev = re.sub("[0-9]*$", "", dev)

		        Dict_Rid_to_Dev[rid] = dev

	return Dict_Rid_to_Dev


def Generate_Dev_to_Rid_Dict():

	Dict_Dev_to_Rid = {}

	for line in os.listdir("/dev/disk/by-label"):

	        if not re.search("rid-data", line):
	                continue

	        rid = line.split("-")[2]
	        dev = os.path.realpath("/dev/disk/by-label/" + line)
	        dev = re.sub("[0-9]*$", "", dev)

	        Dict_Dev_to_Rid[dev] = rid

	return Dict_Dev_to_Rid


def is_rid_visible_to_os(rid):
	"""
	Returns True if the rid is visible to the OS.
	"""

	rid_exists = False
	if os.path.isfile("/dev/disk/by-label/rid-data-" + rid):
		rid_exists = True
	return rid_exists


def is_rid_mounted(rid):
	"""
	Returns True if the rid has been mounted
	"""

	output = SysExecUncached("mount")

	is_mounted = False
	for line in output.splitlines():
		if re.search("/depot/rid-" + rid + "/data", line):
			is_mounted = True
			break

	return is_mounted


def is_rid_attached_to_ibpserver(rid):
	"""
	Returns True if the rid has been attached to a running ibp_server process
	"""

	is_attached = False
	output = SysExec("get_version -a")

	for line in output.splitlines():

		if re.search("Pending RID count", line):
			if re.search(rid, line):
				is_attached = True
				break

		if re.search("^RID: " + rid + " Max:", line):
			is_attached = True
			break

	return is_attached


def mount_unix(device, dir, mount_opts = ""):

	"""
	Mount a given filesystem (if unmounted)
	"""

	mounts = SysExecUncached("mount")

	for line in mounts.splitlines():
		if re.search(device, line):
			logging.error("mount_unix:: Mount " + device + " already appears to be mounted!")
			return 1

	logging.debug("mount_unix:: Mounting " + device + " at mountpoint " + dir)
	cmd = "mount " + mount_opts + " " + device + " " + dir
	subprocess.call(cmd.split())


def umount_unix(filesystem):

	"""
	Umount a given filesystem (if mounted)
	"""

	if not os.path.isdir(filesystem):
		logging.error("umount_unix:: Filesystem " + filesystem + " not found.")
		return 1

	logging.debug("umount_unix:: Unmounting " + filesystem)
	cmd = "umount " + filesystem
	subprocess.call(cmd.split())

# Return the last line of a file
def LastLine(file):
	f = open(file, "r")
	output = f.readlines()
	f.close()

	LastLine = "NOT_SEQUESTERED"

	if len(output) != 0:
		LastLine = output[-1].strip()

	return LastLine


def LocateMetadata(Rid):

	# Determine which case we have (new or old style)
	# This is true if it's the new style

	Metadata_Path = "UNKNOWN"

	if os.path.isdir("/depot/import/md-" + Rid):

		logging.debug("LocateMetadata::  New style (metadata on SSD)")
		Metadata_Path = "PATH:/depot/import/md-" + Rid

	# Otherwise, it's on the data drive (old style)
	else:

		logging.debug("LocateMetadata::  Old style (metadata on data disk)")
		Dict_Rid_To_Dev = Generate_Rid_to_Dev_Dict()
		Metadata_Path = "BLOCKDEV:" + Dict_Rid_To_Dev[Rid]

	logging.debug("LocateMetadata::  Metadata_Path = " + Metadata_Path)

	return Metadata_Path


# Provides a simple equivalent of the "touch" command for Python
def touch(fname, times=None):
	logging.debug("Touching file " + fname)
	with open(fname, 'a'):
		os.utime(fname, times)

def check_pid(pid):
	""" Check For the existence of a unix pid. """

	try:
		os.kill(pid, 0)
	except OSError:
		return False
	else:
		return True


def remove_obj(f):

	if os.path.ismount(f):
		SysExec("umount " + f)

	type = SysExec("file " + f)

	if re.search("ASCII", type):
		os.remove(f)

	if re.search("symbolic", type):
		os.remove(f)

	if re.search("directory", type):
		os.rmdir(f)




def which(program):

	"""

	Functions similar to the 'which' program in Unix.  Given 
	an executable filename, it will return the whole path to
	that executable.

	which("ls") should return "/bin/ls"

	Will print an error message and terminate the program if
	it can't locate the executable in the path.

	"""

	def is_exe(fpath):
		return os.path.exists(fpath) and os.access(fpath, os.X_OK)

	def ext_candidates(fpath):
 		yield fpath
		for ext in os.environ.get("PATHEXT", "").split(os.pathsep):
			yield fpath + ext

	fpath, fname = os.path.split(program)

	if fpath:
		if is_exe(program):
			return program
	else:
		for path in os.environ["PATH"].split(os.pathsep):
			exe_file = os.path.join(path, program)
			for candidate in ext_candidates(exe_file):
				if is_exe(candidate):
					return candidate


def purge(dir, pattern):
	for f in os.listdir(dir):
		if re.search(pattern, f):
			os.remove(os.path.join(dir, f))


def RID_Mount(Rid):

	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

	logging.debug("RID_Mount:: Performing mount operation on Rid: " + Rid)

	# Default mounting options for RIDs
	mount_opts = "-o noatime,nodiratime"

	rname = depot_dir + "/rid-" + Rid

	if os.path.isdir(rname):
		logging.error("RID_Mount:: Looks like resource " + Rid + " is already mounted (" + rname + ")!")
		sys.exit(2)

	Dict_Rid_to_Dev = Generate_Rid_to_Dev_Dict()

	if Rid not in Dict_Rid_to_Dev:
		logging.error("RID_Mount:: Rid " + Rid + " does not appear to be a valid rid.  Exiting.")
		sys.exit(1)

	Sequester_status = RID_Check_Sequester(Rid)
	if RID_Check_Sequester(Rid).split()[0] == "SEQUESTERED":
		logging.error("RID_Mount:: Rid " + Rid + " is sequestered and will not be mounted.  Exiting.")
		sys.exit(1)

	Dev = Dict_Rid_to_Dev[Rid]
	md_dev = Dev + "1"
	data_dev = Dev + "2"

	logging.debug("RID_Mount:: md_dev = " + md_dev + " and data_dev = " + data_dev)

	# Make a temporary mount point so we can mount the first partition
	temp_dir = tempfile.mkdtemp()
	logging.debug("RID_Mount:: temp_dir = " + temp_dir)
	logging.debug("RID_Mount:: mounting " +  md_dev + " at mountpoint "  + temp_dir)
	SysExec("mount " + md_dev + " " + temp_dir)

	# See if rid.settings exists with the "rid-" defined
	# If not, consider rid.settings to be missing and die.
	ridsettings_file = temp_dir + "/rid.settings"

	rid_line_found = False
	if os.path.isfile(ridsettings_file):
		for line in SysExec("cat " + ridsettings_file).splitlines():
			if re.search("^rid", line):
				rid_line_found = True
				break

	logging.debug("RID_Mount:: rid_line_found = " + str(rid_line_found))

	if not os.path.isfile(ridsettings_file) or not rid_line_found:
		logging.error("RID_Mount:: Missing rid.settings!")
		umount_unix(temp_dir)
		os.rmdir(temp_dir)
		sys.exit(1)

	# Get the import info from the file
	import_state = ""
	import_file = temp_dir + "/import"

	if os.path.isfile(import_file):
		logging.debug("RID_Mount:: import_file = " + import_file)

		if os.path.isfile(import_file):
			import_state = SysExec("cat " + import_file).strip()

	umount_unix(temp_dir)
	os.rmdir(temp_dir)

	if not import_state:
		print("Mounting resource: " + Rid + "  ---- dev:" + md_dev + ":" + data_dev)
	else:
		print("Mounting resource: " + Rid + "  ---- dev:" + md_dev + ":" + data_dev + ":" + import_state.strip())

	logging.debug("RID_Mount:: Creating folder " + rname + " and data folder " + rname + "/data")
	os.mkdir(rname)
	os.mkdir(rname + "/data")

	if not import_state:

		logging.debug("RID_Mount:: Taking path 1...")

		logging.debug("RID_Mount:: Creating metadata mount point at " + rname + "/md")
		os.mkdir (rname + "/md")

		if not is_rid_mounted(rname + "/md"):
			logging.debug("RID_Mount:: Mounting metadata drive " + md_dev + " at mountpoint " + rname + "/md")
			mount_unix(md_dev,   rname + "/md",   mount_opts)

		if not is_rid_mounted(rname + "/data"):
			logging.debug("RID_Mount:: Mounting data drive " + data_dev + " at mountpoint " + rname + "/data")
			mount_unix(data_dev, rname + "/data", mount_opts)

		is_metadata = os.path.ismount(rname + "/md")
		is_data     = os.path.ismount(rname + "/data")
		logging.debug("is_metadata = " + str(is_metadata) + " and is_data = " + str(is_data)) 

		if not is_metadata or not is_data:
			logging.error("RID_Mount:: Failed mounting partitions!  Attempting to unwind and exit...")
			umount_unix(rname + "/md")
			umount_unix(rname + "/data")
			os.rmdir(rname + "/md")
			os.rmdir(rname + "/data")
			sys.exit(3)

	else:

		mount_unix(data_dev, rname + "/data", mount_opts)

		logging.debug("RID_Mount:: Creating symlink between " + import_state + " and " + rname + "/md")
		os.symlink(import_state, rname + "/md")

		if not os.path.ismount(rname + "/data") and not os.path.islink(rname + "/md"):
			logging.error("RID_Mount:: Failed mounting partitions!  Attempting to unwind and exit...")
			os.ulink(rname + "/md")
			umount_unix(rname + "/data")
			os.rmdir(rname + "/data")
			os.rmdir(rname)
			sys.exit(4)

		import_state = ":" + import_state

	output_file = rname + "/rid.info"
	logging.debug("RID_Mount:: Saving info to " + output_file + " and then exiting")
	f = open(output_file, "w")
	f.write("dev:" + md_dev + ":" + data_dev + import_state + "\n")
	f.close()


def RID_Umount(Rid):

	logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
#	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

	logging.debug("RID_Umount:: Performing umount operation on Rid: " + Rid)

	rname = depot_dir + "/rid-" + Rid
	rinfo = rname + "/rid.info"

	logging.debug("RID_Umount:: rname = " + rname + " and rinfo = " + rinfo)

	# If the rid doesn't appear to be mounted, fail.
	if not os.path.isdir(rname):
		logging.info("RID_Umount:: Rid " + Rid + " does not appear to be mounted.  No rid directory " + rname + " exists.")
		sys.exit(1)

	if not os.path.isfile(rinfo):
		logging.info("RID_Umount:: Rid " + Rid + " does not appear to be mounted.  No rid.info file at " + rname + ".")
		sys.exit(1)

	# See if lsof sees any files on this rid being used.   If so, fail.

	lsof_md = ""
	lsof_data = ""

	if os.path.isdir("/depot/import/md-" + str(Rid)):
		lsof_md = SysExec("lsof /depot/import/md-" +str(Rid))

	if os.path.isdir("/depot/rid-" + str(Rid) + "/data"):
		lsof_data = SysExec("lsof /depot/rid-" + str(Rid) + "/data")

	if len(lsof_md) > 0 or len(lsof_data) > 0:
		logging.error("RID_Umount:: Can't umount RID.  Appears to be in use according to 'lsof'!")
		sys.exit(1)

	RInfo = SysExec("cat " + rinfo).strip()

	logging.debug("RInfo = " + RInfo)

	dtype = RInfo.split(":")[0]

	logging.debug("dtype = " + dtype)

	import_type=""
	if len(RInfo) == 4:
		import_type = RInfo.split(":")[3]

	logging.debug("RID_Umount:: import_type = " + import_type + " and RInfo = " + RInfo)

	print("Umounting rid " + Rid)

	if dtype != "dev" and dtype != "dir":
		logging.error("RID_Umount:: Missing or unknown device type(" + dtype + ")!")
		sys.exit(2)

	if dtype == "dev":

		logging.debug("RID_Umount:: Running the 'dev' path...")

		logging.debug("RID_Umount:: Umounting data partition at mountpoint" + rname + "/data")
		umount_unix(rname + "/data")
		if not is_rid_mounted(rname + "/data"):
			logging.debug("RID_Umount:: " + rname + "/data was successfully umounted")
		else:
			logging.debug("RID_Umount:: " + rname + "/data was not umounted!!")

		if os.path.isdir(rname + "/data"):
			logging.debug("RID_Umount:: Erasing old data mount point " + rname + "/data")
			os.rmdir(rname + "/data")

		if not import_type:

			logging.debug("RID_Umount:: No import_type found")

			logging.debug("RID_Umount:: Umounting metadata partition at mountpoint " + rname + "/md")
			umount_unix(rname + "/md")
			if not is_rid_mounted(rname + "/md"):
				logging.debug("RID_Umount:: " + rname + "/md was successfully umounted")
			else:
				logging.debug("RID_Umount:: " + rname + "/md was not umounted!!")

			if os.path.islink(rname + "/md"):
				logging.debug("RID_Umount:: Erasing old metadata symlink at " + rname + "/md")
				os.remove(rname + "/md")

			if os.path.isdir(rname + "/md"):
				logging.debug("RID_Umount:: Erasing old metadata mount point at " + rname + "/md")
				os.rmdir(rname + "/md")
		else:
			logging.debug("RID_Umount:: Removing " + rname + "/md")
			os.remove(rname + "/md")

	elif dtype == "dir":
		logging.debug("RID_Umount:: Removing the data/metadata folders...")

		os.remove(rname + "/md")
		os.remove(rname + "/data")

	logging.debug("RID_Umount:: Removing " + rname + "/rid.info")
	os.remove(rname + "/rid.info")

	logging.debug("RID_Umount:: rmdir " + rname)

	if os.path.isdir(rname):
		os.rmdir(rname)


def RID_Sequester(Rid, Msg):

	# We have to support two use cases:
	#
	# * New style (metadata on ssd)
	# * Old style (metadata on data disk)
	#
	# If the metadata is on the data disk, we may need
	# to mount then unmount it.
	Unmount_Later = 0

	Metadata_Location = LocateMetadata(Rid)

	if re.search("^UNKNOWN", Metadata_Location):
		logging.error("RID_Sequester:: Path to Rid metadata cannot be determined.  Exiting.")
		sys.exit(1)

	if re.search("^PATH", Metadata_Location):
		Metadata_Path = Metadata_Location.split(":")[1]

	if re.search("^BLOCKDEV", Metadata_Location):
		Metadata_Path = tempfile.mkdtemp()
		mount_unix(Dev + "1", Metadata_Path)
		Unmount_Later = 1

	Sequester_file = Metadata_Path + "/SEQUESTER_STATUS"

	if not os.path.isfile(Sequester_file):
		touch(Sequester_file)

	last_line = LastLine(Sequester_file).strip()

	if re.search("^SEQUESTERED", last_line):
		print("Rid " + Rid + " is already sequestered.")
	else:

		now = strftime("%a %b %d %T %Z %Y", gmtime())

		Status = "SEQUESTERED | " + now + " | " + Msg + "\n"

		with open(Sequester_file, "a") as f:
			f.write(Status)
		f.close()
		print("Rid " + Rid + " is now sequestered.")

	if Unmount_Later == 1:
		umount_unix(Metadata_Path)
		os.rmdir(Metadata_Path)

	sys.exit(0)


def RID_Unsequester(Rid, Msg):

	# We have to support two use cases:
	#
	# * New style (metadata on ssd)
	# * Old style (metadata on data disk)
	#
	# If the metadata is on the data disk, we may need
	# to mount then unmount it.
	Unmount_Later = 0

	Metadata_Location = LocateMetadata(Rid)

	if re.search("^UNKNOWN", Metadata_Location):
		logging.error("RID_Unsequester:: Path to Rid metadata cannot be determined.  Exiting.")
		sys.exit(1)

	if re.search("^PATH", Metadata_Location):
		Metadata_Path = Metadata_Location.split(":")[1]

	if re.search("^BLOCKDEV", Metadata_Location):
		Metadata_Path = tempfile.mkdtemp()
		mount_unix(Dev + "1", Metadata_Path)
		Unmount_Later = 1

	Sequester_file = Metadata_Path + "/SEQUESTER_STATUS"

	if not os.path.isfile(Sequester_file):
		touch(Sequester_file)

	last_line = LastLine(Sequester_file)

	if re.search("^NOT_SEQUESTERED", last_line):
		print("Rid " + Rid + " is already unsequestered.")
	else:

		now = strftime("%a %b %d %T %Z %Y", gmtime())

		Status = "NOT_SEQUESTERED | " + now + " | " + Msg + "\n"

		with open(Sequester_file, "a") as f:
			f.write(Status)
		f.close()
		print("Rid " + Rid + " is now unsequestered.")

	if Unmount_Later == 1:
		umount_unix(Metadata_Path)
		os.rmdir(Metadata_Path)

	sys.exit(0)


def IBP_Server_Status():

	import psutil

	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

	name = ""
	pid = 0
	# See if ibp_server is currently running, and kill it if it is.
	for proc in psutil.process_iter():
		if re.search("ibp_server.", str(proc)):
			name = proc.name()
			pid = proc.pid
			break

	logging.debug("Name = " + str(name) + " and PID = " + str(pid))


def IBP_Server_Start():

	# If I'm running under pychecker (or another debugger), remove it from sys.argv
	# so it will work as normal below.
	for i in sys.argv:
		if re.search("pychecker", i):
			sys.argv.remove(i)

	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')
	#logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

	# We want a random number so we can spawn a copy of ibp_server with a random filename
	ibp_server_exe = "/tmp/ibp_server." + str(random.randint(0, 32767))

	name = ""
	pid = 0
	# See if ibp_server is currently running, and kill it if it is.
	for proc in psutil.process_iter():
		if re.search("ibp_server.", str(proc)):
			name = proc.name()
			pid = proc.pid
			break

	if not pid and not name:
		logging.info("ibp_server is not running")
	else:
		logging.info("Sending SIGQUIT to name " + name + " and pid " + str(pid))
		os.kill(pid, signal.SIGQUIT)

		while check_pid(pid):
			time = strftime("%Y-%m-%d %H:%M:%S", gmtime())
			pid_status=subprocess.Popen(['ps', 'u', '-p', str(pid)], stdout=subprocess.PIPE).communicate()[0]
			logging.info("Waiting for ibp_server shutdown to complete...  " + time)
			logging.info(pid_status)
			sleep(1)

		print("Completed shutdown.")

	# Remove the old ibp_server.exe binary in /tmp if it exists
	logging.info("Removing old ibp_server binaries under /tmp ...")
	purge("/tmp", "ibp_server")

	# Copy the current version to /tmp
	exe = which("ibp_server.exe")
	if not exe:
		exe = which("ibp_server")

	if not exe:
		logging.error("Can't locate ibp_server.exe in the PATH!  Aborting!")
		sys.exit(1)
	shutil.copyfile(exe, ibp_server_exe)

	# Set permission of the tmp ibp_server to executable
	st = os.stat(ibp_server_exe)
	os.chmod(ibp_server_exe, st.st_mode | stat.S_IEXEC)

	# See if we need to change the number of FD's
	cfg = ""
	for arg in sys.argv[1:]:
		if os.path.isfile(arg):
			cfg = arg
			break

	logging.debug("cfg = " + cfg)

	nthreads = 0
	nres = 0
	nres_list = []

	if os.path.isfile(cfg):

		f = open(cfg, 'r')

		for line in f.read().splitlines():

			if re.search("threads", line):
				logging.debug("nthreads line from cfg = " + line)
				nthreads = line.split("=")
				nthreads = nthreads[1].strip()

			if re.search("^\\[resource ", line) and line not in nres_list:
				nres += 1
				nres_list.append(line)
		f.close()

	nfd = resource.getrlimit(resource.RLIMIT_NOFILE)
	nfd = nfd[0]

	minfd = 3*int(nthreads) + 10*int(nres) + 64

	# nfs/minfd need to be a tuple of (soft_limit, hard_limit).  Then figure out how to do arithmetic on them...
	if nfd < minfd:
		logging.info("** Adjusting max fd to correspond with " + cfg + ".  threads=" + str(nthreads) + " resources=" + str(nres))
		logging.info("** Current max fd is " + str(nfd) + " changing to " + str(minfd) + " (ulimit -n " + str(minfd) + ")")

		resource.setrlimit(resource.RLIMIT_NOFILE, (minfd, minfd))
		newfd = resource.getrlimit(resource.RLIMIT_NOFILE)

		if newfd != (minfd, minfd):
			logging.info("newfd = " + str(newfd) + " and minfd = " + str(minfd))
			logging.error("Can't make fd limit large enough!  Exiting without launching ibp_server!")
			logging.error("Please lower the number of threads or increase the system wide max fd.")
			sys.exit(1)

	cmd = "LD_PRELOAD=\"/usr/local/lib/libtcmalloc.so\" " + ibp_server_exe + " " + " ".join(sys.argv[1:])
	logging.info("Attempting to run command: " + cmd)

	args = [ ibp_server_exe ]
	args.extend(sys.argv[1:])

	env = {}
	env["LD_LIBRARY_PATH"] = "/usr/local/lib"
	env["LD_PRELOAD"]      = "/usr/local/lib/libtcmalloc.so"

	subprocess.Popen(args=args, env = env)


def IBP_Server_Stop():

	name = ""
	pid = 0
	for proc in psutil.process_iter():
		if re.search("ibp_server.", str(proc)):
			name = proc.name()
			pid = proc.pid
			break

	if not pid and not name:
		print("INFO:  ibp_server is not running")
		sys.exit()

	print("INFO:  Sending SIGQUIT to name " + name + " and pid " + str(pid))

	os.kill(pid, signal.SIGQUIT)

	while check_pid(pid):
		time = strftime("%Y-%m-%d %H:%M:%S", gmtime())
		pid_status=subprocess.Popen(['ps', 'u', '-p', str(pid)], stdout=subprocess.PIPE).communicate()[0]
		print("Waiting for ibp_server shutdown to complete...  " + time)
		print(pid_status)
		sleep(1)

	print("Completed shutdown.")


def RID_List(arguments=""):

	# How we want to format our output
	FORMAT="%-6s %4s  %-13s %-11s  %-25s %-25s"

	rid_list = []
	for line in os.listdir(depot_dir):
		if re.search("^rid", line):
			rid_list.append(line.split("-")[1])
	rid_list.sort()

	if ("-rid-only" not in sys.argv) and (arguments != "-rid-only"):
		print FORMAT % ("RID", "Type", "Data", "Metadata", "Import Metadata", "Sequester Status")
		print FORMAT % ("-----", "----", "-----------", "-----------", "----------------------", "-----------------")

	info = []

	for rid in rid_list:

		if os.path.isfile(depot_dir + "/rid-" + str(rid) + "/rid.info"):
			f = open(depot_dir + "/rid-" + str(rid) + "/rid.info" , 'r')
			info = f.read().split(":")
			f.close()

		sequester_status = "NOT_SEQUESTERED"
		if os.path.isdir(depot_dir + "/import/md-" + str(rid)):
			if os.path.isfile(depot_dir + "/import/md-" + str(rid) + "/SEQUESTER_STATUS"):
				f = open(depot_dir + "/import/md-" + str(rid) + "/SEQUESTER_STATUS")
				sequester_status = f.readlines()[-1].strip()
				f.close

		mount_type    = "UNKNOWN"
		data_dev      = "UNKNOWN"
		metadata_dev  = "UNKNOWN"
		import_status = "NOT_IMPORTED"

		if info:
			mount_type   = info[0].strip()
			data_dev     = info[2].strip()
			metadata_dev = info[1].strip()

			if len(info) == 4:
				import_status = info[3].strip()

		if len(sys.argv) > 1:
			if sys.argv[1] == "-rid-only":
				print(rid)

		elif arguments == "-rid-only":
			print(rid)
		else:
			print FORMAT % (rid.rjust(2), mount_type.rjust(2), data_dev.rjust(2), metadata_dev.rjust(2), import_status.rjust(2), sequester_status)



def RID_Merge_Config():

	ibp_conf_file = depot_dir + "/ibp.conf"

	f = open(ibp_conf_file, "w")

	ibp_settings_file = depot_dir + "/ibp.settings"
	if not os.path.isfile(ibp_settings_file):
		print("ERROR!  Cannot find " + ibp_settings_file)
		sys.exit(1)
	t = open(ibp_settings_file)
	f.write(t.read())
	t.close()

	phoebus_settings_file = depot_dir + "/phoebus.settings"
	if not os.path.isfile(phoebus_settings_file):
		print("ERROR!  Cannot find " + phoebus_settings_file)
		sys.exit(1)
	t = open(phoebus_settings_file)
	f.write(t.read())
	t.close()

	rid_list = SysExec("list_rid.py -rid-only")

	for rid in rid_list.splitlines():

		cfg = depot_dir + "/import/md-" + rid + "/rid.settings"
		if os.path.isfile(cfg):

			t = open(cfg)
			f.write(t.read())
			t.close()

	f.close()


def RID_Check_Sequester(Rid):

	# We have to support two use cases:
	#
	# * New style (metadata on ssd)
	# * Old style (metadata on data disk)
	#
	# If the metadata is on the data disk and not currently mounted, we may need
	# to mount then unmount it.
	Unmount_Later = 0

	Metadata_Location = LocateMetadata(Rid)

	logging.debug("RID_Check_Sequester::  Metadata_Location = " + Metadata_Location)

	if re.search("^UNKNOWN", Metadata_Location):
		logging.error("RID_Check_Sequester:: Path to Rid metadata cannot be determined.  Exiting.")
		sys.exit(1)

	if re.search("^PATH", Metadata_Location):
		Metadata_Path = Metadata_Location.split(":")[1]

	if re.search("^BLOCKDEV", Metadata_Location):
		MD_Partition = Metadata_Location.split(":")[1] + "1"
		logging.debug("RID_Check_Sequester:: Metadata Partition = " + MD_Partition)

		Dict_Rid_To_Dev = Generate_Rid_to_Dev_Dict()
		Dev = Dict_Rid_To_Dev[Rid]

		if not is_partition_mounted(MD_Partition):
			logging.debug("RID_Check_Sequester:: Metadata partition is unmounted.  Mounting to check import...")
			Metadata_Path = tempfile.mkdtemp()
			mount_unix(Dev + "1", Metadata_Path)
		else:
			logging.debug("RID_Check_Sequester:: Metadata partition is mounted.  Checking import and then leaving mounted.")
			mounts = SysExecUncached("mount")
			for line in mounts.splitlines():
				if re.search(MD_Partition + " ", line):
					Metadata_Path = line.split(" ")[2]
					break
			Unmount_Later = 1

	logging.debug("RID_Check_Sequester:: Metadata_Path = " + Metadata_Path)

	Sequester_file = Metadata_Path + "/SEQUESTER_STATUS"

	logging.debug("RID_Check_Sequester:: Sequester_file = " + Sequester_file)

	Output = "NOT_SEQUESTERED"
	if os.path.isfile(Sequester_file):
		Output = LastLine(Sequester_file)

	if re.search("^BLOCKDEV", Metadata_Location) and Unmount_Later == 0:
		umount_unix(Metadata_Path)
		os.rmdir(Metadata_Path)

	logging.debug("RID_Check_Sequester:: Output = " + Output)

	return Output


def findRawSize(SD_Device):
	"""
	Fetch raw device size (in bytes) by multiplying "/sys/block/DEV/queue/hw_sector_size"
	by /sys/block/DEV/size
	"""

	secsize = "0"
	numsec  = "0"

	tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/size"
	if os.path.isfile(tfile):
		numsec = SysExec("cat " + tfile).strip()

	tfile = "/sys/block/" + SD_Device.split("/")[-1] + "/queue/hw_sector_size"
	if os.path.isfile(tfile):
		secsize = SysExec("cat " + tfile).strip()

	return int(numsec) * int(secsize)


def Set_Ini_Option(File, Section, Key, Value):

	if os.path.isfile(File + ".old"):
		os.remove(File + ".old")

	if os.path.isfile(File):
		os.rename(File, File + ".old")

	Config = ConfigParser.ConfigParser()

	# I thought this would copy comments to the new config file, but apparently not.
	# Config.comment_prefixes=('#', ';')
	# Config.inline_comment_prefixes=('#', ';')

	Config.read(File + ".old")

	if Section not in Config.sections():
		Config.add_section(Section)

	Config.set(Section, Key, Value)

	with open(File, 'w') as configfile:
		Config.write(configfile)


def partition_exists(path):

	try:
		return stat.S_ISBLK(os.stat(path).st_mode)
	except:
		return False


def is_partition_mounted(partition):
	"""

	Returns True if the partition has been mounted
	"""

	output = SysExec("mount")

	is_mounted = False
	for line in output.splitlines():
		if re.search(partition, line):
			is_mounted = True
			break

	return is_mounted


def RID_Fsck(Rid):

	Rid_to_Dev = Generate_Rid_to_Dev_Dict()

	if Rid not in Rid_to_Dev:
		print("ERROR:  Could not determine the block device associated with RID " + Rid)
		sys.exit(1)

	Dev = Rid_to_Dev[Rid]

	logging.debug("RID_Fsck::  Rid " + Rid + " belongs to Dev " + Dev)

	Partitions = []
	for i in range(0,255):
		if partition_exists(Dev + str(i)):
			Partitions.append(Dev + str(i))

	logging.debug("RID_Fsck::  Partitions = " + str(Partitions))

	for part in Partitions:

		if is_partition_mounted(part):

			logging.debug("RID_Fsck::  Partition " + part + " is mounted, skipping fsck...")
			continue

		logging.debug("RID_Fsck::  Partition " + part + " is unmounted, commensing fsck...")

		SysExec("fsck -y " + part)




def RID_Defrag(Rid, LogDir, Extent_Threshold = 3):

	if not os.path.isdir(LogDir):
		logging.debug("RID_Defrag:: LogDir " + LogDir + " doesn't exist, so creating...")
		os.mkdir(LogDir)

	# Create an array of "valid" characters so I can filter out bad ones
	# There is almost certainly a better way to do this, but it's quick
	# and allows me to test some things.
	ValidChars = [ \
		"a", "b", "c", "d", "e", "f", "g", "h", "i", "j", \
		"k", "l", "m", "n", "o", "p", "q", "r", "s", "t", \
		"u", "v", "w", "x", "y", "z", "A", "B", "C", "D", \
		"E", "F", "G", "H", "I", "J", "K", "L", "M", "N", \
		"O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", \
		"Y", "Z", "0", "1", "2", "3", "4", "5", "6", "7", \
		"8", "9", " ", "-", ":" ]

	# We don't want any from these folders
	SkipMe = [ "./deleted_trash", "./expired_trash", "./lost+found" ]

	# I should add a bit of code to detect where the RID Data partition is mounted
	# but until then...
	if not os.path.isdir("/depot/rid-" + Rid):
		logging.error("RID_Defrag:: ERROR: RID " + Rid + " either doesn't exist or isn't mounted properly.  Please check.")
		sys.exit(1)

	Logfile = LogDir + "/extents-rid-" + Rid + ".log"
	if os.path.isfile(Logfile):
		os.remove(Logfile)

	Now = strftime("%a %b %d %T %Z %Y", gmtime())

	logging.debug("RID_Defrag:: Starting defrag of RID " + Rid + " at " + Now)

	f = open(Logfile, "w")

	f.write("# TIME START RID " + Rid + " SCAN - " + Now + "\n")
	f.write("##################################################################\n")

	for i in range(0, 256):
		Dir = "/depot/rid-" + str(Rid) + "/data/" + str(i)
		for dirname, subdirname, filenames in os.walk(Dir):
			for filename in filenames:
				for skip in SkipMe:
					if dirname == skip:
						continue
				Filename = os.path.join(dirname, filename)
				Filesize = os.path.getsize(Filename)
				NumExtents = SysExec("filefrag " + Filename).split(" ")[1]

				# It's an arbitrary threshold, but the vast majority of files have
				# <= 3 extents, so only defrag files that have more.
				if int(NumExtents) <= Extent_Threshold:
					continue

				Extents_After = check_output(["e4defrag", "-v", Filename])

				# Filter out the nasty non-numeric characters and then
				# pluck out the "after" extents
				Extents_After = "".join([ c for c in Extents_After if c in ValidChars ])
				Extents_After = Extents_After[::-1]
				Extents_After = Extents_After.split("-")[0]
				Extents_After = Extents_After[::-1]
				Extents_After = Extents_After.split(" ")[1]

				Output = "Rid = " + Rid + " and Filename = " + Filename + " and Filesize = " + str(Filesize) + " and Extents Before = " + NumExtents + " and Extents after = " + Extents_After

				f.write(Output + "\n")
				logging.debug(Output)

	Now = strftime("%a %b %d %T %Z %Y", gmtime())

	logging.debug("RID_Defrag:: Finished defrag of Rid " + Rid + " at " + Now)

	f.write("##################################################################\n")
	f.write("# TIME END RID " + Rid + " SCAN - " + Now + "\n")

	f.close()


def Smart_Attributes(Dev):

	# If Dev doesn't exist, bail out now...

	f = open("/sys/block/" + Dev.split("/")[-1] + "/device/model")
	Model = f.read().strip()
	f.close()

	# How to determine if a drive is SATA or SAS.  At some point we need to improve this...
	SAS = 0
	SAS_Transport = SysExec("smartctl -i " + Dev)
	for line in SAS_Transport.splitlines():
		if re.search("^Transport protocol", line):
			if re.search("SAS", line):
				SAS = 1
				break

	Drive_Attributes = {}

	if SAS == 1:

		Attr = SysExec("smartctl -a " + Dev)

		for line in Attr.splitlines():

			# Some SAS attributes can be mapped to corresponding SATA attributes
			if re.search("^Accumulated start-stop cycles", line):
				t = line.split(":")[1].strip()
				Drive_Attributes[4] = "4_Start_Stop_Count " + t + " 0 0 " + t

			if re.search("number of hours powered up", line):
				t = line.split("=")[1].strip().split(".")[0]
				Drive_Attributes[9] = "9_Power_On_Hours " + t + " 0 0 " + t

			if re.search("Current Drive Temperature", line):
				t = line.split(":")[1]
				t = re.sub("C", "", t).strip()
				Drive_Attributes[194] = "194_Temperature_Celsius " + t + " " + t + " 0 " + t

			# Others we'll create unique SAS attributes for
			if re.search("^Elements in grown defect list", line):
				t = line.split(":")[1].strip()
				Drive_Attributes[9000] = "9000_SAS_Grown_Defect_List " + t + " 0 0 " + t

			if re.search("^Manufactured in", line):
				t = re.sub("Manufactured in ", "", line)
				t = re.sub(" of year ", ",", t)
				t = re.sub(" ", "_", t)
				Drive_Attributes[9001] = "9001_SAS_Manufacture_Date 0 0 0 " + t

			if re.search("^read:", line):
				t = ' '.join(line.split())
				t = t.split(" ")[6].split(".")[0]
				Drive_Attributes[9002] = "9002_SAS_Gigabytes_Read " + t + " 0 0 " + t

			if re.search("^write:", line):
				t = ' '.join(line.split())
				t = t.split(" ")[6].split(".")[0]
				Drive_Attributes[9003] = "9003_SAS_Gigabytes_Write " + t + " 0 0 " + t

	else:

		Attr = SysExec("smartctl --attributes " + Dev)

		for line in Attr.splitlines():

			line = line.lstrip()

			if not re.search("^[0-9]", line):
				continue

			line = ' '.join(line.split())

			Num    = line.split(" ")[0]
			Txt    = line.split(" ")[1]
			Val    = line.split(" ")[3]
			Worst  = line.split(" ")[4]
			Thresh = line.split(" ")[5]
			Raw    = line.split(" ")[9]

			key = int(Num)
			val = Num + "_" + Txt + " " + Val + " " + Worst + " " + Thresh + " " + Raw

			Drive_Attributes[key] = val

	return collections.OrderedDict(Drive_Attributes.items())

	# Do some formatting so we can pretty-print the info.   First,
	# get the length of the longest key/val so we can format the output
	pad_len = 3
	len_key = 9
	len_value = 5
	len_worst = 5
	len_thresh = 6
	len_raw = 3
	for key in Drive_Attributes:
		val = Drive_Attributes[key]
		len_key    = max(len(val.split(" ")[0]), len_key)
		len_value  = max(len(val.split(" ")[1]), len_value)
		len_worst  = max(len(val.split(" ")[2]), len_worst)
		len_thresh = max(len(val.split(" ")[3]), len_thresh)
		len_raw    = max(len(val.split(" ")[4]), len_raw)

	FORMAT = "%-" + str(len_key+pad_len) + "s %-" + str(len_value+pad_len) + "s %-" + str(len_worst+pad_len) + "s %-" + str(len_thresh+pad_len) + "s %-" + str(len_raw+pad_len) + "s"

	print FORMAT % ("Attribute", "Value", "Worst", "Thresh", "Raw")
	print("=========================================================================")


	for key, val in sorted.iteritems():

		val = Drive_Attributes[key]

		Attr   = val.split(" ")[0]
		Value  = val.split(" ")[1]
		Worst  = val.split(" ")[2]
		Thresh = val.split(" ")[3]
		Raw    = val.split(" ")[4]

		print FORMAT % (Attr, Value, Worst, Thresh, Raw)


def Query_Drives_Smart_Attributes(Query):

	Output_Dict = {}

	for line in os.listdir("/sys/block"):

		if re.search("^loop", line):
			continue

		if re.search("^ram", line):
			continue

		if re.search("^dm-", line):
			continue

		Dev    = "/dev/" + line
		Attributes = Smart_Attributes(Dev)

		Attr = "None"

		# If the input is a Smart Attribute name, go this way...
		if re.search("_", Query):
			for Key in Attributes:
				Val = Attributes[Key]
				Name = Val.split()[0]
				if re.search(Query, Name):
					Attr = Val

		# If the input is a Smart ID#, go this way...
		if re.search("^[0-9]+$", Query):
			if int(Query) in Attributes:
				Attr = Attributes[int(Query)]

		if Attr == "None":
			continue

		Name   = Attr.split()[0]
		Value  = Attr.split()[1]
		Worst  = Attr.split()[2]
		Thresh = Attr.split()[3]
		Raw    = Attr.split()[4]

		Output_Dict[Dev] = (Dev, Name, Value, Worst, Thresh, Raw)

	return Output_Dict


def Print_Query_Drives_Smart_Attributes(Output_Dict):

	# Ok, now format it for pretty-printing
	pad_len = 3
	len_dev = 6
	len_attr = 4
	len_value = 5
	len_worst = 5
	len_thresh = 6
	len_raw = 3

	for key in Output_Dict:

		val = Output_Dict[key]

		len_dev    = max(len(val[0]), len_dev)
		len_attr   = max(len(val[1]), len_attr)
		len_value  = max(len(val[2]), len_value)
		len_worst  = max(len(val[3]), len_worst)
		len_thresh = max(len(val[4]), len_thresh)
		len_raw    = max(len(val[5]), len_raw)

	FORMAT = "%-" + str(len_dev+pad_len) + "s %-" + str(len_attr+pad_len) + "s %-" + str(len_value+pad_len) + "s %-" + str(len_worst+pad_len) + "s %-" + str(len_thresh+pad_len) + "s %-" + str(len_raw+pad_len) + "s"

	Length = len_dev + len_attr + len_value + len_worst + len_thresh + len_raw + 5*pad_len + 6 # The 6 is pulled from thin air, but works...

	print FORMAT % ("Device", "Attr", "Value", "Worst", "Thresh", "Raw")
	print("=" * Length)

	for key in Output_Dict:
		print FORMAT % Output_Dict[key]


def Determine_Drive_Protocol(Dev):

	"""
	Return the protocol the drive uses (SATA, SAS, etc)
	There may be a better way to do this, but not that I've found...
	"""

	Protocol = "UNKNOWN"

	for line in SysExec("smartctl -i " + Dev).splitlines():

		if re.search("Transport protocol", line) and re.search("SAS", line):
			Protocol = "SAS"
			break

		if re.search("ATA Version", line) or re.search("SATA", line):
			Protocol = "SATA"
			break

	print("Determine_Drive_Protocol::  Protocol = " + Protocol)

	return Protocol


def RID_Run_SmartTest(Rid, TestType = "short"):

	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

	if TestType != "short" and TestType != "long":
		print("ERROR:  You requested a " + TestType + " SMART test which isn't supported.")
		sys.exit(1)

	# Just promote it to a string here...
	Rid = str(Rid)

	Rid_to_Dev = Generate_Rid_to_Dev_Dict()

	if Rid not in Rid_to_Dev:
		print("ERROR:  Could not find Rid " + Rid + " on this system.")
		sys.exit(1)

	Dev = Rid_to_Dev[Rid]

	logging.debug("Dev = " + Dev)

	# I want to check and see if there's already a SMART test running before
	# spawning another.   Unfortunately, this test only works on SATA drives.
	Drive_Protocol = Determine_Drive_Protocol(Dev)

	if Drive_Protocol == "SATA":

		Test_in_Progress = False
		for line in SysExec("smartctl -c " + Dev).splitlines():
			if re.search("Self-test routine in progress", line):
				Test_in_Progress = True
				break

		logging.debug("Test_in_Progress = " + str(Test_in_Progress))

	# Start a SMART test...
	SysExec("smartctl -t " + TestType + " " + Dev)


def HumanFriendlyBytes(bytes, scale, decimals):

	"""
	Convert a integer number of bytes into something legible (10 GB or 25 TiB)
	Base 1000 units = KB, MB, GB, TB, etc.
	Base 1024 units = KiB, MiB, GiB, TiB, etc.
	"""

	AcceptableScales = [ 1000, 1024 ]

	if not scale in AcceptableScales:
		return "ERROR"

	unit_i = int(math.floor(math.log(bytes, scale)))

	if scale == 1000:
		UNITS = [ "B",  "KB",  "MB",  "GB",  "TB",  "PB",  "EB",  "ZB",  "YB" ]
	if scale == 1024:
		UNITS = [ "B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB" ]

	scaled_units = UNITS[unit_i]
	scaled_size = round(bytes / math.pow(scale, unit_i), decimals)

	return str(scaled_size) + " " + scaled_units


def query_yes_no(question, default="no"):

	"""
	Ask a yes/no question via raw_input() and return their answer.
	The return value is True for "yes" or False for "no".
	"""

	valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}

	if default is None:
		prompt = " [y/n] "
	elif default == "yes":
		prompt = " [Y/n] "
	elif default == "no":
		prompt = " [y/N] "
	else:
		raise ValueError("invalid default answer: '%s'" % default)

	while True:
		sys.stdout.write(question + prompt)
		choice = raw_input().lower()
		if default is not None and choice == '':
			return valid[default]
		elif choice in valid:
			return valid[choice]
		else:
			sys.stdout.write("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")


def Parted_Return_Next_Available_Sector(Dev):

	PartedFilter = [ "Model", "Disk", "Sector", "Partition", "Number" ]

	for line in SysExec("parted " + Dev + " unit s p free").splitlines():

		line = ' '.join(line.split())

		# Skip blank lines
		if not line:
			continue

		val = line.split(" ")[0].split(":")[0].strip()

		# If the line contains stuff we don't want, skip it
		if val in PartedFilter:
			continue

	return val


def RID_Create(Rid, Dev, AssumeYes = False):

	if not partition_exists(Dev):
		logging.error("RID_Create:: ERROR:  Could not find block device " + Dev + ".  Exiting...")
		return 1

	Rname = depot_dir + "/rid-" + Rid

	if os.path.isfile(Rname):
		print("ERROR:  Looks like a resource is already mounted using RID " + Rid + "!")
		return 1

	# See if there are any partitions on the drive
	logging.info("RID_Create:: Seeing if any existing partitions on drive " + Dev)
	Parts = []

	PartedFilter = [ "Model", "Disk", "Sector", "Partition", "Number", "unrecognized disk label" ]

	for line in SysExec("parted " + Dev + " print").splitlines():

		line = ' '.join(line.split())

		# Skip blank lines
		if not line:
			continue

		val = line.split(" ")[0].split(":")[0].strip()

		# If the line contains stuff we don't want, skip it
		if val in PartedFilter:
			continue

		Parts.append(val)

	if Parts:
		logging.info("RID_Create:: Found the following existing partitions: " + str(Parts))
	else:
		logging.info("RID_Create:: No existing partitions found.")

	# If any partitions were found, verify with the user before deleting them
	# unless AssumeYes is set to True in the function call.
	if Parts and not AssumeYes:

		Question = "\nFound " + str(len(Parts)) + " existing partitions on " + Dev + ".   Are you sure you wish to delete them? [yes/NO]"
		Answer = query_yes_no(Question, default="no")

		if not Answer:
			logging.info("RID_Create:: Ok, exiting...")
			sys.exit(1)

	# Unmount any existing partitions belonging to this drive
	for line in SysExec("mount").splitlines():
		if re.search("^" + Dev + "[0-9]", line):
			part = line.split()[0]
			logging.info("RID_Create:: Detected mounted partition " + part + ".  Attempting to umount...")
			SysExec("umount -f " + part)

	# Since we are creating the filesystem, we need to erase any partitions already
	# on this drive
	for part in Parts:
		logging.info("RID_Create:: Clearing old partition " + part + " from drive " + Dev)
		cmd = "parted -s " + Dev + " rm " + part
		subprocess.call(cmd.split())

	# Create a gpt boot label
	logging.info("RID_Create:: Installing a GPT label on " + Dev)
	cmd = "parted -s " + Dev + " mklabel gpt"
	subprocess.call(cmd.split())

	# Create a small 10 gb partition for the metadata...
	logging.info("RID_Create:: Creating a 10 GB metadata partition...")
	cmd = "parted -s " + Dev + " mkpart primary 0% 10GB"
	subprocess.call(cmd.split())

	# ...and then allocate the rest of the space to data
	ns = Parted_Return_Next_Available_Sector(Dev)
	logging.info("RID_Create:: Allocating all remaining disk space to the data partition...")
	cmd = "parted -s " + Dev + " mkpart primary " + ns + " 100%"
	subprocess.call(cmd.split())

	# Wait a few seconds for the OS to notice the new partitions
	time.sleep(5)

	# Format the partitions
	logging.info("RID_Create:: Formatting metadata partition...")
	cmd = "mkfs.ext4 -E lazy_itable_init=0,lazy_journal_init=0 -F -q -L rid-md-" + Rid + " " + Dev + "1"
	logging.info("cmd = " + cmd)
	subprocess.call(cmd.split())

	logging.info("RID_Create:: Formatting data partition...")
	cmd = "mkfs.ext4 -E lazy_itable_init=0,lazy_journal_init=0 -F -q -L rid-data-" + Rid + " " + Dev + "2"
	logging.info("cmd = " + cmd)
	subprocess.call(cmd.split())

	# A bit of cleaning in case we're doing this over an old install.
	Dirs = [ Rname, Rname + "/md", Rname + "/data" ]
	for dir in Dirs:
		if os.path.islink(dir):
			os.remove(dir)

		if not os.path.isdir(dir):
			os.mkdir(dir)

	mtopt = "-o noatime,nodiratime"
	cmd = "mount " + mtopt + " " + Dev + "1 " + Rname + "/md"
	subprocess.call(cmd.split())

	cmd = "mount " + mtopt + " " + Dev + "2 " + Rname + "/data"
	subprocess.call(cmd.split())

	mkfs_resource_exe = which(mkfs.resource)
	if not mkfs_resource_exe:
		mkfs_resource_exe = which(mkfs_resource)

	if not mkfs_resource_exe:
		logging.error("Can't locate mkfs.resource in the PATH!  Aborting!")

	cmd = mkfs_resource_exe + " " + Rid + " dir " + Rname + "/data " + Rname + "/md"
	Config = SysExec(cmd)
#	Config = subprocess.call(cmd.split())

	with open(Rname + "/md/rid.settings", "w") as f:
		f.write(Config)
	f.close()

	# Make the info file
	with open(Rname + "/rid.info", "w") as f:
		f.write("dev:" + Dev + "1:" + Dev + "2\n")
	f.close()

	logging.info("RID_Create:: Configuration stored in " + Rname + "/md/rid.settings")


def RID_Import(Rid, MD_Dir):

	Rid_Folder = depot_dir + "/rid-" + Rid
	logging.debug("Rid_Folder = " + Rid_Folder)

	if os.path.isfile(Rid_Folder + "/md/import"):
		logging.info("ERROR:  It appears that Rid " + Rid + " is already imported.")
		sys.exit(1)

	Rid_Info = Rid_Folder + "/rid.info"
	logging.debug("RID_Import:: Rid_Info = " + Rid_Info)

	if not os.path.isfile(Rid_Info):
		logging.info("RID_Import:: Missing " + Rid_Info + " file!")
		sys.exit(2)

	Rid_Info_String = SysExec("cat " + Rid_Info).strip()
	logging.debug("RID_Import:: Rid_Info_String = " + Rid_Info_String)

	Depot_Type = Rid_Info_String.split(":")[0]
	logging.debug("RID_Import:: Depot_Type = " + str(Depot_Type))

	lsof_rid = SysExec("lsof " + Rid_Folder)
	if len(lsof_rid) > 0:
	        logging.error("RID_Import:: Can't umount RID.  Appears to be in use according to 'lsof'!")
	        sys.exit(3)

	md_new = MD_Dir + "/md-" + Rid
	logging.debug("RID_Import:: md_dir = " + MD_Dir + " and md_new = " + md_new)

	if os.path.isdir(md_new):
		print("Import destination already exists: " + md_new)
		sys.exit(4)

	# Copy the data over from the old MD
	Src = Rid_Folder + "/md/"
	Dst = md_new
	if not os.path.isdir(Src) or os.path.islink(Src):
		print("ERROR:  Metadata source directory " + Src + " doesn't appear to exist!")
		sys.exit(1)

	logging.debug("RID_Import:: Copying metadata from " + Src + " to " + Dst)
	shutil.copytree(Src, Dst)

	# Update the rid.info file
	with open(Rid_Info, "w") as f:
		f.write(Rid_Info_String + ":" + md_new + "\n")
	f.close()

	# Add the import location
	with open(Rid_Folder + "/md/import", "w") as f:
		f.write(md_new + "\n")
	f.close()

	print("Import completed.  Remounting resource " + Rid + "...")
	RID_Umount(Rid)
	RID_Mount(Rid)


def copyfolder(src, dst, symlinks=False, ignore=None):
	if not os.path.exists(dst):
		os.makedirs(dst)
	for item in os.listdir(src):
		s = os.path.join(src, item)
		d = os.path.join(dst, item)
		if os.path.isdir(s):
			copyfolder(s, d, symlinks, ignore)
		else:
			if not os.path.exists(d) or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
				shutil.copy2(s, d)


def RID_Export(Rid, MD_Dir = ""):

	Rid_Folder = depot_dir + "/rid-" + Rid
	logging.debug("RID_Export:: Rid_Folder = " + Rid_Folder)

	Rid_Info_File = Rid_Folder + "/rid.info"
	logging.debug("RID_Export:: Rid_Info_File = " + Rid_Info_File)

	Rid_Info_String = SysExec("cat " + Rid_Info_File).strip()
	logging.debug("RID_Export:: Rid_Info_String = " + Rid_Info_String)

	Rid_Info = Rid_Info_String.split(":")
	logging.debug("RID_Export:: Rid_Info len = " + str(len(Rid_Info)) + " and val = " + str(Rid_Info))

        Depot_Type = Rid_Info[0]
        logging.debug("RID_Export:: Depot_Type = " + str(Depot_Type))

	if len(Rid_Info) != 4:
		logging.info("ERROR:  It does not appear that Rid " + Rid + " is currently imported.")
		return 1

	MD_Export_Dev    = Rid_Info[1]
	MD_Import_Folder = Rid_Info[3]
	logging.debug("RID_Export:: MD_Export_Dev = " + MD_Export_Dev + " and MD_Import_Folder = " + MD_Import_Folder)

	if not MD_Import_Folder:
		logging.error("RID_Export:: RID not imported!")
		return 1

	if Depot_Type == "dev":

		MD_Export_Folder = depot_dir + "/rid-" + Rid + "/md"
		logging.debug("RID_Export:: MD_Export_Folder = " + MD_Export_Folder)

		if os.path.islink(MD_Export_Folder):
			logging.debug("RID_Export:: " + MD_Export_Folder + " is a symlink, erasing and creating as new directory...")
			os.remove(MD_Export_Folder)

		if not os.path.isdir(MD_Export_Folder):
			logging.debug("RID_Export:: Directory " + MD_Export_Folder + " doesn't exist, so creating...")
			os.mkdir(MD_Export_Folder)

		logging.debug("RID_Export:: Mounting " + MD_Export_Dev + " to folder " + MD_Export_Folder)
		mount_unix(MD_Export_Dev, MD_Export_Folder)

		# Remove the import flag
		logging.debug("RID_Export:: Removing file " + MD_Export_Folder + "/import")
		os.remove(MD_Export_Folder + "/import")

	# Copy the data over
	Src = MD_Import_Folder
	Dst = MD_Export_Folder
        logging.debug("RID_Export:: Copying metadata from " + Src + " to " + Dst)
	copyfolder(Src, Dst)

	# Remove the tmp mount if needed
	if Depot_Type == "dev":

		if is_partition_mounted(MD_Export_Dev):
			logging.debug("RID_Export::  Umounting " + MD_Export_Folder)
			umount_unix(MD_Export_Folder)

	# Now umount/mount the resource
	logging.debug("RID_Export:: Remounting resource...")
	RID_Umount(Rid)
	RID_Mount(Rid)

	# Erase the old copy of the metadata and exit.
	if os.path.isdir(MD_Import_Folder):
		shutil.rmtree(MD_Import_Folder)


def RID_Detach(Rid, Hostname, Port = "6714", Msg = "Detaching Rid"):
	SysExec("ibp_detach_rid " + Hostname + " " + Port + " " + Rid + " 1 " + Msg)

def RID_Attach(Rid, Hostname, Port = "6714", Msg = "Attaching Rid"):
	SysExec("ibp_attach_rid " + Hostname + " " + Port + " " + Rid + " " + Msg)

