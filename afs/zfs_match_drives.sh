#/usr/bin/env bash

# Get a list of "wwn-" style paths
tmp1=$(mktemp)
ls -alh /dev/disk/by-id | grep -v part | grep wwn | rev | cut -d " " -f 1,3 | rev | sed "s/..\/..\///" | grep "wwn-0x6" | awk '{ print $2,$1 }' | sort > ${tmp1}

# Get a list of "path-" style paths
tmp2=$(mktemp)
ls -alh /dev/disk/by-path | grep -v part | rev | cut -d " " -f 1,3 | rev | sed "s/..\/..\///" | grep scsi | awk '{ print $2,$1 }' | sort > ${tmp2}

# Parse the outputs and get a list of all drives
drives=$(cat ${tmp1} ${tmp2} | cut -d " " -f 1 | sort | uniq)

# Make a list of all ZFS vdev's
tmp3=$(mktemp)
cat /etc/zfs/vdev_id.conf | grep -v ^\\# | awk '{ print $2, $3 }'  | grep [0-9] > ${tmp3}

#sdaa wwn-0x600605b00ed14810244223d22fd87030 pci-0000:81:00.0-scsi-0:2:26:0 d27

printf "%-4s %-4s %-38s %-30s\n" "Dev" "VDev" "WWN_Path" "PCI_Path"
printf "===============================================================================\n"

# Loop over all drives and get a list of both paths
for i in ${drives}
do
	wwn_path=$(cat ${tmp1} | grep "^${i} " | awk '{ print $2 }')
	pci_path=$(cat ${tmp2} | grep "^${i} " | awk '{ print $2 }')
	vdev=$(cat ${tmp3} | egrep -i "(${wwn_path}|${pci_path})" | awk '{ print $1 }')
	[ -z "${vdev}" ] && vdev="UNKN"

	printf "%-4s %-4s %-38s %-30s\n" ${i} ${vdev} ${wwn_path} ${pci_path}
done

rm -f ${tmp1} ${tmp2} ${tmp3}
