#!/usr/bin/env bash

CURRENT_KERN_VER=$(uname -r | cut -d "-" -f 1,2)

LATEST_KERN_VER=$(dpkg -l | grep "linux\-image\-[0-9]" | cut -d "-" -f 3,4 | sed "s/-/./" | sort -t. -k 1,1n -k 2,2n -k 3,3n -k 4,4n | tail -n 1 | sed -r 's/(.*)\./\1-/')

echo
echo "INFO:  Running kernel is ${CURRENT_KERN_VER} and newest kernel is ${LATEST_KERN_VER}"
echo

ALL_UNNECESSARY_KERN_PKGS=$(dpkg -l | grep -E "linux\-(headers|image|tools|modules|hwe-tools|hwe-5.8-tools|hwe-5.8-headers|hwe-5.11-tools|hwe-5.11-headers|hwe-5.13-tools|hwe-5.13-headers)-[23456789]\.[0-9]" | cut -d " " -f 3 | grep -v "${LATEST_KERN_VER}" | grep -v "${CURRENT_KERN_VER}")

if [ -z "${ALL_UNNECESSARY_KERN_PKGS}" ]; then
	echo "INFO:  No kernel packages free for uninstall."
else
	echo "INFO:  Kernel packages to uninstall: ${ALL_UNNECESSARY_KERN_PKGS}"
	apt-get -y --purge remove ${ALL_UNNECESSARY_KERN_PKGS}
fi

echo

exit
