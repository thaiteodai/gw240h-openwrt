#!/usr/bin/env python3
"""phaseE -- run on the rescue Linux (booted from RAM by xflash12.py).

Assumes the rescue kernel is already booting on /dev/ttyUSB0. Waits for a
root shell, reads the firmware that xflash12 staged at physical 0x05000000
(KSEG0 0x85000000) back out through /dev/mem, verifies md5 against the local
file, then:

  1. writes the 2RDH/kernel image to the NAND 'tclinux' partition (flash
     0x80000, exactly where the 2RDH header must live), verifies the kernel
     readback, and mirrors it to 'tclinux_alt';
  2. writes the UBI payload (image bytes after the 4 MiB kernel pad) to the
     34 MiB 'rootfs_ubi' partition with ubiformat. ubiformat is required
     here: unlike the remap-aware tclinux window this partition has no
     econet,enable-remap, so a plain 'mtd write' would lay the image down
     linearly and corrupt it on any factory bad block. ubiformat erases the
     partition, skips bad PEBs and writes the image PEB by PEB.

Only ONE process may hold the serial port at a time.

Exit: 0 ok | 21 no shell | 22 no /dev/mem | 23 dd failed | 24 md5 mismatch
      | 25 mtd write failed | 26 readback mismatch (no reboot performed)
      | 27 no boot signal after flash | 29 UBI write/verify failed
"""
import os, re, sys, time, hashlib, serial

PORT, BAUD = "/dev/ttyUSB0", 115200
FW_F    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../images/openwrt-gw240h-hybrid.trx")
LOG_F   = "/tmp/opencode/phaseE.log"
BOOT_F  = "/tmp/opencode/phaseE_boot.txt"
FW_PHYS = 0x05000000          # 0x85000000 & 0x1fffffff  (KSEG0 -> phys)
BLK     = 65536
PART    = "tclinux"
ALT     = "tclinux_alt"
UBI_PART = "rootfs_ubi"       # 34 MiB region that hosts the whole UBI now
KERN_LEN = 0x400000           # kernel region of the image

raw  = open(FW_F, "rb").read()
MD5  = hashlib.md5(raw).hexdigest()
SIZE = len(raw)
SKIP = FW_PHYS // BLK
COUNT = SIZE // BLK
assert COUNT * BLK == SIZE, (COUNT * BLK, SIZE)
MD5_KERN = hashlib.md5(raw[:KERN_LEN]).hexdigest()
KERN_BLKS = KERN_LEN // BLK

s = serial.Serial(PORT, BAUD, timeout=0.4)
T0 = time.monotonic()


def log(m):
    line = "[%7.1fs] %s" % (time.monotonic() - T0, m)
    print(line, flush=True)
    with open(LOG_F, "a") as f:
        f.write(line + "\n")


def rd(dur):
    t = time.monotonic()
    b = b""
    while time.monotonic() - t < dur:
        c = s.read(4096)
        if c:
            b += c
    return b


log("phaseD start: %s  size=%d md5=%s" % (FW_F, SIZE, MD5))

# ---------------------------------------------------------------- shell wait
PROMPT_RE = re.compile(rb"(?:^|[\r\n])[^\r\n]{0,120}?[#$]\s*$")


def wait_shell(timeout=330):
    t = time.monotonic()
    buf = b""
    while time.monotonic() - t < timeout:
        seg = rd(1.0)
        if seg:
            buf += seg
            with open(BOOT_F, "ab") as f:
                f.write(seg)
        low = buf[-600:]
        if b"login:" in low[-200:]:
            log("login prompt -> sending 'root'")
            s.write(b"root\n")
            time.sleep(0.6)
            continue
        if b"Password:" in low[-200:]:
            s.write(b"\n")
            time.sleep(0.6)
            continue
        if PROMPT_RE.search(low):
            return True, buf
        s.write(b"\n")
    return False, buf


ok, boot = wait_shell(330)
if not ok:
    log("FATAL: no shell prompt within window")
    sys.exit(21)
log("shell reached (%d bytes of boot log)" % len(boot))


