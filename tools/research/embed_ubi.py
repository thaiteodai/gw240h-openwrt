#!/usr/bin/env python3
"""
Embed UBI image into tclinux.trx for GW240H

The tclinux.trx format from OpenWrt econet target:
- Custom TRX header (created by zytrx, starts with non-standard magic)
- Kernel: LZMA compressed, padded to 4 MB (4194304 bytes)
- UBI image: appended after kernel

The GW240H flash layout:
- rootfs_ubi MTD partition: 34 MiB at offset 0x1880000
- This partition holds a UBI device with rootfs + rootfs_data volumes
"""

import struct
import sys
import os

def embed_ubi_in_trx(trx_path, ubi_path, output_path):
    """Embed UBI into TRX, replacing the small UBI section"""
    
    with open(trx_path, 'rb') as f:
        trx_data = f.read()
    
    with open(ubi_path, 'rb') as f:
        ubi_data = f.read()
    
    print(f"Original TRX: {len(trx_data)} bytes ({len(trx_data) // (1024*1024)} MB)")
    print(f"UBI image: {len(ubi_data)} bytes ({len(ubi_data) // (1024*1024)} MB)")
    
    # The tclinux.trx has kernel at offset 0, padded to 4 MB
    # Then UBI follows
    # Original: 5.2 MB total = 4 MB kernel + 1.2 MB other (old small UBI + header)
    
    # Kernel padded size (4 MB)
    kernel_padded_size = 4 * 1024 * 1024  # 4194304 bytes
    
    # New TRX: kernel + new UBI
    # But the TRX format has a specific header and structure
    # The bootloader expects the TRX to be a certain size
    
    # Check if UBI will fit (bootloader limit is typically ~5-6 MB for TRX)
    max_trx_size = 5 * 1024 * 1024  # 5 MB limit for bootloader TRX
    
    if len(ubi_data) > (max_trx_size - kernel_padded_size):
        print(f"WARNING: UBI ({len(ubi_data) // (1024*1024)} MB) too large for TRX")
        print(f"  Max UBI size: {(max_trx_size - kernel_padded_size) // (1024*1024)} MB")
        print(f"  Using original small UBI approach instead")
        # Fall back to keeping original structure
        new_trx = trx_data  # Keep original
    else:
        # Replace the old UBI (after kernel) with new UBI
        # Keep kernel padding, replace UBI
        # Original size after kernel: len(trx_data) - kernel_padded_size
        # New: keep kernel, add new UBI
        
        # Calculate new total size
        new_trx_size = kernel_padded_size + len(ubi_data)
        
        # Create new TRX: kernel portion + new UBI
        new_trx = trx_data[:kernel_padded_size] + ubi_data
        
        # Pad to maintain alignment if needed
        if len(new_trx) < new_trx_size:
            # Add small padding
            new_trx += b'\x00' * (new_trx_size - len(new_trx))
    
    # Write output
    with open(output_path, 'wb') as f:
        f.write(new_trx)
    
    print(f"New TRX: {len(new_trx)} bytes ({len(new_trx) // (1024*1024)} MB)")
    added = len(new_trx) - len(trx_data)
    print(f"  Difference: {added} bytes ({added // (1024*1024)} MB)")
    
    return output_path

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Embed UBI into TRX')
    parser.add_argument('--trx', required=True, help='Input tclinux.trx')
    parser.add_argument('--ubi', required=True, help='UBI image path')
    parser.add_argument('--output', required=True, help='Output TRX path')
    args = parser.parse_args()
    
    result = embed_ubi_in_trx(args.trx, args.ubi, args.output)
    print(f"\nOutput: {args.output}")
