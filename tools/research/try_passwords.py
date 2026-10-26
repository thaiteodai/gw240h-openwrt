#!/usr/bin/env python3
"""Try common default passwords for VNPT GW240H via SSH"""
import subprocess
import sys

passwords = [
    "root",
    "admin", 
    "password",
    "12345678",
    "default",
    "1234",
    "888888",
    "99999999",
    "admin123",
    "support",
    "vnpt",
    "1234567890",
]

firmware = "/home/qyoo/gw240h-openwrt/images/openwrt-econet-en751221-vnpt_gw240h-squashfs-sysupgrade.bin"

print("=" * 60)
print("GW240H SSH Password Recovery")
print("=" * 60)
print(f"Target: admin@192.168.1.1")
print(f"Firmware: {firmware.split('/')[-1]}")
print()

for pwd in passwords:
    print(f"Trying password: '{pwd}'...")
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", 
         f"admin@192.168.1.1", f"echo 'SUCCESS'"],
        input=pwd,
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode == 0 and "SUCCESS" in result.stdout:
        print(f"\n✅ PASSWORD FOUND: '{pwd}'")
        print("\nNow running SCP to upload firmware...")
        
        # Try SCP with password via script
        scp_result = subprocess.run(
            ["scp", "-o", "BatchMode=yes", 
             f"admin@192.168.1.1:{firmware}", 
             f"/tmp/gw240h-sysupgrade.bin"],
            capture_output=True, text=True, timeout=30
        )
        
        if scp_result.returncode == 0:
            print("✅ Firmware uploaded via SCP!")
            print(f"File size: {__import__('os').path.getsize('/tmp/gw240h-sysupgrade.bin')} bytes")
        else:
            print(f"SCP output: {scp_result.stderr}")
        
        break
    elif "password" in result.stderr.lower() or "permission" in result.stderr.lower():
        print(f"  ❌ Failed: authentication rejected")
    else:
        print(f"  ? Output: {result.stderr[:100] if result.stderr else 'no error'}")

print("\n" + "=" * 60)
print("If no password worked, try manual SSH with these passwords:")
print("  root, admin, password, 12345678, default, support, vnpt")
print("=" * 60)
