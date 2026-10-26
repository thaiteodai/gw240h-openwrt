#!/usr/bin/env python3
"""
Post-flash verification for GW240H - similar to GW040H postflash_verify.py
"""

import serial
import time
import sys
import argparse

def wait_for_shell(ser, timeout=120):
    """Wait for OpenWrt shell prompt"""
    ser.timeout = 1
    start = time.time()
    buffer = b''
    
    print("Waiting for OpenWrt boot...")
    while time.time() - start < timeout:
        data = ser.read(1024)
        if data:
            buffer += data
            # Look for shell prompt
            if b'root@' in buffer and (b'#' in buffer or b'$' in buffer):
                return True
            if b'/ #' in buffer:
                return True
            # Keep buffer manageable
            if len(buffer) > 500:
                buffer = buffer[-500:]
        time.sleep(0.5)
    
    return False


def run_cmd(ser, cmd, wait=3):
    """Run command and return output"""
    ser.reset_input_buffer()
    ser.write((cmd + '\n').encode())
    ser.flush()
    time.sleep(wait)
    return ser.read_all().decode('utf-8', errors='ignore')


def verify_flash(ser):
    """Run verification checks"""
    checks = []
    
    # 1. Check OpenWrt version
    print("\n1. Checking OpenWrt version...")
    out = run_cmd(ser, "cat /etc/openwrt_release")
    print(out)
    checks.append(("OpenWrt version", "DISTRIB_ID" in out))
    
    # 2. Check MTD partitions
    print("\n2. Checking MTD partitions...")
    out = run_cmd(ser, "cat /proc/mtd")
    print(out)
    checks.append(("MTD partitions", "rootfs_ubi" in out))
    
    # 3. Check UBI volumes
    print("\n3. Checking UBI volumes...")
    out = run_cmd(ser, "ubinfo -a")
    print(out)
    checks.append(("UBI volumes", "rootfs" in out and "rootfs_data" in out))
    
    # 4. Check overlay
    print("\n4. Checking overlay filesystem...")
    out = run_cmd(ser, "df -h /overlay")
    print(out)
    out2 = run_cmd(ser, "mount | grep overlay")
    print(out2)
    checks.append(("Overlay mounted", "overlay" in out2))
    
    # 5. Check WiFi
    print("\n5. Checking WiFi radios...")
    out = run_cmd(ser, "iw dev")
    print(out)
    checks.append(("WiFi radios", "phy0" in out or "phy1" in out))
    
    out = run_cmd(ser, "ubus call network.wireless status")
    print(out)
    checks.append(("WiFi status", "up" in out.lower()))
    
    # 6. Check Ethernet
    print("\n6. Checking Ethernet ports...")
    out = run_cmd(ser, "ip link show")
    print(out)
    checks.append(("Ethernet interfaces", "eth0" in out or "lan1" in out))
    
    # 7. Check LuCI
    print("\n7. Checking LuCI web server...")
    out = run_cmd(ser, "netstat -ln | grep :80")
    print(out)
    out2 = run_cmd(ser, "ps | grep uhttpd")
    print(out2)
    checks.append(("LuCI running", ":80" in out or "uhttpd" in out2))
    
    # 8. Check LEDs
    print("\n8. Checking LED sysfs...")
    out = run_cmd(ser, "ls /sys/class/leds/")
    print(out)
    checks.append(("LEDs registered", len(out.strip()) > 0))
    
    # 9. Check buttons
    print("\n9. Checking button sysfs...")
    out = run_cmd(ser, "ls /sys/class/input/ 2>/dev/null; cat /proc/bus/input/devices 2>/dev/null | head -20")
    print(out)
    checks.append(("Buttons registered", "gpio-keys" in out or "input" in out))
    
    # 10. Check persistent config
    print("\n10. Testing persistent config...")
    run_cmd(ser, "uci set system.@system[0].hostname='GW240H-Test'")
    run_cmd(ser, "uci commit system")
    run_cmd(ser, "sync")
    time.sleep(1)
    out = run_cmd(ser, "uci get system.@system[0].hostname")
    print(out)
    checks.append(("Config persistence", "GW240H-Test" in out))
    
    # Summary
    print("\n" + "="*50)
    print("VERIFICATION SUMMARY")
    print("="*50)
    all_pass = True
    for name, result in checks:
        status = "PASS" if result else "FAIL"
        if not result:
            all_pass = False
        print(f"  {status}: {name}")
    
    print("="*50)
    if all_pass:
        print("ALL CHECKS PASSED!")
    else:
        print("SOME CHECKS FAILED!")
    
    return all_pass


def main():
    parser = argparse.ArgumentParser(description='Verify GW240H OpenWrt flash')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate')
    parser.add_argument('--timeout', type=int, default=120, help='Boot timeout')
    
    args = parser.parse_args()
    
    ser = serial.Serial(args.port, args.baud, timeout=1)
    
    try:
        if wait_for_shell(ser, args.timeout):
            print("Shell ready!")
            success = verify_flash(ser)
            sys.exit(0 if success else 1)
        else:
            print("ERROR: Shell not detected within timeout")
            sys.exit(1)
    finally:
        ser.close()


if __name__ == '__main__':
    main()