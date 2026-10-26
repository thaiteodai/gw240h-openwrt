#!/usr/bin/env python3
"""Build the GW240H 2RDH hybrid image from a freshly built tclinux.trx.

Same layout as the proven GW040H hybrid8 packager:

  [0x000000 .. 0x000100)  fresh 256-byte "2RDH" header
  [0x000100 .. 0x400000)  LZMA kernel copied from the built trx (its own
                          first 256 bytes, a zytrx header, are replaced)
  [0x400000 ..)           UBI payload copied verbatim

The built tclinux.trx from the econet target already contains the kernel in
the first 4 MiB region and the UBI at 0x400000; only the 256-byte leading
header has to be swapped for a 2RDH one so bootbase recognizes the slot.

Refuses to write an image with a missing/short UBI or a mismatched JAMCRC.
"""

import argparse
import struct
import sys
import zlib

HDR_LEN = 256
UBI_OFF = 0x400000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trx", required=True, help="built openwrt-...-squashfs-tclinux.trx")
    ap.add_argument("--out", required=True, help="output 2RDH hybrid image")
    args = ap.parse_args()

    built = open(args.trx, "rb").read()
    if len(built) < UBI_OFF + 0x20000:
        sys.exit("FATAL: trx is only %d bytes, no room for a UBI at %#x"
                 % (len(built), UBI_OFF))
    if built[UBI_OFF:UBI_OFF + 4] != b"UBI#":
        sys.exit("FATAL: no UBI# magic at %#x in %s (built image has no rootfs)"
                 % (UBI_OFF, args.trx))

    kernel_region = built[0:UBI_OFF - HDR_LEN]      # LZMA + zero pad, 0x3FFF00
    ubi = built[UBI_OFF:]
    content = kernel_region + ubi

    kernellen = len(kernel_region)
    rootfslen = len(ubi)
    totlen = HDR_LEN + kernellen + rootfslen
    crc = zlib.crc32(content) ^ 0xFFFFFFFF          # JAMCRC, as bootbase wants

    hdr = bytearray(HDR_LEN)
    hdr[0:4] = b"2RDH"
    struct.pack_into(">I", hdr, 4, HDR_LEN)
    struct.pack_into(">I", hdr, 8, totlen)
    struct.pack_into(">I", hdr, 12, crc)
    hdr[16:48] = b"G240DEVN00T001\n".ljust(32, b"\0")
    hdr[48:80] = b"003_000_000_003\n".ljust(32, b"\0")
    struct.pack_into(">I", hdr, 80, kernellen)
    struct.pack_into(">I", hdr, 84, rootfslen)
    struct.pack_into(">I", hdr, 88, 0)              # romfilelen
    hdr[92:124] = b"3 6035 122 0\n".ljust(32, b"\0")
    struct.pack_into(">I", hdr, 124, 0x80002000)    # loadaddr

    img = bytes(hdr) + content

    # verify exactly the way bootbase will
    v = memoryview(img)
    assert v[0:4] == b"2RDH"
    hdrlen, tl, vcrc = struct.unpack(">III", v[4:16])
    klen, rlen, romlen = struct.unpack(">III", v[80:92])
    loadaddr = struct.unpack(">I", v[124:128])[0]
    calc = zlib.crc32(bytes(v[HDR_LEN:HDR_LEN + klen + rlen])) ^ 0xFFFFFFFF
    assert hdrlen == HDR_LEN, hdrlen
    assert tl == HDR_LEN + klen + rlen == len(img)
    assert klen == UBI_OFF - HDR_LEN, hex(klen)
    assert rlen == rootfslen
    assert calc == vcrc, (hex(calc), hex(vcrc))
    assert loadaddr == 0x80002000
    assert v[UBI_OFF:UBI_OFF + 4] == b"UBI#"
    assert bytes(v[128:256]) == b"\0" * 128

    open(args.out, "wb").write(img)
    print("OK wrote %s (%d bytes)" % (args.out, len(img)))
    print("kernellen=0x%x rootfslen=0x%x totlen=0x%x crc=0x%08x"
          % (klen, rlen, tl, vcrc))


if __name__ == "__main__":
    main()
