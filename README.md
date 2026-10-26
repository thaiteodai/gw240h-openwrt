# VNPT GW240H → OpenWrt Custom Build

> OpenWrt SNAPSHOT cho VNPT GW240H (Econet EN751221, 256 MB RAM, 128 MB SPI NAND, MT7615D dual-band). Boot từ NAND, overlay UBI ghi được, LuCI, WiFi 2.4 + 5 GHz, flash qua UART. GPON không hỗ trợ.
>
> Custom OpenWrt for the VNPT GW240H (Econet EN751221, 256 MB RAM, 128 MB SPI NAND, MT7615D dual-band). NAND boot, writable UBI overlay, LuCI, 2.4 + 5 GHz AP, UART flashing. GPON unsupported.

*(Tiếng Việt ở trên, English below.)*

## Trạng thái / Status

*Kiểm chứng trên phần cứng ngày 2026-10-26 / verified on hardware 2026-10-26.*

| Hạng mục / Item | Kết quả / Result |
|---|---|
| OpenWrt SNAPSHOT `r37622-a25fb079b1` (Linux 6.18.55) boot từ NAND / boots from NAND | ✅ |
| UBI attach `mtd4` (`rootfs_ubi`), 272 PEB, 0 bad / 0 bad blocks | ✅ |
| Overlay `/dev/ubi0_1` ghi được, giữ qua reboot / writable, persists | ✅ |
| LuCI (uhttpd, 80/443), SSH (dropbear), dnsmasq | ✅ |
| WiFi 2.4 GHz + 5 GHz (MT7615D, EEPROM hiệu chuẩn từ `reservearea`) | ✅ |
| LAN: `br-lan` trên `eth0` (một GMAC), mặc định `192.168.1.1/24` | ✅ (bridge hoạt động; từng cổng chưa test riêng / ports not individually benchmarked) |
| Flash qua UART (`xmdm`/xmodem) + ghi NAND qua SSH | ✅ |
| LED trên vỏ máy / case LEDs | ❌ **chưa hoạt động** — xem bên dưới |
| Nút Reset / WPS / WiFi | ❌ **chưa hoạt động** — không có node `gpio-keys`, `/dev/input` trống |
| GPON (EN7571) | ❌ không có driver / unsupported |
| VoIP FXS (Le9662) | ❌ không có trong build / not included |
| `sysupgrade` | ⚠️ chưa kiểm chứng / untested |
| Địa chỉ MAC Ethernet | ⚠️ random mỗi lần boot (DTS thiếu cell MAC) |
| Mật khẩu root / root password | ⚠️ trống sau flash, đặt ngay / empty, set immediately |

**Về LED và nút bấm / About LEDs and buttons:** kernel có `kmod-leds-gpio`, `kmod-gpio-button-hotplug` và hai `gpiochip` (2×32 line), nhưng DTS **không** khai báo `gpio-leds`/`gpio-keys`. Vì vậy:
- `/sys/class/leds` chỉ có `mt76-phy0`, `mt76-phy1` (LED do chip WiFi tự đăng ký).
- `files/.../board.d/01_leds` tạo các mục `system.led_*` trỏ tới `power`, `internet`, `pon`, `lan1..4`… — các tên này **không tồn tại**, nên cấu hình đó vô tác dụng.
- Số chân trong bảng phần cứng (Reset 0, WPS 77, WiFi 79) là từ nguồn OEM, **chưa xác minh** bằng thực nghiệm.

