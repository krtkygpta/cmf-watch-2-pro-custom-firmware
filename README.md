# CMF Watch Pro 2 - Custom Firmware & Web Flasher

This repository provides tools, repacked firmware, and flashing instructions for the **CMF Watch Pro 2 (by Nothing)** running on the **Actions Technology ATS3089C SoC** (`jx402_01_3089c`).

---

## ⚠️ Important Disclaimer & Warnings

* Modifying and flashing custom firmware to an embedded microcontroller carries an inherent risk of **bricking the device**.
* The CMF Watch Pro 2 does **not** have an external hardware recovery button (like DFU/fastboot). If an invalid image is flashed and the Bluetooth radio fails to boot, recovery requires opening the watch case to connect an SWD hardware debugger (ST-Link/J-Link).
* Proceed at your own risk. Only flash devices you are prepared to troubleshoot or recover.

---

## 📦 What Is In This Repository

1. **`repack_firmware.py`**:
   Full unpacker, SDFS editor, and AOTA repacker script. It extracts partitions, swaps watchface assets, compresses data into 32 KB LZMA/XZ blocks with official 16-byte headers, updates XML descriptors, and recalculates CRC-32 checksums.
2. **`web_flasher.html`**:
   A Chromium Web Bluetooth interface to connect, inspect GATT services, and communicate with the watch directly from a PC without installing Android ADB or vendor software.
3. **Firmware Architecture Documentation**:
   Technical documentation on the AOTA container format, SDFS filesystem, and Bluetooth LE protocol.

---

## ⚡ How to Flash the Watch Using a PC

There are two primary ways to flash or upload custom watchfaces from your computer:

### Option 1: Direct Web Bluetooth (Fastest & Safest)
The CMF Watch Pro 2 supports direct Web Bluetooth connections from Chromium browsers (Google Chrome, Microsoft Edge, Brave, Opera) on Windows, macOS, and Linux.

1. **Disconnect from Phone**:
   * Turn **OFF** Bluetooth on your smartphone (or force-close the Nothing X / CMF Watch app).
   * *Reason:* The watch can only maintain one active Bluetooth connection. Disconnecting from your phone allows the watch to advertise to your PC.
2. **Open the Web Flasher**:
   * You can open the included `web_flasher.html` in Chrome/Edge, or use the online portal at:
     👉 **[https://fmc.freethinkel.dev](https://fmc.freethinkel.dev)**
3. **Connect to the Watch**:
   * Click **Connect**.
   * A browser pop-up will appear scanning for Bluetooth devices.
   * Select your **CMF Watch Pro 2** from the list and confirm pairing.
   * *Note: The CMF Watch Pro 2 does NOT require an authentication key for pairing (unlike the Gen 1 watch).*
4. **Flash the Watchface**:
   * Select your `.bin` watchface file (e.g. `watchface.bin`).
   * Click **Flash / Upload**.
   * The file streams over BLE directly to the watch's storage slot in ~20–30 seconds.

---

### Option 2: Full Firmware Flash via Local OTA Server

If you want to flash the entire repacked 56 MB OS image (`repacked_cmf_firmware.bin`):

1. **Host the Firmware on your PC**:
   In the repository folder, start a local Python HTTP server:
   ```bash
   python -m http.server 8080
   ```
   Note your PC's local IP address (e.g. `192.168.1.50`).

2. **Intercept the Official App Update**:
   * Install **mitmproxy** or an HTTP proxy on the phone running the Nothing X / CMF Watch app.
   * When checking for firmware updates, intercept the OTA JSON response and replace the download URL with:
     `http://<YOUR_PC_IP>:8080/repacked_cmf_firmware.bin`
   * The official app will download the repacked firmware from your PC and flash it over BLE using the official OTA bootloader protocol.

---

## 🛠️ Technical Details & Firmware Layout

* **Base Board**: `jx402_01_3089c`
* **SoC**: Actions Technology ATS3089C (ARM Cortex-M33 @ 24MHz/96MHz + DSP)
* **OS**: Zephyr RTOS (v3.x) with LVGL Graphics Framework
* **Container Format**: Actions AOTA (Starts with `AOTA` magic at `0x0000`)
* **Checksum Verification**: Standard IEEE 802.3 CRC-32 on all partitions and descriptors.

### Partition Table:
| Partition | Target Flash | Contents |
| :--- | :--- | :--- |
| `ota.xml` | Host Manifest | XML Partition and Checksum Descriptor |
| `TEMP.bin` | Internal Flash | Zephyr RTOS Kernel (`app.bin`) & System Config (`sdfs.bin`) |
| `res.bin` | Storage Flash | LVGL Icons, Vector Assets, and UI Themes |
| `fonts.bin`| Storage Flash | System Fonts (`.font`) & Preloaded Watchfaces (`.wfc`) |
| `res_e.bin`| Storage Flash | Extended Watchface Animation Bundles (`1.ajs` - `19.ajs`) |
| `sdfs_k.bin`| Storage Flash | System Audio Ringtones (`.act`) & Regulatory Data |
| `AGPS` | Co-processor | Assisted GPS Ephemeris & GNSS Engine |

---

## 📜 How to Generate Your Own Repacked Firmware

Run the included Python repacker script:
```bash
python repack_firmware.py
```
This will automatically verify partition checksums, recompress into 32 KB blocks, and produce `repacked_cmf_firmware.bin`.
