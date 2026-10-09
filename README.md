# CMF Watch Pro 2 - Custom Firmware Flashing Guide

This repository contains the tools, architecture specifications, and instructions for flashing custom/repacked firmware onto the **CMF Watch Pro 2** (Actions ATS3089C SoC / board `jx402_01_3089c`).

---

## ⚠️ Warning & Brick Risk
The CMF Watch Pro 2 does **not** have an external recovery mode or USB port. If an invalid or corrupted firmware image is written to flash and the Bluetooth radio fails to boot, recovery requires opening the watch chassis and soldering directly to the internal SWD pins (SWDIO/SWCLK) using an ST-Link/J-Link programmer.

---

## ⚡ How to Flash the Firmware Image (`.bin`)

There are two verified methods to flash the generated `repacked_cmf_firmware.bin` (56 MB) to the watch:

---

### Method 1: The Local OTA Proxy Method (Most Reliable)

This method uses your PC to serve the repacked `.bin` file while letting the official phone app (Nothing X / CMF Watch) execute the Bluetooth transfer using its built-in, vetted OTA transfer protocol.

#### Step 1: Host the firmware on your PC
In this directory on your computer, start a local HTTP server:
```bash
python -m http.server 8080
```
Find your PC's local IP address (e.g. `192.168.1.50`).
Verify you can download the file by opening `http://192.168.1.50:8080/repacked_cmf_firmware.bin` in your browser.

#### Step 2: Intercept the phone's update check
1. On your phone (connected to the same Wi-Fi network as your PC), install an HTTP proxy tool such as **mitmproxy**, **Charles Proxy**, or **HTTP Canter / Reqable**.
2. Configure your phone's Wi-Fi proxy settings to point to your PC's IP and proxy port.
3. Open the **CMF Watch / Nothing X app** and navigate to:
   `Device Settings -> Firmware Update -> Check for Updates`.
4. In your proxy, intercept the JSON response from Nothing's OTA server.
5. Replace the firmware download URL field in the response with:
   ```json
   "url": "http://<YOUR_PC_IP>:8080/repacked_cmf_firmware.bin"
   ```
6. Update the `file_size` (56,045,040 bytes) and MD5 in the JSON response if required by the app.

#### Step 3: Trigger the Flash
1. Tap **Update Now** in the CMF app.
2. The app downloads `repacked_cmf_firmware.bin` from your PC.
3. The app puts the watch into OTA mode and uploads the 56 MB package over Bluetooth Low Energy.
4. The watch screen will display the OTA progress circle and reboot once complete.

---

### Method 2: Android Gadgetbridge FW/App Installer

Gadgetbridge supports the CMF Watch Pro 2 over Bluetooth LE without requiring a proprietary authentication key.

1. **Install Gadgetbridge**:
   Install the latest [Gadgetbridge APK](https://gadgetbridge.org/) (v0.94.0 or newer) on an Android phone.
2. **Pair with Watch**:
   * Turn OFF Bluetooth on other phones so the watch is in advertising mode.
   * In Gadgetbridge, tap **+ (Add Device)** $\rightarrow$ select **CMF Watch Pro 2**.
   * Pair directly (no auth key required).
3. **Send the Firmware**:
   * Copy `repacked_cmf_firmware.bin` to your phone's storage.
   * In any Android file manager, locate `repacked_cmf_firmware.bin` and select **Open with...**.
   * Choose **Gadgetbridge FW/App Installer**.
   * Tap **Install** to initiate the Bluetooth transfer to the watch bootloader.

---

## 🛠️ Firmware Structure & Repacking Tools

* **`repack_firmware.py`**:
  Unpacks, modifies SDFS partitions, compresses into 32 KB LZMA blocks with the 16-byte `b"LZMA"` headers, updates XML partition descriptors, and calculates IEEE 802.3 CRC-32 checksums.
* **Firmware Partition Map**:
  * `0x00000400`: `ota.xml` (Partition manifest & uncompressed CRC32)
  * `0x00000C00`: `TEMP.bin` (Nested AOTA container holding `app.bin` / Zephyr RTOS)
  * `0x0013FE00`: `res.bin` (UI icons and themes)
  * `0x0071D400`: `fonts.bin` (System typography & preloaded dials)
  * `0x00E8BE00`: `res_e.bin` (Extended watchface animations `1.ajs` - `19.ajs`)
  * `0x033F7600`: `sdfs_k.bin` (System ringtones `.act` and FCC certificates)
  * `0x03448458`: `AGPS` (GNSS positioning binary)

### Generating a New Binary:
```bash
python repack_firmware.py
```
Outputs `repacked_cmf_firmware.bin` ready for OTA flashing.
