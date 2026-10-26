#!/bin/bash
"""
GW240H UART Flash Troubleshooting Script
Helps diagnose why bootloader prompt isn't being detected
"""

set -e

echo "========================================="
echo "GW240H UART Flash Troubleshooting"
echo "========================================="
echo ""

# Step 1: Check serial port exists
echo "Step 1: Checking serial port..."
if [ -c "/dev/ttyUSB0" ]; then
    echo "  ✓ /dev/ttyUSB0 exists"
else
    echo "  ! /dev/ttyUSB0 not found"
    echo "  Available ports:"
    ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyS* 2>/dev/null || echo "  No serial ports found"
    echo ""
    read -p "Enter your serial port: " PORT
    PORT=${PORT:-/dev/ttyUSB0}
fi

# Step 2: Check pyserial
echo ""
echo "Step 2: Checking Python serial..."
python3 -c "import serial; print('  ✓ pyserial available')" 2>/dev/null || {
    echo "  ! pyserial not installed"
    echo "  Installing: pip3 install pyserial"
    pip3 install pyserial 2>/dev/null && echo "  ✓ Installed" || echo "  ✗ Failed to install"
}

# Step 3: Test raw serial connection
echo ""
echo "Step 3: Testing serial connection..."
echo "  Sending test character to $PORT..."
python3 -c "
import serial
try:
    s = serial.Serial('$PORT', 115200, timeout=2)
    s.write(b'C')  # Send xmodem start
    s.close()
    print('  ✓ Serial connection works - could receive data')
except Exception as e:
    print(f'  ! Serial error: {e}')
"

# Step 4: Check LED indications
echo ""
echo "Step 4: GW240H LED indicators..."
echo "  Expected behavior when holding Reset during power-on:"
echo "    - Power LED should illuminate"
echo "    - Internet/PON LEDs may flash"
echo "    - After 3-5 seconds, prompt should appear: 'bldr>' or '>'"
echo ""
read -p "  Did you hold Reset button during power-on? (y/n): " held_reset
if [ "$held_reset" = "y" ]; then
    echo "  Good, you held Reset during power-on"
else
    echo "  !! Critical: Must hold Reset button BEFORE and DURING power-on"
    echo "  - Disconnect power from GW240H"
    echo "  - Hold Reset button firmly"
    echo "  - Apply power while holding Reset"
    echo "  - Keep holding 3-5 seconds after seeing any LED activity"
fi

# Step 5: Try different baud rates
echo ""
echo "Step 5: Testing different baud rates..."
for baud in 115200 57600 38400 9600; do
    python3 -c "
import serial, time
try:
    s = serial.Serial('/dev/ttyUSB0', $baud, timeout=1)
    time.sleep(0.5)
    s.close()
    print(f'  ✓ Baud rate $baud: works')
except:
    print(f'  - Baud rate $baud: failed')
" 2>/dev/null
done

echo ""
echo "========================================="
echo "Most Likely Fixes"
echo "========================================="
echo ""
echo "1. HARDWARE CONNECTIONS (Most Common Issue):"
echo "   - GW240H TX → Computer RX"
echo "   - GW240H RX → Computer TX"
echo "   - GW240H GND → Computer GND (ESSENTIAL - connect GND first!)"
echo "   - Use quality USB-to-serial cable"
echo ""
echo "2. TIMING (Very Important):"
echo "   - Disconnect GW240H power"
echo "   - Hold Reset button DOWN"
        echo "   - Apply power while holding Reset"
echo "   - Keep holding 3-5 seconds after LED activity starts"
echo "   - Release Reset ONLY AFTER seeing the prompt"
echo ""
echo "3. TRY HTTP INSTEAD (Recommended if UART fails):"
echo "   - Connect computer to GW240H LAN port"
echo "   - Set IP: 192.168.1.100"
echo "   - Browse to: http://192.168.1.1"
echo "   - Upload: openwrt-econet-en751221-vnpt_gw240h-squashfs-sysupgrade.bin"
echo ""
echo "========================================="