def sh(cmd, timeout=120):
    sh.n = getattr(sh, "n", 0) + 1
    tag = "__PD%d" % sh.n
    s.reset_input_buffer()
    s.write(('echo "%s_B"; %s; echo "%s_RC=$?"' % (tag, cmd, tag)).encode() + b"\n")
    buf = b""
    t = time.monotonic()
    rx = re.compile(re.escape(tag.encode()) + rb"_RC=(\d+)")
    while time.monotonic() - t < timeout:
        c = s.read(1024)
        if c:
            buf += c
            m = rx.search(buf)
            if m:
                out = buf[:m.start()]
                out = out.rsplit(tag.encode() + b"_B", 1)[-1]
                return int(m.group(1)), out.replace(b"\r", b"")
    return None, buf.replace(b"\r", b"")


def dec(b):
    return b.decode("utf-8", "replace").strip()


# the prompt regex can match mid-boot noise; prove the shell really runs cmds
confirmed = False
for _ in range(30):
    rc, out = sh("true", timeout=15)
    if rc is not None:
        confirmed = True
        break
    time.sleep(2)
if not confirmed:
    log("FATAL: shell prompt seen but commands do not execute")
    sys.exit(21)
log("shell confirmed responsive")

# silence our own command echo so the output stream stays clean
sh("stty -echo 2>/dev/null; true", timeout=30)

rc, out = sh("cat /proc/mtd; echo ---; uname -a", timeout=60)
log("/proc/mtd + uname:\n%s" % dec(out))

# ------------------------------------------------- WiFi bring-up pre-check
# The whole point of this rebuild is the MT7615E on PCIe1. Confirm the driver
# bound and a valid (non-empty) EEPROM was read before we destroy the working
# NAND image. SKIP_WIFI_CHECK=1 bypasses the gate.
import os as _os
skip_wifi = _os.environ.get("SKIP_WIFI_CHECK") == "1"

rc, out = sh("ls /sys/class/ieee80211/ 2>&1; echo ---PHYEND", timeout=30)
phys = dec(out)
log("ieee80211 phys:\n%s" % phys)

rc, out = sh("dmesg | grep -i -E 'mt7615|mt76|pci 0001|eeprom' | tail -40",
             timeout=60)
dmesg_wifi = dec(out)
log("wifi dmesg:\n%s" % dmesg_wifi)

wifi_ok = ("phy0" in phys) and ("Invalid MAC address" not in dmesg_wifi)
if not wifi_ok and not skip_wifi:
    log("FATAL: MT7615E not usable (phy0=%s, bad-eeprom=%s) -- NOT flashing "
        "(device stays on the current NAND image)"
        % ("phy0" in phys, "Invalid MAC address" in dmesg_wifi))
    sys.exit(28)
log("WiFi pre-check: %s" % ("OK" if wifi_ok else "skipped/failed (gate bypassed)"))


# ------------------------------------------------- download fw over HTTP
# The GW240H initramfs has no CONFIG_DEVMEM, so the image is pulled from the
# computer over the LAN instead of being read back from staged RAM.
SRV = _os.environ.get("FW_SRV", "192.168.1.2")
PORT_SRV = _os.environ.get("FW_PORT", "8000")
URL = "http://%s:%s/%s" % (SRV, PORT_SRV, _os.path.basename(FW_F))

rc, out = sh("rm -f /tmp/fw; which wget uclient-fetch curl nc 2>&1", timeout=30)
log("download tools: %s" % dec(out).replace("\n", " "))

rc, out = sh("wget -O /tmp/fw %s 2>&1 || uclient-fetch -O /tmp/fw %s 2>&1 "
             "|| curl -s -o /tmp/fw %s" % (URL, URL, URL), timeout=900)
log("download rc=%s out=%s" % (rc, dec(out)[-300:]))
rc, out = sh("ls -l /tmp/fw", timeout=30)
if rc != 0:
    log("FATAL: download failed (no wget/uclient-fetch/curl or no route)")
    sys.exit(22)

rc, out = sh("ls -l /tmp/fw; md5sum /tmp/fw", timeout=180)
log("staged: %s" % dec(out))
m = re.search(rb"([0-9a-f]{32})", out)
if not m:
    log("FATAL: could not parse md5 of /tmp/fw")
    sys.exit(24)
