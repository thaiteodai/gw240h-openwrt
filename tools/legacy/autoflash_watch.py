#!/usr/bin/env python3
"""Unattended GW240H flasher.

Waits for the USB-UART adapter, stages the rescue initramfs + the 2RDH hybrid
image in RAM, boots the rescue kernel, and lets phaseE write kernel + UBI to
NAND. Retries forever-ish, so it is safe to plug the cable / power-cycle the
router late: the loop will pick it up.

  log:        /tmp/opencode/autoflash.log
  final flag: /tmp/opencode/AUTOFLASH_DONE  (phaseE reported success)

Usage:  nohup python3 -u tools/autoflash_watch.py &
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = "/tmp/opencode/autoflash.log"
DONE = "/tmp/opencode/AUTOFLASH_DONE"
PORT = "/dev/ttyUSB0"

# Rescue initramfs built from the GW240H tree itself.
INIT = os.environ.get(
    "INIT_F",
    os.path.join(ROOT,
                 "images/openwrt-econet-en751221-vnpt_gw240h-initramfs-kernel.bin"))
FW = os.environ.get("FW_F", os.path.join(ROOT, "images/openwrt-gw240h-hybrid.trx"))


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def port_ready():
    if not os.path.exists(PORT):
        return False
    try:
        import serial
        s = serial.Serial(PORT, 115200, timeout=0.2)
        s.close()
        return True
    except Exception:
        return False


def run(cmd, env, timeout):
    log("RUN %s" % " ".join(os.path.basename(c) for c in cmd))
    deadline = time.time() + timeout
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, bufsize=1)
    assert p.stdout is not None
    for raw in iter(p.stdout.readline, b""):
        log("  | " + raw.decode("utf-8", "replace").rstrip("\n"))
        if time.time() > deadline:
            log("TIMEOUT after %ss -> killing" % timeout)
            p.kill()
            p.wait()
            return 124
    p.wait()
    log("exit=%d" % p.returncode)
    return p.returncode


def main():
    os.makedirs("/tmp/opencode", exist_ok=True)
    for f in (INIT, FW):
        if not os.path.exists(f):
            log("FATAL missing image %s" % f)
            return 2
    log("=== unattended GW240H flash start ===")
    log("initramfs: %s (%d bytes)" % (INIT, os.path.getsize(INIT)))
    log("hybrid   : %s (%d bytes)" % (FW, os.path.getsize(FW)))

    env = dict(os.environ, INIT_F=INIT, FW_F=FW)

    for round_no in range(1, 21):
        while not port_ready():
            log("waiting for %s (plug the USB-UART adapter)..." % PORT)
            time.sleep(10)

        log("round %d: port present" % round_no)
        rc = run([sys.executable, "-u", os.path.join(HERE, "xflash_gw240h.py")],
                 env, 7200)
        if rc != 0:
            if rc in (14, 15):
                # jump fault / no boot: staged RAM cannot be trusted
                try:
                    os.remove("/tmp/opencode/xflash_state.json")
                    log("cleared staging state (bad boot)")
                except OSError:
                    pass
            log("staging failed (rc=%d); will retry after 30s" % rc)
            time.sleep(30)
            continue

        log("rescue kernel up -> writing NAND")
        rc = run([sys.executable, "-u", os.path.join(HERE, "phaseE_gw240h.py")],
                 env, 2400)
        if rc == 0:
            open(DONE, "w").write("ok %s\n" % time.strftime("%F %T"))
            log("=== FLASH COMPLETE ===")
            return 0
        log("phaseE failed (rc=%d); retrying from staging" % rc)
        time.sleep(30)

    log("=== giving up after 20 rounds ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
