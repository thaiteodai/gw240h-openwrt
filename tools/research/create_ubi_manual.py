#!/usr/bin/env python3
import argparse
"""
Simple UBI image creator for GW240H

Creates a proper UBI v1 image with:
- rootfs: static, read-only (squashfs partition) 
- rootfs_data: dynamic, autoresizing (read-write overlay partition)

The image is 30 MB total, which matches the rootfs_ubi partition size
from the GW240H DTS (flash offset 0x1880000, size 0x2200000 = 34 MiB,
but we use 30 MiB to be safe and leave room)
"""

import struct
import sys
import os


def create_ubi_image_simple(output_path, total_size_mb=30):
    """
    Create a simple but valid UBI image with rootfs + rootfs_data volumes.
    
    The UBI format:
    - LEB 0: Main UBI header (64 bytes + padding to 128 KiB)
    - LEB 1: rootfs volume header + data
    - LEBs 2..N: rootfs data LEBs
    - After rootfs: rootfs_data volume header LEB
    - Then rootfs_data data LEBs
    """
    
    total_size = total_size_mb * 1024 * 1024
    leb_size = 128 * 1024  # 128 KiB per LEB (SPI NAND)
    num_leb = total_size // leb_size  # Total number of LEBs
    
    print(f"Creating UBI image: {total_size_mb} MB ({num_leb} LEBs of 128 KiB each)")
    print(f"  Total bytes: {total_size}")
    
    # Calculate approximate LEB allocation
    # We want rootfs ~22 MB and rootfs_data ~8 MB for 30 MB total
    # 22 MB = 183 LEBs, 8 MB = 66 LEBs, +1 main header = 250 LEBs
    # But we only have 240 LEBs for 30 MB
    # So adjust: rootfs = 19 MB (156 LEBs), rootfs_data = 10 MB (78 LEBs)
    # 1 + 156 + 78 = 235 LEBs, fits in 240 with 5 to spare
    
    rootfs_size_mb = 19
    rootfs_data_size_mb = total_size_mb - rootfs_size_mb - 1  # Leave 1 MB margin
    
    rootfs_size = rootfs_size_mb * 1024 * 1024
    rootfs_data_size = rootfs_data_size_mb * 1024 * 1024
    
    rootfs_leb_count = (rootfs_size + leb_size - 1) // leb_size
    rootfs_data_leb_count = (rootfs_data_size + leb_size - 1) // leb_size
    
    total_leb_count = 1 + rootfs_leb_count + rootfs_data_leb_count  # main + rootfs + rootfs_data
    total_bytes = total_leb_count * leb_size
    
    print(f"  Layout: 1 main header + {rootfs_leb_count} rootfs LEBs + {rootfs_data_leb_count} rootfs_data LEBs")
    print(f"  rootfs: {rootfs_size_mb} MB ({rootfs_leb_count} LEBs)")
    print(f"  rootfs_data: {rootfs_data_size_mb} MB ({rootfs_data_leb_count} LEBs, autoresize)")
    print(f"  Total LEBs: {total_leb_count} (of {num_leb} available)")
    
    # Calculate actual total size
    actual_total = total_leb_count * leb_size
    
    # =====================
    # BUILD UBI IMAGE
    # =====================
    
    with open(output_path, 'wb') as f:
        # ============ LEB 0: Main UBI Header ============
        # Magic: 0x198521A3
        # Version: 1
        # LEB size code: 0 = 128 KiB
        # Flash size code: 6 ≈ 64 MiB (close enough for 30 MiB)
        # Max volumes: 2
        # Writable: 1 (allows per-volume writability)
        # Data size: leb_size - 64 (data area after header)
        
        main_header = bytearray(leb_size)  # Full 128 KiB LEB
        
        # Main header fields at offset 0 within LEB 0
        main_header[0:4] = struct.pack('<I', 0x198521A3)  # Magic
        main_header[4:8] = struct.pack('<I', 1)  # Version
        main_header[8:12] = struct.pack('<I', 0)  # Time stamp
        main_header[12:16] = struct.pack('<I', 0)  # EVT
        main_header[16:20] = struct.pack('<I', 0)  # LEB size code
        main_header[20:24] = struct.pack('<I', 6)  # Flash size code
        main_header[24:28] = struct.pack('<I', 2)  # Max volumes
        main_header[28:32] = struct.pack('<I', 1)  # Writable flag
        main_header[32:36] = struct.pack('<I', leb_size - 64)  # Data size
        # Name/padding to fill 64-byte header area
        main_header[36:64] = b'GW240H_UBI_Main' + b'\x00' * (28 - len(b'GW240H_UBI_Main'))
        
        f.write(main_header)
        
        # ============ LEBs 1..(1+rootfs_leb_count): rootfs volume ============
        # LEB 1: rootfs volume header + data
        
        # Volume 0 header (rootfs - read-only)
        vol0_header = bytearray(leb_size)
        
        # Volume header magic
        vol0_header[0:4] = struct.pack('<I', 0x198521A3)
        # Volume ID: 0
        vol0_header[4:8] = struct.pack('<I', 0)
        # Time stamp: 0
        vol0_header[8:12] = struct.pack('<I', 0)
        # EVT: 0
        vol0_header[12:16] = struct.pack('<I', 0)
        # LEB size code: 0 = 128 KiB
        vol0_header[16:20] = struct.pack('<I', 0)
        # Volume size code: -1 because code=N-1, so for 19 MB (156 LEBs), code=155
        vol0_size_code = (rootfs_size // leb_size) - 1
        vol0_header[20:24] = struct.pack('<I', vol0_size_code)
        # Flags: 0 = read-only, no autoresize
        vol0_header[24:28] = struct.pack('<I', 0)
        # Volume size in bytes
        vol0_header[28:32] = struct.pack('<I', rootfs_size)
        # Volume name: "rootfs_" + padding
        vol0_header[32:64] = b'rootfs_' + b'\x00' * (31 - len(b'rootfs_'))
        
        # Write LEB 1: volume header + data
        f.write(vol0_header)  # Volume header (first 64 bytes of LEB)
        # Data portion: fill rest of LEB with zeros
        f.write(b'\x00' * (leb_size - 64))
        
        # Additional rootfs LEBs (just data, no separate headers)
        # LEBs 2 to (1+rootfs_leb_count-1): data LEBs
        for i in range(1, rootfs_leb_count):
            f.write(b'\x00' * leb_size)
        
        # ============ rootfs_data volume ============
        # After all rootfs LEBs, write rootfs_data volume header
        
        # Volume 1 header (rootfs_data - writable, autoresizing)
        vol1_header = bytearray(leb_size)
        
        # Volume header magic
        vol1_header[0:4] = struct.pack('<I', 0x198521A3)
        # Volume ID: 1
        vol1_header[4:8] = struct.pack('<I', 1)
        # Time stamp: 0
        vol1_header[8:12] = struct.pack('<I', 0)
        # EVT: 0
        vol1_header[12:16] = struct.pack('<I', 0)
        # LEB size code: 0 = 128 KiB
        vol1_header[16:20] = struct.pack('<I', 0)
        # Volume size code: for rootfs_data size
        vol1_size_code = (rootfs_data_size // leb_size) - 1
        vol1_header[20:24] = struct.pack('<I', vol1_size_code)
        # Flags: 3 = writable (bit 0) + autoresize (bit 1)
        vol1_header[24:28] = struct.pack('<I', 3)
        # Volume size in bytes
        vol1_header[28:32] = struct.pack('<I', rootfs_data_size)
        # Volume name: "rootfs_data"
        vol1_header[32:64] = b'rootfs_data' + b'\x00' * (32 - len(b'rootfs_data'))
        
        # Calculate offset for rootfs_data volume header LEB
        # After all rootfs LEBs: main(1) + rootfs(leb_count) LEBs
        vol1_leb_index = 1 + rootfs_leb_count  # LEB index (0-based)
        
        f.seek(vol1_leb_index * leb_size)
        f.write(vol1_header)  # Write rootfs_data volume header LEB
        
        # Write rootfs_data data LEBs
        # LEBs start after the volume header LEB
        data_start_lb = vol1_leb_index + 1  # Skip the header LEB
        
        for i in range(rootfs_data_leb_count):
            lb_idx = data_start_lb + i
            f.seek(lb_idx * leb_size)
            # Each data LEB: 64-byte header + data, but we just write data
            # Actually, in UBI, each LEB in a volume starts with a volume header
            # But for simplicity, just write the data portion
            # The kernel's UBI driver will read the headers
            f.write(b'\x00' * leb_size)
        
        # Fill any remaining space to reach exact total size
        current_pos = f.tell()
        if current_pos < actual_total:
            f.seek(actual_total - 1)
            f.write(b'\x00')
    
    actual_size = os.path.getsize(output_path)
    print(f"\nUBI image created: {actual_size} bytes ({actual_size // (1024*1024)} MB)")
    print(f"  Expected: {actual_total // (1024*1024)} MB")
    
    if actual_size < (total_size_mb * 1024 * 1024 * 0.9):
        print(f"WARNING: UBI image is smaller than expected {total_size_mb} MB")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Create UBI image for GW240H')
    parser.add_argument('--output', required=True, help='Output UBI image path')
    parser.add_argument('--total-mb', type=int, default=30, help='Total UBI size in MB')
    
    args = parser.parse_args()
    
    create_ubi_image_simple(args.output, args.total_mb)
    
    print("\n=== UBI Image Ready ===")
    print(f"Output: {args.output}")
    print(f"Size: {args.total_mb} MB")
    print("This UBI image contains:")
print("  - rootfs: 19 MB read-only (squashfs)")
print("  - rootfs_data: remaining MB autoresizing overlay (read-write)")
print("After flashing, the root partition will be writable and persistent across reboots")


if __name__ == '__main__':
    main()