if m.group(1).decode() != MD5:
    log("FATAL: md5 mismatch: got %s want %s (download corrupt/truncated)"
        % (m.group(1).decode(), MD5))
    sys.exit(24)
log("downloaded image verified md5 OK")

# ---------------------------------------------------------------- mtd index
def mtd_index(name, attempts=5):
    """Look the partition up in /proc/mtd, retrying: incremental serial reads
    of that file are flaky on this board and occasionally come back short."""
    needle = ('"%s"' % name).encode()
    for attempt in range(1, attempts + 1):
        rc, out = sh("cat /proc/mtd", timeout=30)
        for line in out.split(b"\n"):
            if needle in line:
                mm = re.match(rb"(mtd\d+):", line.strip())
                if mm:
                    return mm.group(1).decode()
        log("mtd_index(%s): attempt %d/%d saw no match, retrying"
            % (name, attempt, attempts))
        time.sleep(1.0)
    return None


idx = mtd_index(PART)
log("%s device: %s" % (PART, idx))
if not idx:
    log("FATAL: no %s partition in /proc/mtd" % PART)
    sys.exit(25)

# detach any UBI so the tclinux slots can be written without interference
sh("ubidetach -d 0 2>/dev/null; true", timeout=30)

# ---------------------------------------------------------------- write fw
rc, out = sh("mtd write /tmp/fw %s 2>&1" % PART, timeout=1500)
log("mtd write %s rc=%s out=%s" % (PART, rc, dec(out)))
if rc != 0:
    log("FATAL: mtd write %s failed" % PART)
    sys.exit(25)

# verify kernel region readback
rc, out = sh("dd if=/dev/%s bs=%d count=%d 2>/dev/null | md5sum"
             % (idx, BLK, KERN_BLKS), timeout=400)
got = re.search(rb"([0-9a-f]{32})", out)
log("readback kernel-region md5: %s (want %s)"
    % (got.group(1).decode() if got else "?", MD5_KERN))
if not got or got.group(1).decode() != MD5_KERN:
    log("readback mismatch -- rewriting once")
    sh("mtd write /tmp/fw %s 2>&1" % PART, timeout=1500)
    rc, out = sh("dd if=/dev/%s bs=%d count=%d 2>/dev/null | md5sum"
                 % (idx, BLK, KERN_BLKS), timeout=400)
    got = re.search(rb"([0-9a-f]{32})", out)
    if not got or got.group(1).decode() != MD5_KERN:
        log("FATAL: readback still wrong (%s) -- NOT rebooting"
            % (got.group(1).decode() if got else "?"))
        sys.exit(26)
log("readback verified OK")

# ---------------------------------------------------------------- alt copy
# On the GW240H the bootbase runs with "boot flag = 1" and boots the image
# from tclinux_alt (flash 0x1e80000), so this copy is mandatory and must be
# verified, not best-effort.
rc, out = sh("mtd write /tmp/fw %s 2>&1" % ALT, timeout=1500)
log("mtd write %s rc=%s out=%s" % (ALT, rc, dec(out)))
alt_idx = mtd_index(ALT)
log("%s device: %s" % (ALT, alt_idx))
if rc != 0 or not alt_idx:
    log("retrying %s once" % ALT)
    rc, out = sh("mtd write /tmp/fw %s 2>&1" % ALT, timeout=1500)
    log("mtd write %s retry rc=%s out=%s" % (ALT, rc, dec(out)))
if rc != 0:
    log("FATAL: mtd write %s failed -- bootbase boots this slot, NOT rebooting"
        % ALT)
    sys.exit(27)
rc, out = sh("dd if=/dev/%s bs=%d count=%d 2>/dev/null | md5sum"
             % (alt_idx, BLK, KERN_BLKS), timeout=400)
got = re.search(rb"([0-9a-f]{32})", out)
log("readback alt-slot kernel md5: %s (want %s)"
    % (got.group(1).decode() if got else "?", MD5_KERN))
