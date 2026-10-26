# Legacy / Thử nghiệm cũ

Các script ở đây thuộc những lần thử trước, **không dùng để flash** bản hiện tại.
They are kept for the record only — do not use them to flash the current build.

| File | Ghi chú |
|---|---|
| `flash_gw240h.py`, `flash_gw240h_fixed.py` | các bản flash UART trước khi chuyển sang quy trình xflash + `ubiformat` |
| `build_hybrid.py` | bản đóng gói hybrid đầu tiên (đã thay bằng `build_hybrid_gw240h.py`) |
| `phaseE_gw240h.py` | ghi NAND qua `/dev/mem`; initramfs hiện tại **không** có `CONFIG_DEVMEM` nên không chạy được |
| `autoflash_watch.py` | vòng lặp tự động gọi `xflash_gw240h.py` + `phaseE_gw240h.py` (cùng lý do trên) |
| `xflash_gw240h.py.bak` | bản sao lưu |

Đường đã kiểm chứng nằm ở `tools/`: `xflash_gw240h.py` → `tools/flash_ssh.sh`.
