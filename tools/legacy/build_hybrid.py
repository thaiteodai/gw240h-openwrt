#!/usr/bin/env python3
"""
Build hybrid 2RDH image for GW240H (Econet EN751221/EN7521)

The tclinux.trx format from OpenWrt build:
- Custom TRX header (created by zytrx)
- Kernel (LZMA compressed, padded to 4MB)
- UBI image (created by ubinize-image.sh)

For UART flashing via xflash12.py + phaseE.py (GW040H style), we need:
- 2RDH header (256 bytes)
- Kernel (LZMA compressed, padded to 4MB)  
- UBI image

This script extracts the kernel and UBI from the tclinux.trx and creates
the hybrid 2RDH image.
"""

import struct
import hashlib
import os
import sys
import argparse
import zlib
import tempfile
import subprocess

HEADER_MAGIC = b'2RDH'
HEADER_VERSION = 1
HEADER_SIZE = 256
KERNEL_LOAD_ADDR = 0x80000000
KERNEL_ENTRY_ADDR = 0x80000000
KERNEL_PADDED_SIZE = 4 * 1024 * 1024  # 4 MB

def crc32(data):
    return zlib.crc32(data) & 0xffffffff

def extract_from_trx(trx_path, kernel_out, ubi_out):
    """Extract kernel and UBI from OpenWrt tclinux.trx"""
    with open(trx_path, 'rb') as f:
        data = f.read()
    
    # The tclinux.trx format from OpenWrt econet target:
    # - Custom TRX header (created by zytrx, variable size)
    # - Kernel (LZMA compressed, padded to 4MB)
    # - UBI image
    
    # Find the kernel LZMA stream (magic: 0x5d 0x00 0x00 or 0xfd 0x37 0x7a 0x58 0x5a)
    # LZMA alone format: 0x5d 0x00 0x00
    # LZMA with header: 0xfd 0x37 0x7a 0x58 0x5a 0x00
    
    # Search for LZMA magic
    lzma_magic1 = b'\x5d\x00\x00'
    lzma_magic2 = b'\xfd\x37\x7a\x58\x5a\x00'
    
    kernel_start = data.find(lzma_magic1)
    if kernel_start == -1:
        kernel_start = data.find(lzma_magic2)
    
    if kernel_start == -1:
        raise ValueError("Could not find LZMA kernel in TRX")
    
    # The kernel is padded to 4MB
    kernel_end = kernel_start + KERNEL_PADDED_SIZE
    
    # UBI starts after kernel padding
    ubi_start = kernel_end
    
    # Find UBI magic (0x55 0x42 0x49 0x20)
    ubi_magic = b'UBI '
    ubi_actual_start = data.find(ubi_magic, ubi_start)
    if ubi_actual_start == -1:
        ubi_actual_start = ubi_start  # Assume no extra padding
    
    kernel_data = data[kernel_start:kernel_end]
    ubi_data = data[ubi_actual_start:]
    
    print(f"Kernel offset: {kernel_start}")
    print(f"UBI offset: {ubi_actual_start}")
    print(f"Kernel size: {len(kernel_data)} bytes")
    print(f"UBI size: {len(ubi_data)} bytes")
    
    with open(kernel_out, 'wb') as f:
        f.write(kernel_data)
    
    with open(ubi_out, 'wb') as f:
        f.write(ubi_data)

def build_hybrid(kernel_path, ubi_path, output_path):
    """Build 2RDH hybrid image"""
    
    print(f"Reading kernel from: {kernel_path}")
    print(f"Reading UBI from: {ubi_path}")
    
    with open(kernel_path, 'rb') as f:
        kernel_data = f.read()
    
    with open(ubi_path, 'rb') as f:
        ubi_data = f.read()
    
    # Kernel should already be padded to 4MB
    if len(kernel_data) < KERNEL_PADDED_SIZE:
        kernel_padded = kernel_data.ljust(KERNEL_PADDED_SIZE, b'\x00')
    else:
        kernel_padded = kernel_data[:KERNEL_PADDED_SIZE]
    
    # Estimate kernel uncompressed size (typical for MIPS kernel ~7-8MB)
    kernel_uncompressed_size = 7672 * 1024
    
    # Calculate CRCs
    kernel_crc = crc32(kernel_padded)
    ubi_crc = crc32(ubi_data)
    
    print(f"Kernel size (padded): {len(kernel_padded)} bytes")
    print(f"UBI size: {len(ubi_data)} bytes")
    print(f"Kernel CRC32: {kernel_crc:08x}")
    print(f"UBI CRC32: {ubi_crc:08x}")
    
    # Build header
    header = bytearray(HEADER_SIZE)
    header[0:4] = HEADER_MAGIC
    struct.pack_into('<I', header, 4, HEADER_VERSION)
    struct.pack_into('<I', header, 8, kernel_uncompressed_size)
    struct.pack_into('<I', header, 12, len(kernel_padded))
    struct.pack_into('<I', header, 16, len(ubi_data))
    struct.pack_into('<I', header, 20, kernel_crc)
    struct.pack_into('<I', header, 24, ubi_crc)
    struct.pack_into('<I', header, 28, KERNEL_LOAD_ADDR)
    struct.pack_into('<I', header, 32, KERNEL_ENTRY_ADDR)
    
    # Calculate header CRC (bytes 0-251)
    header_crc = crc32(header[:252])
    struct.pack_into('<I', header, 252, header_crc)
    
    # Write output
    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(kernel_padded)
        f.write(ubi_data)
    
    print(f"Hybrid image written to: {output_path}")
    print(f"Total size: {HEADER_SIZE + len(kernel_padded) + len(ubi_data)} bytes")

def main():
    parser = argparse.ArgumentParser(description='Build GW240H hybrid 2RDH image')
    parser.add_argument('--trx', required=True, help='Input tclinux.trx from OpenWrt build')
    parser.add_argument('--output', required=True, help='Output hybrid image')
    
    args = parser.parse_args()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        kernel_path = os.path.join(tmpdir, 'kernel.bin')
        ubi_path = os.path.join(tmpdir, 'ubi.bin')
        
        extract_from_trx(args.trx, kernel_path, ubi_path)
        build_hybrid(kernel_path, ubi_path, args.output)

if __name__ == '__main__':
    main()