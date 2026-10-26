#!/usr/bin/env python3
"""
GW240H UART Flash - Fixed for this bootloader
Based on working approach with raw xmodem after triggering download
"""

import serial
import time
import sys
import os
import argparse
import select

RESCUE_LOAD_ADDR = 0x80020000
FIRMWARE_STAGE_ADDR = 0x85000000
XMODEM_BLOCK_SIZE = 128

class XModemSender:
    def __init__(self, ser):
        self.ser = ser
        self.packet_num = 1
    
    def _crc16(self, data):
        crc = 0
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = (crc << 1)
                crc &= 0xffff
        return crc
    
    def wait_for_c(self, timeout=30):
        print("  Waiting for 'C' from bootloader...")
        start = time.time()
        while time.time() - start < timeout:
            if self.ser.in_waiting:
                data = self.ser.read(self.ser.in_waiting)
                for b in data:
                    if b == ord('C'):
                        print("  Got 'C', starting transfer")
                        return True
                sys.stdout.write(data.decode('ascii', errors='ignore'))
                sys.stdout.flush()
            time.sleep(0.01)
        return False
    
    def send_file(self, filepath, load_addr):
        print(f"Sending {filepath} to 0x{load_addr:x} via xmodem...")
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        # Pad to 128-byte blocks
        padding = (-len(data)) % XMODEM_BLOCK_SIZE
        data += b'\x1a' * padding
        
        total_blocks = len(data) // XMODEM_BLOCK_SIZE
        print(f"  File: {len(data)} bytes ({os.path.getsize(filepath)} original), {total_blocks} blocks")
        
        # Try to trigger download
        self.ser.reset_input_buffer()
        self.ser.write(f'loadb 0x{load_addr:x}\r\n'.encode())
        time.sleep(0.5)
        self.ser.read_all()
        
        if not self.wait_for_c(timeout=10):
            print("  No 'C' received, trying different approach...")
            # Try just 'loadb' and see
            self.ser.reset_input_buffer()
            self.ser.write(b'loadb\r\n')
            time.sleep(1)
            self.ser.read_all()
            if not self.wait_for_c(timeout=10):
                print("  Still no 'C', attempting direct send anyway...")
        
        self.packet_num = 1
        retries = 0
        max_retries = 10
        
        for i in range(total_blocks):
            block = data[i*XMODEM_BLOCK_SIZE:(i+1)*XMODEM_BLOCK_SIZE]
            
            packet = bytearray()
            packet.append(0x01)  # SOH
            packet.append(self.packet_num & 0xff)
            packet.append((~self.packet_num) & 0xff)
            packet.extend(block)
            crc = self._crc16(block)
            packet.append((crc >> 8) & 0xff)
            packet.append(crc & 0xff)
            
            # Send packet
            self.ser.write(bytes(packet))
            self.ser.flush()
            
            # Wait for ACK/NAK
            start = time.time()
            got_response = False
            while time.time() - start < 2:
                if self.ser.in_waiting:
                    resp = self.ser.read(1)
                    if resp == b'\x06':  # ACK
                        self.packet_num = (self.packet_num + 1) % 256
                        if self.packet_num == 0:
                            self.packet_num = 1
                        retries = 0
                        got_response = True
                        if (i + 1) % 1000 == 0:
                            print(f"  Sent {i+1}/{total_blocks} blocks...")
                        break
                    elif resp == b'\x15':  # NAK
                        retries += 1
                        if retries > max_retries:
                            print(f"  Too many NAKs at block {i+1}")
                            raise RuntimeError("Transfer failed")
                        break  # retry same block
                    elif resp == b'\x18':  # CAN
                        raise RuntimeError("Transfer cancelled")
                    else:
                        pass
                time.sleep(0.001)
            
            if not got_response and retries == 0:
                # didn't get ACK, might need to retry
                pass
            
            if retries > 0 and retries <= max_retries:
                continue  # retry current block
            elif retries > max_retries:
                raise RuntimeError("Transfer failed")
        
        # Send EOT
        print("  Sending EOT...")
        self.ser.write(b'\x04')
        self.ser.flush()
        time.sleep(1)
        resp = self.ser.read(10)
        print(f"  EOT response: {resp}")
        
        print(f"\n  Transfer complete!")
        return True

def main():
    parser = argparse.ArgumentParser(description='GW240H UART Flash - Fixed')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate')
    parser.add_argument('--initramfs', required=True, help='Initramfs kernel')
    parser.add_argument('--hybrid', required=True, help='Hybrid 2RDH image')
    
    args = parser.parse_args()
    
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    except serial.SerialException as e:
        print(f"ERROR: Cannot open {args.port}: {e}")
        sys.exit(1)
    
    print(f"\n=== GW240H UART Flash (Fixed) ===")
    print(f"Port: {args.port}, Baud: {args.baud}")
    print("=" * 40)
    
    try:
        # Make sure we're at prompt
        ser.write(b'\r\n')
        time.sleep(1)
        ser.read_all()
        
        xmodem = XModemSender(ser)
        
        # Send initramfs
        print("\n[1/3] Sending initramfs kernel via xmodem...")
        xmodem.send_file(args.initramfs, RESCUE_LOAD_ADDR)
        
        # Send hybrid
        print("\n[2/3] Sending hybrid firmware via xmodem...")
        xmodem.packet_num = 1
        xmodem.send_file(args.hybrid, FIRMWARE_STAGE_ADDR)
        
        # Boot
        print("\n[3/3] Booting into rescue kernel...")
        ser.write(f'go 0x{RESCUE_LOAD_ADDR:x}\r\n'.encode())
        ser.flush()
        time.sleep(5)
        ser.read_all()
        
        print("\n=== FLASH STAGE COMPLETE ===")
        print("Router should boot into rescue OpenWrt.")
        print("Now run phaseE to flash to NAND...")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        ser.close()

if __name__ == '__main__':
    main()
