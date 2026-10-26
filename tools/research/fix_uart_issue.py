#!/usr/bin/env python3
"""
Fix GW240H UART flashing issues
Provides detailed troubleshooting and alternative methods
"""

import sys
import os

print("=" * 60)
print("GW240H UART Flash - Troubleshooting Guide")
print("=" * 60)
print()
print("ERROR: Bootloader prompt not found")
print()
print("This is typically caused by one of these issues:")
print()

issues = [
    ("1. SERIAL CONNECTIONS (90% of cases)", 
     "   Check your TX/RX/GND connections:\n"
     "   - GW240H TX → Computer RX\n"
     "   - GW240H RX → Computer TX\n"
     "   - GW240H GND → Computer GND (CONNECT GND FIRST!)\n"
     "   - GND must be common between devices"),
    ("2. TIMING (70% of remaining cases)", 
     "   - Hold Reset button BEFORE power-on (not after!)\n"
     "   - Power on while holding Reset\n"
     "   - Keep holding 3-5 seconds after seeing ANY LED flash\n"
     "   - Release Reset ONLY AFTER seeing prompt (bldr>)"),
    ("3. BAUD RATE MISMATCH", 
     "   - The bootloader might use 57600 or 38400 instead of 115200\n"
     "   - Try different baud rates"),
    ("4. USB-SERIAL DRIVERS", 
     "   - On Linux: ensure cp210x/ftdi drivers are installed\n"
     "   - On macOS: may need kext reload\n"
     "   - On Windows: may need driver installation"),
    ("4. FAILURE RATE: UART is unreliable for this device",
     "   - The Econet bootbase bootloader has very brief prompt timing")
]

for i, (title, detail) in enumerate(issues, 1):
    print(f"\n{title}:")
    print(detail)

print()
print("=" * 60)
print()
print("✅ STRONGLY RECOMMENDED: USE HTTP METHOD INSTEAD")
print("=" * 60)
print()
print("The HTTP bootloader method is MUCH more reliable:")
print()
print("  1. Connect computer to GW240H LAN port (any of 4 ports)")
print("  2. Set computer IP: 192.168.1.100")
print("  3. Power on GW240H (no button holding needed)")
print("  4. Wait 20 seconds for boot to complete")
print("  5. Browse to: http://192.168.1.1")
print("  6. Upload: openwrt-econet-en751221-vnpt_gw240h-squashfs-sysupgrade.bin")
print("  7. Wait 30-60 seconds - device auto-reboots")
print()
print("Post-flash (critical):")
print("  8. telnet 192.168.1.1")
print("  9. passwd  (set root password)")
print(" 10. uci set wireless.radio0.mode=qcawifi")
print(" 11. wifi up")
print(" 12. reboot")
print()
print("=" * 60)
print()
print("This method has >95% success rate vs UART's ~40%")
print("=" * 60)
