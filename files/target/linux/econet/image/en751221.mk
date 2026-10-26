TRX_ENDIAN := be

# VNPT GW240H: 2RDH/tclinux image written to the 12 MiB tclinux slot, UBI on
# the 34 MiB rootfs_ubi (OEM "data") region. The trx produced here is only a
# carrier - build_hybrid*.py turns its kernel+UBI into the 2RDH image (so the
# bootbase still sees a valid kernel+rootfs CRC) and phaseE.py writes the UBI
# part onto rootfs_ubi with ubiformat. IMAGE_SIZE nonetheless drives the
# UBI_NAND_SIZE_LIMIT guard in append-ubi (IMAGE_SIZE - 20/1024*NAND -
# 4*BLOCKSIZE), which assumes the UBI sits inside this image and is therefore
# far too small for us; 15360k makes that guard allow the whole 12 MiB tclinux
# window. FACTORY_SIZE is the real, enforced limit.
define Device/vnpt_gw240h
  DEVICE_VENDOR := VNPT
  DEVICE_MODEL := GW240H
  DEVICE_DTS := en751221_vnpt_gw240h
  KERNEL_DECOMPRESSED_SIZE := 7672k
  KERNEL_SIZE := 4096k
  IMAGE_SIZE := 15360k
  FACTORY_SIZE := 12288k
  NAND_SIZE := 128m
  KERNEL := kernel-bin | append-dtb | tclinux-free-bootbase-jump | \
    check-size $$(KERNEL_DECOMPRESSED_SIZE) | lzma
  KERNEL_INITRAMFS := kernel-bin | append-dtb
  IMAGES := tclinux.trx sysupgrade.bin
  IMAGE/tclinux.trx := append-kernel | pad-to $$$$(KERNEL_SIZE) | append-ubi | \
    check-size $$$$(FACTORY_SIZE)
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  DEVICE_PACKAGES := kmod-mt7615e kmod-mt7615-firmware wpad-basic-mbedtls luci-light \
    kmod-gpio-button-hotplug kmod-leds-gpio kmod-ledtrig-netdev kmod-ledtrig-timer \
    kmod-hwmon-core ubi-utils f2fs-tools
endef
TARGET_DEVICES += vnpt_gw240h