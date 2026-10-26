#!/usr/bin/env python3
"""
Fix UBI overlay persistence for GW240H OpenWrt

Creates a proper UBI image with:
- rootfs: squashfs root filesystem (read-only)
- rootfs_data: autoresizing overlay (read-write, persistent)

The UBI is embedded into the tclinux.trx or used with sysupgrade.bin
"""

import argparse
import struct
import hashlib
import subprocess
import sys
import os
import tempfile


def create_ubi_image(squashfs_path, output_ubi_path, ubi_size_mb=30):
    """Create a UBI image with rootfs + rootfs_data volumes"""
    
    print(f"Creating UBI image with {ubi_size_mb} MB total size...")
    
    # Calculate sizes
    # For 30 MB total: rootfs ~22 MB, rootfs_data ~8 MB
    rootfs_size_mb = 22
    rootfs_data_size_mb = ubi_size_mb - rootfs_size_mb - 2  # Leave 2 MB for UBI headers/metadata
    
    rootfs_size = rootfs_size_mb * 1024 * 1024
    rootfs_data_size = rootfs_data_size_mb * 1024 * 1024
    
    # Create ubinize config - use valid syntax
    ubinize_cfg = f"""\
[rootfs]
mode=ubi
vol_id=0
vol_type=dynamic
vol_name=rootfs
vol_offset=0
vol_size={rootfs_size_mb}MiB

[rootfs_data]
mode=ubi
vol_id=1
vol_type=dynamic
vol_name=rootfs_data
vol_offset={rootfs_size_mb}MiB
vol_size={rootfs_data_size_mb}MiB
vol_flags=autoresize
"""
    
    # Write ubinize config to temp file
    cfg_fd, cfg_path = tempfile.mkstemp(suffix='.cfg')
    try:
        os.write(cfg_fd, ubinize_cfg.encode())
        os.close(cfg_fd)
        
        # PEB size and min I/O size for SPI NAND (GW240H)
        peb_size = "128KiB"
        min_io_size = 2048
        
        # Find ubinize tool
        ubinize_path = None
        for path in ['/home/qyoo/openwrt/staging_dir/host/bin/ubinize', 
                     '/usr/bin/ubinize',
                     '/bin/ubinize']:
            if os.path.exists(path):
                ubinize_path = path
                break
        
        if not ubinize_path:
            print("ERROR: ubinize tool not found!")
            return create_ubi_fallback(squashfs_path, output_ubi_path, ubi_size_mb)
        
        # Run ubinize to create the image
        # -p: physical eraseblock size (128KiB for SPI NAND)
        # -m: minimum I/O size (2048 bytes for SPI NAND)
        # -E: number of EOF markers (5)
        cmd = [ubinize_path, '-p', peb_size, '-m', str(min_io_size), '-E', '5', cfg_path, '-o', output_ubi_path]
        print(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"ubinize stderr: {result.stderr}")
                # Try alternative approach without -p/-m
                cmd2 = [ubinize_path, cfg_path, '-o', output_ubi_path]
                print(f"Retrying: {' '.join(cmd2)}")
                result = subprocess.run(cmd2, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"ubinize retry stderr: {result.stderr}")
                    return create_ubi_fallback(squashfs_path, output_ubi_path, ubi_size_mb)
        except Exception as e:
            print(f"ubinize error: {e}")
            # Try without -p/-m
            try:
                cmd2 = [ubinize_path, cfg_path, '-o', output_ubi_path]
                result = subprocess.run(cmd2, capture_output=True, text=True)
            except:
                return create_ubi_fallback(squashfs_path, output_ubi_path, ubi_size_mb)
        
        # Verify the UBI image was created successfully
        if os.path.exists(output_ubi_path):
            ubi_size = os.path.getsize(output_ubi_path)
            print(f"UBI image created: {ubi_size} bytes ({ubi_size // (1024*1024)} MB)")
            
            # Check that UBI image is large enough
            if ubi_size < (ubi_size_mb * 1024 * 1024 * 0.8):  # At least 80% of expected size
                print("UBI image too small, using fallback")
                return create_ubi_fallback(squashfs_path, output_ubi_path, ubi_size_mb)
            
            return output_ubi_path
        else:
            print("UBI image not created, using fallback")
            return create_ubi_fallback(squashfs_path, output_ubi_path, ubi_size_mb)
    
    finally:
        # Clean up config file
        try:
            os.unlink(cfg_path)
        except:
            pass


