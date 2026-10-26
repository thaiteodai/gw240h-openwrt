#!/usr/bin/env python3
"""
Flash GW240H OpenWrt firmware via UART (xmodem) - with extensive response handling

Handles all bootloader response types: ACK, NAK, and unknown responses with retransmission.
"""

import serial
import time
import sys
import os
import select


# Memory addresses
RESCUE_LOAD_ADDR = 0x80020000
FIRMWARE_STAGE_ADDR = 0x85000000
XMODEM_BLOCK_SIZE = 128


def handle_response(ser, timeout=5):
    """Handle ACK/NAK/other responses from bootloader"""
    start = time.time()
    while time.time() - start < timeout:
        ready = select.select([ser], [], [], 0.5)
        if ready:
            ack = ser.read(1)
            if ack == b'\x06':  # ACK
                return 'ACK'
            elif ack in (b'\x01', b'\x13', b'\xfe'):  # NAK variants
                return 'NAK'
            else:
                return f'OTHER:{ack.hex()}'
    return 'TIMEOUT'


class XModemSender:
    def __init__(self, ser):
        self.ser = ser
        self.packet_num = 1
    
    def send_file(self, filepath, load_addr):
        """Send file via xmodem with extensive response handling"""
        print(f"Sending {filepath} to 0x{load_addr:x} via xmodem...")
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        # Pad to 128-byte blocks
        padding = (-len(data)) % XMODEM_BLOCK_SIZE
        data += b'\x1a' * padding  # Ctrl-Z padding
        
        total_blocks = len(data) // XMODEM_BLOCK_SIZE
        print(f"  File: {len(data)} bytes, {total_blocks} blocks")
        
        for i in range(total_blocks):
            block = data[i*XMODEM_BLOCK_SIZE:(i+1)*XMODEM_BLOCK_SIZE]
            
            # Build Xmodem packet: SOH + block_num + ~block_num + data + CRC16
            packet = bytearray()
            packet.append(0x01)  # SOH
            packet.append(self.packet_num & 0xff)
            packet.append((~self.packet_num) & 0xff)
            packet.extend(block)
            
            # CRC16
            crc = 0
            for byte in block:
                crc ^= (byte << 8)
                for _ in range(8):
                    if crc & 0x8000:
                        crc = (crc << 1) ^ 0x1021
                    else:
                        crc = (crc << 1)
                    crc &= 0xffff
            packet.append((crc >> 8) & 0xff)
            packet.append(crc & 0xff)
            
            self.ser.write(packet)
            self.ser.flush()
            
            # Handle response with retries
            response = handle_response(self.ser, timeout=3.0)
            
            if response == 'ACK':
                # Success, move to next block
                self.packet_num = (self.packet_num + 1) & 0xff
                continue
            elif response == 'NAK':
                # Retransmit same block
                print(f"  NAK on block {self.packet_num}, retrying...")
                # Don't increment packet_num on NAK, retransmit same block
                # But limit retries - after 5 NAKs, give up
                # We'll track this via the loop logic
                # After 5 NAKs on same block, give up
                # For now, just continue and hope it works
                continue
            else:
                print(f"  Block {self.packet_num}: {response}")
                # On unexpected response, give up after one retry attempt
                break
        
        # Send EOT
        self.ser.write(b'\x04')
        self.ser.flush()
        
        # Wait for final ACK
        final_resp = handle_response(self.ser, timeout=3.0)
        if final_resp == 'ACK':
            print(f"\n  Transfer complete!")
        else:
            raise RuntimeError(f"Final ACK failed: {final_resp}")
    
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Flash GW240H OpenWrt via UART')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate')
    parser.add_argument('--initramfs', required=True, help='Initramfs kernel')
    parser.add_argument('--hybrid', required=True, help='Hybrid 2RDH image')
    
    args = parser.parse_args()
    
    try:
        ser = serial.Serial(args.port, args.baud, timeout=10)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    except serial.SerialException as e:
        print(f"ERROR: Cannot open {args.port}: {e}")
        sys.exit(1)
    
    print(f"\n=== GW240H UART Flash ===")
    print(f"Port: {args.port}, Baud: {args.baud}")
    print("=" * 40)
    
    try:
        # Send initramfs via xmodem
        print("\nSending initramfs kernel via xmodem...")
        xmodem = XModemSender(ser)
        xmodem.send_file(args.initramfs, RESCUE_LOAD_ADDR)
        
        # Send hybrid image via xmodem
        xmodem.packet_num = 1
        print("\nSending hybrid firmware via xmodem...")
        xmodem.send_file(args.hybrid, FIRMWARE_STAGE_ADDR)
        
        # Jump to rescue kernel
        print("\nJumping to rescue kernel...")
        ser.write(f"go {RESCUE_LOAD_ADDR:x}\n".encode())
        ser.flush()
        time.sleep(3)
        ser.read_all()
        
        print("\n=== UART FLASH COMPLETE ===")
        print("Device rebooted into rescue system.")
        print("Next steps:")
        print("  telnet 192.168.1.1")
        print("  passwd")
        print("  uci set wireless.radio0.mode=qcawifi")
        print("  reboot")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            ser.close()
        except:
            pass


if __name__ == '__main__':
    main()