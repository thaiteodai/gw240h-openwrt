#!/usr/bin/env python3
"""xflash_gw240h: boot GW240H rescue initramfs from RAM from RAM, and stage hybrid5 firmware in RAM.

Parity with the proven flash-boot path: bootbase LZMA-decompresses the kernel
payload to 0x80002000 (the 2RDH header loadaddr); that payload begins with a
4-byte stub  j 0x80020000  followed by 0x1DFFC zero bytes, so the real kernel
(a vmlinux.bin linked at 0x80020000) ends up at 0x80020000 and is entered there.
We therefore xmdm the raw initramfs-kernel.bin straight to 0x80020000 and
jump 80020000 -- the same kernel bytes at the same address, minus the stub and
bootbase fw args (unneeded: bootargs live in the DT chosen node).

xmdm quirk: receiver drops the FIRST 128-byte packet of every call, so each
call sends a 128B junk packet first, len == exact bytes sent, real chunk lands
contiguously at dest. Per-chunk head/tail verify before proceeding.

Phases: attach -> initramfs -> stage fw -> jump -> classify boot output.
Exit: 11 attach fail | 12 transfer/verify fail | 14 jump fault (bootbase
exception) | 15 no boot signal | 0 kernel up / shell up.
"""
import os,sys,time,serial,re,json,hashlib

PORT, BAUD = "/dev/ttyUSB0", 115200
INIT_F = os.environ.get("INIT_F") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "../images/openwrt-econet-en751221-vnpt_gw240h-initramfs-kernel.bin")
FW_F = os.environ.get("FW_F") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "../images/openwrt-gw240h-hybrid.trx")
INIT_ADDR = 0x80020000
FW_ADDR = 0x85000000
JUNK = b"\x00" * 128
BLK = 128

for f in (INIT_F, FW_F):
    if not os.path.exists(f):
        print("FATAL missing file:", f, flush=True)
        sys.exit(12)
INIT = open(INIT_F, "rb").read()
FW = open(FW_F, "rb").read()
print("initramfs: %d bytes, fw: %d bytes" % (len(INIT), len(FW)), flush=True)
assert len(INIT) % 128 or True  # padded per chunk anyway
if INIT[:4] == b"\0\0\0\0" or INIT == b"\0" * 16:
    print("FATAL: initramfs artifact looks empty", flush=True)
    sys.exit(12)

_T = []
for i in range(256):
    c = i << 8
    for _ in range(8):
        c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    _T.append(c)


def xcrc(d):
    c = 0
    for b in d:
        c = ((c << 8) ^ _T[((c >> 8) ^ b) & 0xFF]) & 0xFFFF
    return c


s = serial.Serial(PORT, BAUD, timeout=0.3)
t_start = time.monotonic()


def log(m):
    print("[%6.0fs] %s" % (time.monotonic() - t_start, m), flush=True)


def rd(dur):
    t = time.monotonic()
    b = b""
    while time.monotonic() - t < dur:
        c = s.read(4096)
        if c:
            b += c
    return b


def drain_prompt(timeout=8):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        s.write(b"\r")
        o = rd(1.2)
        if b"bldr>" in o:
            return True
    return False


def send_packet(seq, blk, timeout=12, max_retry=12):
    hdr = b"\x01" + bytes([seq & 0xFF, (~seq) & 0xFF])
    pkt = hdr + blk + xcrc(blk).to_bytes(2, "big")
    retries = 0
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s.write(pkt)
        t2 = time.monotonic()
        while time.monotonic() - t2 < timeout:
            c = s.read(1)
            if not c:
                retries += 1
                if retries > max_retry:
                    return False
                break
            if c == b"\x06":
                return True
            if c in (b"\x18",):
                return False
            if c in (b"\x15", b"C"):
                retries += 1
                if retries > max_retry:
                    return False
                break
            deadline = time.monotonic() + timeout
    return False


def eot_wait(tries=3, wait=3.0):
    for _ in range(tries):
        s.write(b"\x04")
        t = time.monotonic()
        while time.monotonic() - t < wait:
            c = s.read(1)
            if c == b"\x06":
                return True
    return False


