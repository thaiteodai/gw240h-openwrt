#!/bin/sh
# Finish the GW240H flash over SSH on the RAM rescue system.
#
# This is the path that was verified on hardware: the rescue initramfs exposes
# dropbear on 192.168.1.1 with an empty root password, so the image can be
# pushed over the LAN when the USB-TTL link is unusable or simply slower.
#
# Prerequisites:
#   - xflash_gw240h.py has booted the rescue kernel (runs entirely from RAM,
#     NAND untouched so far);
#   - this PC has an address in 192.168.1.0/24 on the Ethernet port;
#   - ssh/scp reach root@192.168.1.1 with an empty password.
#
# Usage:
#   ./tools/flash_ssh.sh
#   HOST=192.168.1.1 IMG=../images/openwrt-gw240h-hybrid.trx ./tools/flash_ssh.sh
#
# After it finishes, reboot with:  ssh root@192.168.1.1 reboot
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
HOST=${HOST:-192.168.1.1}
IMG=${IMG:-$HERE/../images/openwrt-gw240h-hybrid.trx}
EXPECTED_MD5=${EXPECTED_MD5:-16b1657e4606e5cdb7c2038c80c11984}

[ -f "$IMG" ] || { echo "error: image not found: $IMG" >&2; exit 1; }

md5=$(md5sum "$IMG" | cut -d' ' -f1)
echo "image: $IMG"
echo "md5:   $md5"
if [ "$md5" != "$EXPECTED_MD5" ]; then
	echo "warning: md5 does not match the known-good image ($EXPECTED_MD5)" >&2
	printf 'continue anyway? [y/N] '
	read -r ans
	[ "$ans" = y ] || [ "$ans" = Y ] || exit 1
fi

echo "--- checking rescue system at $HOST"
ssh "root@$HOST" 'uname -a; cat /proc/mtd | grep -E "tclinux|rootfs_ubi"'

echo "--- uploading image"
scp "$IMG" "root@$HOST:/tmp/fw"

echo "--- writing NAND (tclinux, tclinux_alt, rootfs_ubi)"
ssh "root@$HOST" 'set -e

md5sum /tmp/fw

UBI_IDX=$(grep rootfs_ubi /proc/mtd | cut -d: -f1)
[ -n "$UBI_IDX" ] || { echo "rootfs_ubi not found in /proc/mtd" >&2; exit 1; }
echo "rootfs_ubi -> /dev/$UBI_IDX"

mtd write /tmp/fw tclinux
mtd write /tmp/fw tclinux_alt

dd if=/tmp/fw of=/tmp/ubi bs=65536 skip=64

ubidetach -d 0 2>/dev/null || true
ubidetach -m "${UBI_IDX#mtd}" 2>/dev/null || true
ubiformat "/dev/$UBI_IDX" -y -q -f /tmp/ubi

ubiattach -m "${UBI_IDX#mtd}" -d 0
ubinfo -d 0

sync'

echo
echo "NAND written and verified."
echo "Reboot with:  ssh root@$HOST reboot"