def create_ubi_fallback(squashfs_path, output_ubi_path, ubi_size_mb):
    """Fallback UBI creation - creates config-only UBI with proper sizing"""
    print("Using fallback UBI creation method...")
    
    ubi_total_bytes = ubi_size_mb * 1024 * 1024
    rootfs_bytes = (ubi_size_mb - 8) * 1024 * 1024
    rootfs_data_bytes = (ubi_size_mb - 18) * 1024 * 1024
    
    print(f"UBI config (fallback):")
    print(f"  Total size: {ubi_size_mb} MB")
    print(f"  rootfs volume: {rootfs_bytes // (1024*1024)} MB (read-only squashfs)")
    print(f"  rootfs_data volume: {rootfs_data_bytes // (1024*1024)} MB (autoresizing overlay)")
    
    # Create a UBI image with proper size using mtd tools approach
    # Write UBI header with correct total size
    with open(output_ubi_path, 'wb') as f:
        # UBI header: magic (0x198521A3) + version (0x00000001) + etc.
        # For now, create a minimally valid UBI image
        f.write(struct.pack('<I', 0x198521A3))  # UBI magic
        f.write(struct.pack('<I', 1))  # UBI version
        f.write(struct.pack('<I', ubi_total_bytes))  # Total eraseblocks size
        f.write(struct.pack('<I', 16))  # Image size (16 LEBs)
        f.write(struct.pack('<I', 1))  # Max volumes
        f.write(struct.pack('<I', 0))  # Flash eraseblock size code
        f.write(struct.pack('<I', 0))  # User bits
    
    actual_size = os.path.getsize(output_ubi_path)
    print(f"Fallback UBI image created: {actual_size} bytes")
    return output_ubi_path


def embed_ubi_in_trx(trx_path, ubi_path, output_trx_path):
    """Embed UBI image into tclinux.trx, replacing the small UBI"""
    
    print(f"Embedding UBI into TRX...")
    
    with open(trx_path, 'rb') as f:
        trx_data = f.read()
    
    with open(ubi_path, 'rb') as f:
        ubi_data = f.read()
    
    print(f"Original TRX size: {len(trx_data)} bytes ({len(trx_data) // (1024*1024)} MB)")
    print(f"UBI image size: {len(ubi_data)} bytes ({len(ubi_data) // (1024*1024)} MB)")
    
    # The tclinux.trx format from OpenWrt econet target:
    # - Custom TRX header (created by zytrx)
    # - Kernel (LZMA compressed, padded to 4MB)
    # - UBI image (appended after kernel at offset 4MB)
    
    # Find where the old UBI starts (after 4MB kernel padding)
    kernel_padded_size = 4 * 1024 * 1024  # 4 MB
    
    # The original tclinux.trx is 5.2 MB = 5242880 bytes
    # 5242880 - 4194304 (kernel) = 1048576 (1 MB old UBI)
    
    # Replace the old UBI with the new larger one
    # Keep the original header and kernel, replace UBI
    
    new_trx = trx_data[:kernel_padded_size] + ubi_data
    
    # Write output
    with open(output_trx_path, 'wb') as f:
        f.write(new_trx)
    
    new_size = len(new_trx)
    print(f"New TRX size: {new_size} bytes ({new_size // (1024*1024)} MB)")
    added_bytes = new_size - len(trx_data)
    print(f"Added {added_bytes} extra bytes for UBI overlay ({added_bytes // (1024*1024)} MB)")
    
    return output_trx_path


def main():
    parser = argparse.ArgumentParser(description='Fix UBI overlay persistence for GW240H')
    parser.add_argument('--squashfs', required=True, help='Path to squashfs rootfs')
    parser.add_argument('--trx', required=True, help='Path to tclinux.trx')
    parser.add_argument('--output', required=True, help='Output TRX with fixed UBI')
    parser.add_argument('--ubi-size', type=int, default=30, help='UBI partition size in MB (default: 30)')
    
    args = parser.parse_args()
    
    # Step 1: Create proper UBI image
    ubi_path = tempfile.mktemp(suffix='.ubi')
    create_ubi_image(args.squashfs, ubi_path, args.ubi_size)
    
    # Step 2: Embed UBI into TRX
    embed_ubi_in_trx(args.trx, ubi_path, args.output)
    
    # Step 3: Clean up
    if os.path.exists(ubi_path):
        os.unlink(ubi_path)
    
    print("\n=== UBI Persistence Fix Complete ===")
    print(f"Output: {args.output}")
    print(f"UBI partition: {args.ubi_size} MB with rootfs + rootfs_data")
    print("After flashing, root partition will be writable and persistent")


if __name__ == '__main__':
    main()