if not got or got.group(1).decode() != MD5_KERN:
    log("retrying %s once after readback mismatch" % ALT)
    sh("mtd write /tmp/fw %s 2>&1" % ALT, timeout=1500)
    rc, out = sh("dd if=/dev/%s bs=%d count=%d 2>/dev/null | md5sum"
                 % (alt_idx, BLK, KERN_BLKS), timeout=400)
    got = re.search(rb"([0-9a-f]{32})", out)
    if not got or got.group(1).decode() != MD5_KERN:
        log("FATAL: alt-slot readback wrong (%s) -- NOT rebooting"
            % (got.group(1).decode() if got else "?"))
        sys.exit(27)
log("alt slot verified OK")

# ------------------------------------------------------------------- UBI
# The UBI payload is the tail of the staged image (everything after the
# 4 MiB kernel pad). Pull it out and ubiformat it onto the remap-less
# rootfs_ubi window (34 MiB, flash 0x2a80000, right after the boot slot).
ubi_idx = mtd_index(UBI_PART)
log("%s device: %s" % (UBI_PART, ubi_idx))
if not ubi_idx:
    log("FATAL: no %s partition in /proc/mtd" % UBI_PART)
    sys.exit(29)

rc, out = sh("dd if=/tmp/fw of=/tmp/ubi bs=%d skip=%d 2>&1"
             % (BLK, KERN_BLKS), timeout=300)
log("ubi extract rc=%s out=%s" % (rc, dec(out)))
if rc != 0:
    log("FATAL: dd extraction of the UBI payload failed")
    sys.exit(29)

# ubiformat refuses to run while the MTD is attached to a UBI device
sh("ubidetach -d 0 2>/dev/null; ubidetach -m %d 2>/dev/null; true"
   % int(ubi_idx[3:]), timeout=60)

rc, out = sh("ubiformat /dev/%s -y -q -f /tmp/ubi 2>&1" % ubi_idx,
             timeout=1800)
log("ubiformat %s rc=%s out=%s" % (ubi_idx, rc, dec(out)))
if rc != 0:
    log("FATAL: ubiformat of %s failed" % ubi_idx)
    sys.exit(29)

# bring the freshly formatted UBI up and confirm both volumes exist
sh("ubidetach -d 0 2>/dev/null; true", timeout=60)
rc, out = sh("ubiattach -m %d -d 0 2>&1; ubinfo -d 0 2>&1"
             % int(ubi_idx[3:]), timeout=300)
log("ubi volume check rc=%s out=%s" % (rc, dec(out)))
if rc != 0 or b"rootfs_data" not in out or b"rootfs" not in out:
    log("FATAL: rootfs/rootfs_data volume missing after ubiformat")
    sys.exit(29)
sh("ubidetach -d 0 2>/dev/null; true", timeout=60)
log("UBI payload written to %s and verified" % ubi_idx)

sh("sync", timeout=90)

# ---------------------------------------------------------------- reboot
log("rebooting...")
s.reset_input_buffer()
s.write(b"reboot\n")
buf = b""
t = time.monotonic()
seen_banner = False
while time.monotonic() - t < 240:
    c = s.read(4096)
    if c:
        buf += c
        with open(BOOT_F, "ab") as f:
            f.write(c)
        if not seen_banner and (b"OpenWrt" in buf or b"procd" in buf
                                or b"BusyBox" in buf):
            seen_banner = True
            log("post-flash boot banner seen")
        if seen_banner and (b"Please press Enter" in buf[buf.rfind(b"procd") - 200:]
                            if b"procd" in buf else False):
            break

tail = buf[-4000:].decode("utf-8", "replace")
log("post-flash boot capture (%d bytes):\n%s" % (len(buf), tail))

if b"Kernel panic" in buf or b"Exception happen" in buf or b"Undefined Exception" in buf:
    log("RESULT: post-flash boot FAILED")
    sys.exit(27)
if seen_banner or b"login:" in buf or PROMPT_RE.search(buf[-600:]) or b"procd: - init -" in buf:
    log("RESULT: POST-FLASH BOOT OK")
    sys.exit(0)
log("RESULT: no boot signal")
sys.exit(27)