Muốn làm LED/nút hoạt động: dò chân GPIO (đọc input khi bấm nút; xuất output để tìm LED), thêm node `gpio-leds` + `gpio-keys` vào DTS rồi build lại. Xem [Known issues](#known-issues--việc-còn-lại).

## Điểm mấu chốt: bootbase boot slot `0x1e80000`

Trên **unit này**, bootbase chạy `boot flag = 1` và boot ảnh từ **slot phụ**:

```
boot_info_addr: 75c0570; flag: 1
==>1e80000
```

Vì vậy `tclinux_alt` (`0x1e80000 .. 0x2a80000`) là slot thực sự được boot, và **bất cứ thứ gì ghi đè vùng này đều làm máy chết**. Lần flash đầu đặt `rootfs_ubi` tại `0x1880000` (theo bản đồ của GW040H) đã ghi đè slot này; triệu chứng:

```
Undefined Exception happen
CP0_EPC=81fb9f10
```

Bản đồ dưới đây đã sửa đúng: `rootfs_ubi` dời lên `0x2a80000`, và **cả hai** slot `tclinux`/`tclinux_alt` đều nhận đầy đủ hybrid 2RDH.

## Bản đồ phân vùng / Flash map (đã kiểm chứng)

| Phân vùng | Offset | Kích thước | Nội dung |
|---|---|---|---|
| `bootloader` | `0x00000000` | 256 KiB | bootbase OEM — **không bao giờ ghi** |
| `romfile` | `0x00040000` | 256 KiB | cấu hình OEM — không ghi |
| `tclinux` | `0x00080000` | 12 MiB (`0xc00000`) | hybrid 2RDH đầy đủ (slot dự phòng) |
| `tclinux_alt` | `0x01e80000` | 12 MiB | hybrid 2RDH đầy đủ — **slot bootbase boot** |
| `rootfs_ubi` | `0x02a80000` | 34 MiB (`0x2200000`) | UBI: `rootfs` (squashfs) + `rootfs_data` (overlay) |
| `yaffs` | `0x04c80000` | 18 MiB | không dùng (cửa sổ còn lại của flash) |
| `safedata` | `0x05e80000` | 10 MiB | cấu hình OEM — giữ nguyên |
| `reservearea` | `0x07520000` | 768 KiB | **EEPROM hiệu chuẩn MT7615 tại `+0x20000`** (cell `0x4da8` byte) |

Thứ tự ghi (mọi bước đều đọc lại để kiểm tra):

1. `mtd write <hybrid> tclinux` — slot chính, giữ hai slot nhất quán nếu `boot flag` đổi.
2. `mtd write <hybrid> tclinux_alt` — **bắt buộc**: bootbase cần header `2RDH` hợp lệ **và** JAMCRC khớp trên toàn bộ container (kernel + UBI).
3. `dd if=<hybrid> of=/tmp/ubi bs=65536 skip=64` rồi `ubiformat /dev/mtd4 -y -q -f /tmp/ubi` — UBI thật mà kernel attach và boot.

Không dùng `mtd write` cho `rootfs_ubi`: hai slot `tclinux*` có `econet,enable-remap`, còn `rootfs_ubi` thì không, nên phải `ubiformat` để xử lý bad block.

## Ảnh & checksum / Images & checksums

| File | Kích thước | MD5 |
|---|---|---|
| `images/openwrt-gw240h-hybrid.trx` | 11,403,264 B | `16b1657e4606e5cdb7c2038c80c11984` |
| `images/openwrt-econet-en751221-vnpt_gw240h-initramfs-kernel.bin` | 8,849,454 B | `0267d2d0c520eb76ac38b1bfb0378105` |

Đây là đúng hai file đã dùng để flash thành công. Kiểm tra trước khi dùng:

```bash
cd gw240h-openwrt
md5sum images/openwrt-gw240h-hybrid.trx \
       images/openwrt-econet-en751221-vnpt_gw240h-initramfs-kernel.bin
```

`images/openwrt-econet-en751221-vnpt_gw240h.manifest` liệt kê toàn bộ package của bản build.

## Phần cứng / Hardware (theo boot log)

| Thành phần | Thực tế |
|---|---|
| SoC | Econet **EN751221**, MIPS 34Kc, 1 CPU hoạt động (597.60 BogoMIPS), kernel SMP |
| RAM | 256 MB (`Memory: 213912K/262144K available`) |
| Flash | SPI NAND **ESMT 128 MiB**, block 128 KiB, page 2048 B, OOB 64 B |
| WiFi | MediaTek **MT7615D** DBDC trên PCIe1, PCI ID `14c3:7615`, driver `mt7615e`, 2 phy |
| Ethernet | `econet_eth 1fb50000.ethernet`, một GMAC, 4 cổng LAN qua bridge `br-lan` |
| PON | GPON/EPON — không có driver mã nguồn mở |
| VoIP | 2× FXS (Le9662 SLIC) — không có trong build |
| LED / nút | có phần cứng, **chưa nối vào OpenWrt** (xem phần trạng thái) |

> Hai điểm trong bản README cũ đã được sửa theo log thật: SoC là **EN751221** (không phải EN7521), và NAND là **ESMT** (không phải Fudan F50L1G41LB). CPU cũng chỉ có **1 core** hoạt động, không phải 4 core @ 900 MHz.

## Flash lên máy / Flashing

### 0. Chuẩn bị

- Cáp USB-TTL **3.3 V** (CP2102/FT232RL), nối `GND ↔ GND`, `RX ↔ TX`, `TX ↔ RX`; console `115200 8N1`.
- Python 3 + `pyserial`; đóng picocom/minicom/screen trước khi chạy.
- Một dây Ethernet từ máy tính vào một trong 4 cổng LAN (dùng cho đường SSH/HTTP khi ghi NAND).

```bash
cd gw240h-openwrt
chmod +x tools/*.py tools/*.sh
```

### 1. Nạp rescue + firmware vào RAM (qua serial)

```bash
python3 tools/xflash_gw240h.py
```

Script sẽ:
- đợi prompt `bldr>` — nếu chưa thấy, **rút nguồn 5 giây rồi cắm lại** theo hướng dẫn trên terminal;
- gửi initramfs tới `0x80020000` (resumable, có state trong `/tmp/opencode/xflash_state.json`);
- gửi hybrid tới `0x85000000`;
- `jump 80020000` → rescue Linux chạy hoàn toàn từ RAM.

Thành công khi log kết thúc bằng `RESULT: SHELL_UP` và có prompt shell. **NAND chưa bị ghi ở bước này.**

### 2. Rescue system

Rescue initramfs mang `dropbear` với root **mật khẩu trống**, LAN mặc định `192.168.1.1/24`. Đặt IP tĩnh cho máy tính cùng dải, ví dụ `192.168.1.2/24`:

```bash
sudo ip addr add 192.168.1.2/24 dev <ethernet-iface>
ping -c1 192.168.1.1
ssh root@192.168.1.1        # Enter khi hỏi mật khẩu
```

> Initramfs này **không** có `CONFIG_DEVMEM`, nên không đọc lại được ảnh đã stage từ RAM. Vì vậy firmware được truyền qua LAN (SSH hoặc HTTP) ở bước sau.

### 3. Ghi NAND — đường đã kiểm chứng (SSH)

```bash
scp images/openwrt-gw240h-hybrid.trx root@192.168.1.1:/tmp/fw
ssh root@192.168.1.1
```

Trên rescue system:

```sh
md5sum /tmp/fw                       # phải là 16b1657e4606e5cdb7c2038c80c11984
mtd write /tmp/fw tclinux
mtd write /tmp/fw tclinux_alt        # BẮT BUỘC — đây là slot được boot
dd if=/tmp/fw of=/tmp/ubi bs=65536 skip=64
ubidetach -d 0 2>/dev/null; ubidetach -m 4 2>/dev/null
ubiformat /dev/mtd4 -y -q -f /tmp/ubi
ubiattach -m 4 -d 0 && ubinfo -d 0   # phải thấy rootfs + rootfs_data
sync && reboot
```

Sau ~55 giây máy boot lại từ NAND.

### 3'. Ghi NAND — tự động qua HTTP (thử nghiệm)

`tools/phaseE_net.py` làm cùng việc nhưng điều khiển rescue qua serial và tải ảnh bằng HTTP. Trên máy tính:

```bash
python3 -m http.server 8000 --bind 192.168.1.2 --directory images
# terminal khác:
FW_SRV=192.168.1.2 FW_PORT=8000 python3 tools/phaseE_net.py
```

Đường này đã đi được tới bước tải ảnh + kiểm MD5, nhưng tra cứu `/proc/mtd` qua serial hay trả về thiếu trên board này (`tclinux device: None`). Nếu gặp lỗi đó, dùng đường SSH ở trên — nó đã được kiểm chứng.

### 4. Xác minh / verify

```bash
python3 tools/postflash_verify.py            # hoặc --port /dev/ttyUSB0
```

Kỳ vọng / expected:
- `openwrt_release` = `r37622-a25fb079b1`
- `/proc/mtd` đúng bản đồ trên, `ubinfo -d 0` có 2 volume
- `/overlay` là `ubi0_1`, ghi được
- `iw dev` có 2 phy/AP; LuCI trả HTTP 200
- LAN `192.168.1.1`, WiFi mở SSID `OpenWrt`

Sau đó đặt ngay mật khẩu root (`passwd`) và WPA2 cho WiFi.

## Build từ source / Building from source

Repo này **không phải** cây OpenWrt đầy đủ; `files/` là overlay chép đè lên một cây OpenWrt có target `econet/en751221`.

```bash
git clone https://git.openwrt.org/openwrt/openwrt.git
cd openwrt
rsync -a /path/to/gw240h-openwrt/files/ ./
make menuconfig      # Target: Econet (EN751221) -> Device: VNPT GW240H
make -j"$(nproc)"
```

Overlay gồm:

| File | Vai trò |
|---|---|
| `target/linux/econet/dts/en751221_vnpt_gw240h.dts` | flash map (slot boot `0x1e80000`), GMAC, PCIe MT7615, EEPROM nvmem |
| `target/linux/econet/image/en751221.mk` | device `vnpt_gw240h`, `KERNEL_SIZE=4096k`, `FACTORY_SIZE=12288k` |
| `target/linux/econet/base-files/etc/board.d/01_leds` | cấu hình LED — hiện vô tác dụng (xem trạng thái) |
| `files/etc/uci-defaults/99-wifi-ap` | bật AP ở lần boot đầu |
| `files/etc/uci-defaults/10-network` | vô tác dụng (xem Known issues) |

Đóng gói hybrid từ ảnh build:

```bash
python3 tools/build_hybrid_gw240h.py \
  --trx ../openwrt/bin/targets/econet/en751221/openwrt-econet-en751221-vnpt_gw240h-squashfs-tclinux.trx \
  --out images/openwrt-gw240h-hybrid.trx
```

`build.sh` là script cũ (đường dẫn tuyệt đối, nhánh 23.05); dùng các lệnh trên thay vì `build.sh`. Build đã dùng: OpenWrt SNAPSHOT, Linux 6.18.55, GCC 14.4.0.

## Known issues / Việc còn lại

1. **LED + nút bấm**: chưa có `gpio-leds`/`gpio-keys`; `01_leds` chỉ trỏ tới tên không tồn tại. Cần dò chân GPIO rồi bổ sung DTS. Pin map OEM (0/77/79) chưa xác minh.
2. **MAC Ethernet ngẫu nhiên** mỗi lần boot (`econet_eth ... generated random MAC address`): DTS thiếu cell lấy MAC từ `romfile`/`safedata`; chỉ ảnh hưởng thẩm mỹ/DHCP reservation.
3. **`10-network` vô tác dụng**: nó ghi `/etc/board.json` (symlink → `/tmp/sysinfo/board.json`) *sau* khi `config_generate` đã tạo `/etc/config/network`, và `/tmp` mất khi reboot. Mạng thực tế lấy mặc định `lan = eth0` từ `board.d/99-default_network`.
4. **`sysupgrade` chưa kiểm chứng**: với bản đồ này hãy flash lại bằng quy trình UART + `ubiformat`; `tclinux_alt` là slot dự phòng.
5. **GPON / VoIP**: không có driver xPON, không có stack FXS → chỉ dùng làm router/AP.
6. **Cáp USB-TTL có thể treo** (`could not open port /dev/ttyUSB0`, `Errno 5`): rút/cắm lại adapter; nếu đã vào rescue thì ghi tiếp qua SSH như bước 3.
7. **`phaseE_net.py`** (HTTP) chưa hoàn chỉnh trên board này — dùng đường SSH.

## Cảnh báo cross-flash: GW040H ≠ GW240H

Cùng SoC nhưng **boot slot khác nhau**, nên bản đồ phân vùng không dùng lẫn được:

| | GW040H | GW240H (unit này) |
|---|---|---|
| `boot flag` | 0 | **1** |
| Slot bootbase đọc | `0x80000` | **`0x1e80000`** |
| `rootfs_ubi` | `0x1880000` | **`0x2a80000`** |
| Hậu quả nếu dùng nhầm | — | ghi đè slot boot → `Undefined Exception` |

## Credit / Ghi công

Xem [CREDITS.md](CREDITS.md). Dự án dựa trên cổng OpenWrt GW040H cùng tác giả, target `econet` của OpenWrt, driver `mt76`, và các phân tích công khai của cộng đồng (ResearcherPT/vnptmodemresearch).

## License

MIT — xem [LICENSE](LICENSE).

---

# English

## Status

Verified on hardware 2026-10-26: OpenWrt SNAPSHOT `r37622-a25fb079b1` (Linux 6.18.55) boots from NAND, `ubi0` attaches to `mtd4` with 272 PEBs / 0 bad blocks, the overlay persists across reboot, LuCI + SSH + dnsmasq work, both MT7615D radios come up with the factory EEPROM read from `reservearea`, and the LAN bridge (`br-lan` over the single `eth0`) is at `192.168.1.1/24`.

**Not working / not implemented:** case LEDs and buttons (no `gpio-leds`/`gpio-keys` nodes in the DTS; only `mt76-phy0`/`mt76-phy1` exist in `/sys/class/leds` and `/dev/input` is empty), GPON, VoIP, and `sysupgrade` (untested). The Ethernet MAC is random on every boot. Root has an empty password after flashing.

## The critical detail: this bootbase boots `0x1e80000`

The OEM bootbase on this unit runs with `boot flag = 1`, so it loads the image from the **secondary slot**:

```
boot_info_addr: 75c0570; flag: 1
==>1e80000
```

Anything overlapping `0x1e80000 .. 0x2a80000` bricks the device (`Undefined Exception happen`, `CP0_EPC=81fb9f10`). The GW040H map (`rootfs_ubi` at `0x1880000`) does exactly that — do not reuse it here.

## Flash map (verified)

| Partition | Offset | Size | Content |
|---|---|---|---|
| `bootloader` | `0x00000000` | 256 KiB | OEM bootbase — never write |
| `romfile` | `0x00040000` | 256 KiB | OEM config — leave alone |
| `tclinux` | `0x00080000` | 12 MiB | full 2RDH hybrid (spare slot) |
| `tclinux_alt` | `0x01e80000` | 12 MiB | full 2RDH hybrid — **the slot that boots** |
| `rootfs_ubi` | `0x02a80000` | 34 MiB | UBI `rootfs` + `rootfs_data` |
| `yaffs` | `0x04c80000` | 18 MiB | unused |
| `safedata` | `0x05e80000` | 10 MiB | OEM config — untouched |
| `reservearea` | `0x07520000` | 768 KiB | MT7615 calibration EEPROM at `+0x20000` |

Write order (each step is read-back verified): both `tclinux` slots get the **whole** hybrid via `mtd write` (2RDH header + JAMCRC must be valid on the slot the bootbase reads), and the UBI goes to `rootfs_ubi` via `ubiformat` (that partition has no `econet,enable-remap`, so bad blocks must be handled by UBI).

## Images

| File | Size | MD5 |
|---|---|---|
| `images/openwrt-gw240h-hybrid.trx` | 11,403,264 B | `16b1657e4606e5cdb7c2038c80c11984` |
| `images/openwrt-econet-en751221-vnpt_gw240h-initramfs-kernel.bin` | 8,849,454 B | `0267d2d0c520eb76ac38b1bfb0378105` |

## Flashing

1. **Stage over UART:** `python3 tools/xflash_gw240h.py` — waits for `bldr>`, sends the initramfs to `0x80020000` and the hybrid to `0x85000000`, then `jump 80020000`. Power-cycle the ONT when prompted. NAND is not touched yet.
2. **Rescue system:** boots from RAM with `dropbear`, empty root password, LAN `192.168.1.1/24`. Give your PC `192.168.1.2/24` on the Ethernet port.
3. **Write NAND (proven path):**

   ```bash
   scp images/openwrt-gw240h-hybrid.trx root@192.168.1.1:/tmp/fw
   ssh root@192.168.1.1
   ```

   ```sh
   md5sum /tmp/fw                       # must be 16b1657e4606e5cdb7c2038c80c11984
   mtd write /tmp/fw tclinux
   mtd write /tmp/fw tclinux_alt        # mandatory — bootbase boots this slot
   dd if=/tmp/fw of=/tmp/ubi bs=65536 skip=64
   ubidetach -d 0 2>/dev/null; ubidetach -m 4 2>/dev/null
   ubiformat /dev/mtd4 -y -q -f /tmp/ubi
   ubiattach -m 4 -d 0 && ubinfo -d 0   # rootfs + rootfs_data must be listed
   sync && reboot
   ```

   The rescue initramfs has no `CONFIG_DEVMEM`, so the staged RAM copy cannot be read back — transfer the image over the LAN instead.

   `tools/phaseE_net.py` automates this over HTTP (`FW_SRV=192.168.1.2 FW_PORT=8000`, with `python3 -m http.server 8000 --bind 192.168.1.2 --directory images`). It reaches the download + MD5 check, but the `/proc/mtd` lookup over this serial console is unreliable (`tclinux device: None`); the SSH path above is the proven one.

4. **Verify:** `python3 tools/postflash_verify.py`. Expect `r37622-a25fb079b1`, the partition map above, two UBI volumes, a writable overlay, two radios, LuCI HTTP 200, LAN `192.168.1.1`, open SSID `OpenWrt`. Then set a root password and WPA2.

## Build

Overlay `files/` onto an OpenWrt tree and select **Econet EN751221 → VNPT GW240H**:

```bash
git clone https://git.openwrt.org/openwrt/openwrt.git
cd openwrt
rsync -a /path/to/gw240h-openwrt/files/ ./
make menuconfig
make -j"$(nproc)"

python3 tools/build_hybrid_gw240h.py \
  --trx ../openwrt/bin/targets/econet/en751221/openwrt-econet-en751221-vnpt_gw240h-squashfs-tclinux.trx \
  --out images/openwrt-gw240h-hybrid.trx
```

`build.sh` is an older helper (absolute paths, 23.05 branch); prefer the commands above.

## Known issues

1. LEDs/buttons: no `gpio-leds`/`gpio-keys`; `01_leds` references names that do not exist. GPIO probing is required before adding DTS nodes.
2. Random Ethernet MAC each boot: the DTS has no MAC nvmem cell.
3. `10-network` is inert: it rewrites `/etc/board.json` (a symlink into `/tmp`) after `config_generate` has already produced `/etc/config/network`.
4. `sysupgrade` untested — reflash with the UART + `ubiformat` flow.
5. No GPON, no VoIP.
6. The USB-TTL adapter can wedge (`Errno 5`); replug it, or finish over SSH if the rescue system is already up.
7. `phaseE_net.py` is experimental on this board.

## Do not cross-flash with the GW040H

The GW040H boots the primary slot (`0x80000`) and keeps `rootfs_ubi` at `0x1880000`. This GW240H boots `0x1e80000` and needs `rootfs_ubi` at `0x2a80000`. Using the wrong map overwrites the booted slot and the board dies with `Undefined Exception`.

## Credits / License

See [CREDITS.md](CREDITS.md). MIT — see [LICENSE](LICENSE).