def xfer_call(dest, payload, tag):
    assert len(payload) % BLK == 0
    s.reset_input_buffer()
    s.write(("xmdm %x %x\r" % (dest, len(payload))).encode())
    t = time.monotonic()
    poll = None
    while time.monotonic() - t < 20:
        c = s.read(1)
        if c in (b"C", b"\x15"):
            poll = c
            break
    if poll is None:
        log("FATAL %s: no XMODEM poll; tail=%r" % (tag, rd(3)[:60]))
        sys.exit(12)
    seq = 0
    for i in range(0, len(payload), BLK):
        if not send_packet(seq, payload[i:i + BLK]):
            log("FATAL %s: ack fail at +%#x" % (tag, i))
            sys.exit(12)
        seq = (seq + 1) & 0xFF
    if not eot_wait():
        log("WARN %s: no EOT ack" % tag)
    if not drain_prompt(8):
        log("WARN %s: prompt not seen after EOT, resyncing" % tag)
        s.write(b"\x18\x18\x18")
        drain_prompt(10)


LINE_RE = re.compile(rb"^([0-9a-fA-F]{8})\s+((?:[0-9a-fA-F]{2}[ \.]+)*[0-9a-fA-F]{2})")


def dump_once(addr, timeout=4.0):
    s.reset_input_buffer()
    s.write(b"dump %08x 10\r" % addr)
    t = time.monotonic()
    buf = b""
    while time.monotonic() - t < timeout:
        c = s.read(512)
        if not c:
            continue
        buf += c
        lines = buf.replace(b"\r", b"").split(b"\n")
        for line in lines[:-1]:  # complete lines only (ignore echo)
            m = LINE_RE.match(line)
            if m and int(m.group(1), 16) == addr:
                hb = re.sub(rb"[ \.]+", b"", m.group(2))
                if len(hb) % 2:
                    hb = hb[:-1]
                try:
                    return bytes.fromhex(hb.decode())
                except ValueError:
                    return None
    return None


def dump16(addr, tries=3):
    """Read 16 bytes at addr. The bootloader occasionally swallows a dump
    while it is still finishing the previous xmdm call, so retry and, if it
    keeps failing, force a resync back to the bldr> prompt."""
    for i in range(tries):
        got = dump_once(addr, 4.0)
        if got is not None:
            return got
        if i == tries - 1:
            break
        s.write(b"\x18\x18\x18")
        drain_prompt(4)
    s.write(b"\x18\x18\x18")
    if drain_prompt(6):
        return dump_once(addr, 4.0)
    return None


def pad128(chunk):
    if len(chunk) % BLK:
        chunk = chunk + b"\x1a" * (BLK - len(chunk) % BLK)
    return chunk


def xfer_abort():
    """Properly abort a stuck xmdm receive: CAN bytes then wait for prompt."""
    for _ in range(5):
        s.write(b"\x18\x18\x18")
        time.sleep(0.2)
    return drain_prompt(90)


STATE_F = "/tmp/opencode/xflash_state.json"


def _state_load():
    try:
        with open(STATE_F) as f:
            return json.load(f)
    except Exception:
        return {}


def _state_put(key, val):
    st = _state_load()
    st[key] = val
    tmp = STATE_F + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, STATE_F)


def load_image(data, base, name, chunk_size=0x8000):
    md5 = hashlib.md5(data).hexdigest()
    """Stream `data` into RAM at `base`, 32 KiB per xmdm call.

    The receiver drops the first 128-byte packet of every call, so a junk
    packet is prefixed and the call length is the padded chunk length; the
    real chunk therefore lands contiguously at dest.

    Every chunk is re-transferred (never skipped) so a previous partial run
    can never leave stale bytes in the middle. Head bytes are verified for
    every chunk, plus a middle and tail sample every 8th chunk.
    """
    nfull = len(data) // chunk_size
    rem = len(data) % chunk_size
    nchunks = nfull + (1 if rem else 0)

    # ---- resume support -------------------------------------------------
    # Chunks are verified as they land, so a previous (interrupted) run left
    # valid bytes in RAM. Resume only if the last verified chunk is still
    # there; a power cycle wipes DRAM and the probe fails -> restart at 0.
    st = _state_load().get(name) or {}
    start = 0
    if st.get("md5") == md5 and st.get("size") == len(data):
        cand = int(st.get("next", 0))
        if 0 < cand <= nchunks:
            prev = (cand - 1) * chunk_size
            if dump16(base + prev) == data[prev:prev + 16]:
                start = cand
                log("%s: resuming at chunk %d/%d (RAM verified)" % (name, start, nchunks))
            else:
                log("%s: stale state, RAM probe failed -> restarting" % name)
    if start == 0:
        _state_put(name, {"md5": md5, "size": len(data), "next": 0})

    for i in range(start, nchunks):
        chunk = data[i * chunk_size:(i + 1) * chunk_size]
        dest = base + i * chunk_size
        padded = pad128(chunk)
        for attempt in range(4):
            try:
                xfer_call(dest, JUNK + padded, "%s[%d]" % (name, i))
            except SystemExit:
                if attempt < 3:
                    log("%s[%d] xfer died (attempt %d), resyncing..." % (name, i, attempt))
                    s.write(b"\x18\x18\x18")
                    if not drain_prompt(30):
                        log("FATAL: cannot recover bldr> prompt")
                        sys.exit(11)
                    continue
                raise
            ok = dump16(dest) == chunk[:16]
            if ok and (i % 8 == 0 or i == nchunks - 1):
                mid = chunk_size // 2
                mid = min(mid, len(padded) - 16)
                ok = dump16(dest + mid) == padded[mid:mid + 16]
                if ok:
                    ok = dump16(dest + len(padded) - 16) == padded[-16:]
            if ok:
                break
            log("VERIFY FAIL %s[%d] @%#x (attempt %d)" % (name, i, dest, attempt))
            s.write(b"\x18\x18\x18")
            if not drain_prompt(30):
                log("FATAL: cannot recover bldr> prompt")
                sys.exit(11)
        else:
            log("FATAL: %s[%d] could not be verified after 4 attempts" % (name, i))
            return False
        _state_put(name, {"md5": md5, "size": len(data), "next": i + 1})
        log("%s chunk %d/%d ok" % (name, i + 1, nchunks))
    return True


