# Credits / Ghi công

## Project lead / Người thực hiện
- **@thaiteodai** — commissioned and led this port

## Prior work / Công việc trước đó
- **VNPT GW040H OpenWrt port** (same author) — the GW040H build proved the
  xmdm/UART staging flow, the 2RDH hybrid layout and the `ubiformat` step that
  this port follows:
  https://github.com/thaiteodai/gw040h-openwrt
- **vnptmodemresearch** (ResearcherPT) — VNPT GPON ONT firmware analysis, tools
  and reference dumps: https://github.com/ResearcherPT/vnptmodemresearch
  (telnet_password.py, romfileedit-h.py, asp-decoder.py, openwrt-initramfs-en751221,
  flashdump/, gw040ns-firmware)
- **OpenWrt Project** — build system, kernel, packages and the
  `target/linux/econet` target: https://openwrt.org/
- **Econet/Linux wiki** — tclinux/trx format and free-bootbase details:
  https://econet-linux.pkt.wiki/
- **MediaTek mt76 / mt7615** driver and firmware
- **ZyXEL trx/zytrx documentation** — reference for the JAMCRC/tclinux header layout

## Special thanks / Lời cảm ơn
- The OpenWrt econet target maintainers and contributors for EN751221 support
- Community members who published firmware dumps and analysis for VNPT ONTs
- @cuongDinh105, @ResearcherPT

Credit is given to all referenced work. Any omissions are accidental — please
open an issue to correct them.
