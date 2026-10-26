# Docs / Tài liệu

[Tiếng Việt dưới đây. [English below.]]

## Tiếng Việt

Bằng chứng và ghi chú từ quá trình bring-up / flash:

- [`boot-log-rescue.txt`](boot-log-rescue.txt) — log serial đầy đủ của lần boot rescue kernel từ RAM (`jump 80020000`), Linux 6.18.55, MTD, UBI, `mt7615e`, `br-lan`.
- [`bootloader_tips.txt`](bootloader_tips.txt) — cách bắt prompt `bldr>` (thời điểm, tốc độ, dây nối) và các lỗi thường gặp.
- [`../README.md`](../README.md) — bản đồ phân vùng đã kiểm chứng, quy trình flash, build, known issues.
- [`../CREDITS.md`](../CREDITS.md) — nguồn tham khảo.

Các điểm đáng chú ý trong log:

```
boot_info_addr: 75c0570; flag: 1      -> bootbase đọc slot 0x1e80000
ubi0: attached mtd4 (rootfs_ubi)      -> 272 PEB, 0 bad
mt7615e 0001:01:00.0                  -> PCI 14c3:7615, 2 phy
econet_eth ... generated random MAC   -> MAC chưa lấy từ nvmem
```

## English

Evidence and notes from the bring-up / flashing sessions:

- [`boot-log-rescue.txt`](boot-log-rescue.txt) — full serial capture of the RAM rescue boot (`jump 80020000`): Linux 6.18.55, MTD map, UBI attach, `mt7615e`, `br-lan`.
- [`bootloader_tips.txt`](bootloader_tips.txt) — how to catch the `bldr>` prompt and common failures.
- [`../README.md`](../README.md) — verified flash map, flashing flow, build, known issues.
- [`../CREDITS.md`](../CREDITS.md) — references.

Highlights from the log:

```
boot_info_addr: 75c0570; flag: 1      -> bootbase loads slot 0x1e80000
ubi0: attached mtd4 (rootfs_ubi)      -> 272 PEBs, 0 bad
mt7615e 0001:01:00.0                  -> PCI 14c3:7615, two phys
econet_eth ... generated random MAC   -> MAC is not read from nvmem yet
```