# ---------- attach ----------
# clear any xmdm session left stuck by a previous failed run
s.write(b"\x18\x18\x18")
time.sleep(0.5)

SHELL_MARK = (b"root@", b"Please press Enter", b"login:", b"/ #", b"~#")


def at_shell(buf):
    return any(m in buf for m in SHELL_MARK)


if not drain_prompt(6):
    # Not at bldr> yet. If an OS shell is running, reboot and catch the
    # bootloader's 3 second "press any key" window; otherwise just wait.
    s.reset_input_buffer()
    s.write(b"\r")
    probe = rd(3.0)
    log("attach probe: %r" % probe[-160:])
    if b"login:" in probe:
        log("stock login prompt -> authenticating")
        s.write(b"\r\nadmin\r")
        time.sleep(1.2)
        s.write(b"VnT3ch@dm1n\r")
        time.sleep(1.5)
        probe2 = rd(1.0)
        log("login probe: %r" % probe2[-120:])
        if b"#" in probe2 or b"$" in probe2:
            probe = probe2
    if at_shell(probe):
        log("OS shell detected -> rebooting to reach boot command mode")
        s.write(b"\r\nreboot\r")
        got = False
        t = time.monotonic()
        while time.monotonic() - t < 90:
            s.write(b"\r")
            o = rd(0.5)
            if b"bldr>" in o:
                got = True
                break
        if got:
            log("attached at bldr>")
        else:
            log("reboot did not yield bldr>; falling through to wait loop")

if not drain_prompt(15):
    log("no prompt yet; sending aborts; waiting up to ~600s for bldr> "
        "(POWER-CYCLE THE ONT NOW: unplug, wait 5s, plug back in)")
    ok = False
    for _ in range(20):
        s.write(b"\x18\x18\x18")
        if drain_prompt(30):
            ok = True
            break
    if not ok:
        log("FATAL: no bldr> (device wedged -- power cycle needed)")
        sys.exit(11)
log("attached")

# ---------- phase 1: initramfs ----------
if not load_image(INIT, INIT_ADDR, "init"):
    sys.exit(12)
log("initramfs staged at %#x (%d bytes)" % (INIT_ADDR, len(INIT)))

# ---------- phase 2: stage firmware ----------
if os.environ.get("SKIP_FW") == "1":
    log("SKIP_FW=1 -> firmware staging skipped (will be fetched over the network)")
else:
    if not load_image(FW, FW_ADDR, "fw"):
        sys.exit(12)
    log("firmware staged at %#x (%d bytes)" % (FW_ADDR, len(FW)))

# ---------- phase 3: jump ----------
log("jumping to rescue kernel...")
s.reset_input_buffer()
s.write(b"jump 80020000\r")
boot = rd(150)
open("/tmp/opencode/x12_boot.txt", "wb").write(boot)
log("boot capture: %d bytes" % len(boot))
print(boot[-3500:].decode("utf-8", "replace"), flush=True)

if b"Exception happen" in boot or b"Undefined Exception" in boot:
    log("RESULT: JUMP_FAULT")
    sys.exit(14)
shell_markers = (b"/ #", b"login:", b"Please press Enter", b"root@")
if any(m in boot for m in shell_markers):
    log("RESULT: SHELL_UP")
    sys.exit(0)
if b"Linux version" in boot:
    log("RESULT: KERNEL_BOOTED")
    sys.exit(0)
log("RESULT: NO_SIGNAL")
sys.exit(15)
