#!/bin/sh
# Build OpenWrt for the VNPT GW240H from an existing OpenWrt tree.
#
#   OPENWRT_DIR=/path/to/openwrt ./build.sh
#
# Defaults to ../openwrt (a sibling checkout). The tree must already contain
# the econet/en751221 target (OpenWrt SNAPSHOT; this build used Linux 6.18).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
OPENWRT_DIR=${OPENWRT_DIR:-$HERE/../openwrt}

if [ ! -d "$OPENWRT_DIR/target/linux/econet" ]; then
	echo "error: $OPENWRT_DIR is not an OpenWrt tree with the econet target" >&2
	echo "clone it first:" >&2
	echo "  git clone https://git.openwrt.org/openwrt/openwrt.git \"$OPENWRT_DIR\"" >&2
	exit 1
fi

echo "=== overlaying files/ onto $OPENWRT_DIR"
rsync -a "$HERE/files/" "$OPENWRT_DIR/"

if [ ! -f "$OPENWRT_DIR/.config" ]; then
	echo "=== no .config yet — pick: Target: Econet -> EN751221 -> VNPT GW240H"
	make -C "$OPENWRT_DIR" menuconfig
fi

echo "=== building"
make -C "$OPENWRT_DIR" -j"$(nproc)"

TRX="$OPENWRT_DIR/bin/targets/econet/en751221/openwrt-econet-en751221-vnpt_gw240h-squashfs-tclinux.trx"
echo "=== packaging the 2RDH hybrid"
python3 "$HERE/tools/build_hybrid_gw240h.py" \
	--trx "$TRX" \
	--out "$HERE/images/openwrt-gw240h-hybrid.trx"

echo "done: $HERE/images/openwrt-gw240h-hybrid.trx"
