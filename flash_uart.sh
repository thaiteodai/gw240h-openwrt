#!/bin/sh
# Step 1 of the flash: stage the rescue initramfs and the hybrid over UART.
# Step 2 (after the rescue system is up at 192.168.1.1): ./tools/flash_ssh.sh
set -eu
cd "$(dirname "$0")"

python3 tools/xflash_gw240h.py

cat <<'EOF'

Rescue system should now be running from RAM at 192.168.1.1
(dropbear, root with an empty password). NAND has not been touched.

Next:
  ./tools/flash_ssh.sh
EOF
