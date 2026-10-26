# Tools / Công cụ

[Tiếng Việt dưới đây. [English below.]]

## Tiếng Việt

Flash mặc định dùng `/dev/ttyUSB0` @ `115200 8N1` (sửa hằng `PORT` ở đầu script nếu khác).

### Quy trình đã kiểm chứng

| Bước | Lệnh | Việc |
|---|---|---|
| 1 | `python3 tools/xflash_gw240h.py` | đợi `bldr>`, nạp initramfs vào `0x80020000`, hybrid vào `0x85000000`, `jump 80020000` |
| 2 | `./tools/flash_ssh.sh` | scp hybrid sang rescue rồi `mtd write` cả hai slot + `ubiformat` `rootfs_ubi` (cần rescue đã lên, LAN `192.168.1.1`) |
| 3 | `python3 tools/postflash_verify.py` | kiểm tra sau flash |

`flash_uart.sh` chỉ chạy bước 1 rồi in hướng dẫn.

### Đóng gói ảnh

```bash
python3 tools/build_hybrid_gw240h.py \
  --trx ../openwrt/bin/targets/econet/en751221/openwrt-econet-en751221-vnpt_gw240h-squashfs-tclinux.trx \
  --out images/openwrt-gw240h-hybrid.trx
```

Script tự kiểm tra magic `UBI#` tại `0x400000`, JAMCRC và header `2RDH` trước khi ghi file.

### Thử nghiệm

- `phaseE_net.py` — điều khiển rescue qua serial, tải ảnh qua HTTP (`FW_SRV`, mặc định `192.168.1.2`, `FW_PORT=8000`) rồi ghi NAND. Trên board này bước tra `/proc/mtd` qua serial hay trả về thiếu, nên đường SSH ở trên là đường chính.

### Biến môi trường

| Biến | Dùng bởi | Mặc định |
|---|---|---|
| `INIT_F`, `FW_F` | `xflash_gw240h.py` | `images/...` trong repo |
| `FW_SRV`, `FW_PORT` | `phaseE_net.py` | `192.168.1.2`, `8000` |
| `HOST`, `IMG`, `EXPECTED_MD5` | `flash_ssh.sh` | `192.168.1.1`, `images/openwrt-gw240h-hybrid.trx` |

### Ghi chú

- Đóng picocom/minicom/screen trước khi chạy (chúng giữ `/dev/ttyUSB0`).
- UART treo (`Errno 5: could not open port`) → rút/cắm lại cáp USB-TTL.
- `tools/legacy/` là các bản thử nghiệm cũ (không dùng để flash); `tools/research/` là script thăm dò.

## English

The flow defaults to `/dev/ttyUSB0` @ `115200 8N1` (edit the `PORT` constant to change).

### Proven flow

| Step | Command | What it does |
|---|---|---|
| 1 | `python3 tools/xflash_gw240h.py` | wait for `bldr>`, stage initramfs at `0x80020000`, hybrid at `0x85000000`, `jump 80020000` |
| 2 | `./tools/flash_ssh.sh` | scp the hybrid to the rescue system, `mtd write` both slots, `ubiformat` `rootfs_ubi` (rescue must be up at `192.168.1.1`) |
| 3 | `python3 tools/postflash_verify.py` | post-flash checks |

`flash_uart.sh` runs step 1 only and prints the next step.

### Packaging an image

```bash
python3 tools/build_hybrid_gw240h.py \
  --trx ../openwrt/bin/targets/econet/en751221/openwrt-econet-en751221-vnpt_gw240h-squashfs-tclinux.trx \
  --out images/openwrt-gw240h-hybrid.trx
```

It validates the `UBI#` magic at `0x400000`, the JAMCRC and the `2RDH` header before writing.

### Experimental

- `phaseE_net.py` — drives the rescue system over serial, downloads the image over HTTP (`FW_SRV`, default `192.168.1.2`, `FW_PORT=8000`) and writes NAND. The `/proc/mtd` lookup over this serial console is unreliable, so the SSH path is the supported one.

### Environment variables

| Variable | Used by | Default |
|---|---|---|
| `INIT_F`, `FW_F` | `xflash_gw240h.py` | `images/...` in this repo |
| `FW_SRV`, `FW_PORT` | `phaseE_net.py` | `192.168.1.2`, `8000` |
| `HOST`, `IMG`, `EXPECTED_MD5` | `flash_ssh.sh` | `192.168.1.1`, `images/openwrt-gw240h-hybrid.trx` |

### Notes

- Close picocom/minicom/screen first (they hold `/dev/ttyUSB0`).
- If the UART wedges (`Errno 5: could not open port`), unplug/replug the USB-TTL adapter.
- `tools/legacy/` holds superseded experiments; `tools/research/` holds probing helpers.
