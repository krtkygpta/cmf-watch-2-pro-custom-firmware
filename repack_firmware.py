import struct
import zlib
import lzma
import os
import sys

ORIGINAL_FW = r"cmf-watch-firmware\original.bin"
REPACKED_FW = r"repacked_cmf_firmware.bin"
CUSTOM_WF = r"C:\Users\krtky\Downloads\watchface.bin"

def repack_firmware_with_watchface(wf_path=CUSTOM_WF, output_path=REPACKED_FW):
    print("=" * 60)
    print("CMF Watch Pro 2 Firmware Watchface Injector & Repacker")
    print("=" * 60)

    if not os.path.exists(wf_path):
        print(f"Error: Custom watchface file not found at {wf_path}")
        return False

    with open(wf_path, "rb") as f:
        wf_data = f.read()

    print(f"[+] Loaded custom watchface: {wf_path} ({len(wf_data)} bytes)")
    magic, ver, name = struct.unpack("<II16s", wf_data[:24])
    name_str = name.split(b"\x00")[0].decode("latin-1", "replace")
    print(f"    Name: '{name_str}', Magic: 0x{magic:08x}, Version: {ver}")

    with open(ORIGINAL_FW, "rb") as f:
        orig_data = f.read()

    print(f"[+] Loaded base firmware: {ORIGINAL_FW} ({len(orig_data)} bytes)")

    # 1. Parse outer partition table
    # Offset 0x200 contains the partition table (each 32 bytes)
    entries = []
    for i in range(16):
        raw_entry = orig_data[0x200 + i * 32 : 0x200 + (i + 1) * 32]
        name_raw, offset, size, pad, checksum = struct.unpack("<16sIIII", raw_entry)
        part_name = name_raw.split(b"\x00")[0].decode("latin-1")
        if not part_name:
            break
        entries.append({
            "name": part_name,
            "offset": offset,
            "size": size,
            "pad": pad,
            "checksum": checksum,
            "data": orig_data[offset : offset + size]
        })

    print(f"[+] Found {len(entries)} outer partitions.")

    # 2. Extract and decompress fonts.bin (partition index 3, offset 0x0071d400)
    fonts_part = next(p for p in entries if p["name"] == "fonts.bin")
    print(f"[+] Decompressing fonts.bin partition (size {fonts_part['size']} bytes)...")

    fonts_raw = fonts_part["data"]
    decomp_fonts = bytearray()
    curr = 0
    while curr < len(fonts_raw):
        m, hdr_sz, comp_sz, dict_sz = struct.unpack("<4sIII", fonts_raw[curr : curr + 16])
        decomp_fonts.extend(lzma.decompress(fonts_raw[curr + 16 : curr + 16 + comp_sz]))
        curr += 16 + comp_sz

    print(f"[+] Decompressed fonts.bin size: {len(decomp_fonts)} bytes")

    # 3. Parse SDFS inside fonts.bin
    # Directory table in fonts.bin has 32-byte records: [name 12s, offset I, size I, pad 8s, crc I]
    # We replace local280.wfc with our custom watchface!
    TARGET_SLOT = "local280.wfc"
    print(f"[+] Locating '{TARGET_SLOT}' in fonts.bin SDFS table...")

    # We read directory records
    name_second, dir_table_end, sz_second, pad_second, crc_second = struct.unpack("<12sII8sI", decomp_fonts[32:64])
    print(f"    SDFS Directory table extends up to 0x{dir_table_end:x} (first file starts here)")

    sdfs_entries = []
    target_idx = -1
    for i in range(0, dir_table_end, 32):
        name_b, off, sz, pad, crc = struct.unpack("<12sII8sI", decomp_fonts[i : i + 32])
        e_name = name_b.split(b"\x00")[0].decode("latin-1")
        if not e_name:
            continue
        sdfs_entries.append({
            "dir_offset": i,
            "name": e_name,
            "offset": off,
            "size": sz,
            "data": bytes(decomp_fonts[off : off + sz]) if sz > 0 else b""
        })
        if e_name == TARGET_SLOT:
            target_idx = len(sdfs_entries) - 1

    if target_idx == -1:
        print(f"[-] Could not find {TARGET_SLOT} in SDFS")
        return False

    print(f"[+] Target found at index {target_idx}: current size {sdfs_entries[target_idx]['size']} bytes")
    # Replace target data
    sdfs_entries[target_idx]["data"] = wf_data
    sdfs_entries[target_idx]["size"] = len(wf_data)

    # 4. Rebuild SDFS image
    # Directory records start at 0, files start after directory table aligned to 0x40 (64 bytes)
    rebuilt_sdfs = bytearray(decomp_fonts[:dir_table_end])
    # The first file starts at dir_table_end
    current_payload_offset = dir_table_end

    for idx, e in enumerate(sdfs_entries):
        if idx == 0:  # sdfs.bin metadata entry
            continue
        # Align to 64 bytes
        if current_payload_offset % 64 != 0:
            current_payload_offset += (64 - (current_payload_offset % 64))

        e_data = e["data"]
        e_size = len(e_data)
        e_crc = zlib.crc32(e_data)

        # Update directory record in rebuilt_sdfs
        name_bytes = e["name"].encode("latin-1").ljust(12, b"\x00")
        entry_bin = struct.pack("<12sII8sI", name_bytes, current_payload_offset, e_size, b"\x00" * 8, e_crc)
        rebuilt_sdfs[e["dir_offset"] : e["dir_offset"] + 32] = entry_bin

        # Append payload
        if len(rebuilt_sdfs) < current_payload_offset:
            rebuilt_sdfs.extend(b"\x00" * (current_payload_offset - len(rebuilt_sdfs)))
        rebuilt_sdfs.extend(e_data)
        current_payload_offset += e_size

    # Update sdfs.bin total size in entry 0
    total_uncomp_size = len(rebuilt_sdfs)
    rebuilt_sdfs[16:20] = struct.pack("<I", total_uncomp_size)
    print(f"[+] Rebuilt uncompressed fonts.bin size: {total_uncomp_size} bytes")

    # 5. Recompress into 32KB LZMA blocks
    print(f"[+] Recompressing fonts.bin into 32 KB LZMA blocks...")
    compressed_fonts = bytearray()
    CHUNK_SIZE = 32768
    num_chunks = (len(rebuilt_sdfs) + CHUNK_SIZE - 1) // CHUNK_SIZE

    for c_idx in range(num_chunks):
        chunk = rebuilt_sdfs[c_idx * CHUNK_SIZE : (c_idx + 1) * CHUNK_SIZE]
        comp_chunk = lzma.compress(chunk, format=lzma.FORMAT_XZ)
        # Prefix 16-byte LZMA header: b"LZMA" + header_size(16) + comp_sz + uncomp_sz
        lzma_hdr = struct.pack("<4sIII", b"LZMA", 16, len(comp_chunk), len(chunk))
        compressed_fonts.extend(lzma_hdr)
        compressed_fonts.extend(comp_chunk)

    print(f"[+] Compressed fonts.bin size: {len(compressed_fonts)} bytes (original was {fonts_part['size']} bytes)")

    # 6. Rebuild Outer Firmware Image
    print("[+] Rebuilding outer AOTA image...")
    # Update fonts_part
    fonts_part["data"] = bytes(compressed_fonts)
    fonts_part["size"] = len(compressed_fonts)
    fonts_part["checksum"] = zlib.crc32(fonts_part["data"])

    # Update ota.xml with new sizes and uncompressed CRC32
    ota_xml_part = next(p for p in entries if p["name"] == "ota.xml")
    ota_xml_text = ota_xml_part["data"].decode("utf-8")
    
    # Update file_size, orig_size and checksum for font
    import re
    uncomp_crc_hex = f"0x{zlib.crc32(rebuilt_sdfs):X}"
    new_orig_size_hex = f"0x{len(rebuilt_sdfs):X}"
    new_file_size_hex = f"0x{len(compressed_fonts):X}"

    # Replace in XML
    def replace_partition_in_xml(xml_content, p_name, new_f_sz, new_o_sz, new_crc):
        pattern = rf"(<name>{p_name}</name>[\s\S]*?<file_size>)(0x[0-9a-fA-F]+)(</file_size>[\s\S]*?<orig_size>)(0x[0-9a-fA-F]+)(</orig_size>[\s\S]*?<checksum>)(0x[0-9a-fA-F]+)(</checksum>)"
        repl = rf"\g<1>{new_f_sz}\g<3>{new_o_sz}\g<5>{new_crc}\g<7>"
        return re.sub(pattern, repl, xml_content)

    updated_xml = replace_partition_in_xml(ota_xml_text, "font", new_file_size_hex, new_orig_size_hex, uncomp_crc_hex)
    updated_xml_bytes = updated_xml.encode("utf-8")
    ota_xml_part["data"] = updated_xml_bytes
    ota_xml_part["size"] = len(updated_xml_bytes)
    ota_xml_part["checksum"] = zlib.crc32(updated_xml_bytes)

    # Re-calculate sequential offsets (aligned to 0x200 / 512 bytes)
    curr_offset = 0x400  # First partition (ota.xml) starts at 0x400
    for p in entries:
        if curr_offset % 0x200 != 0:
            curr_offset += (0x200 - (curr_offset % 0x200))
        p["offset"] = curr_offset
        curr_offset += p["size"]

    # Assemble outer binary
    out_bin = bytearray()
    out_bin.extend(orig_data[:0x200])  # AOTA header

    # Partition table at 0x200
    ptable = bytearray()
    for p in entries:
        n_b = p["name"].encode("latin-1").ljust(16, b"\x00")
        ptable.extend(struct.pack("<16sIIII", n_b, p["offset"], p["size"], p["pad"], p["checksum"]))
    ptable = ptable.ljust(0x200, b"\x00")
    out_bin.extend(ptable)

    # Append partitions
    for p in entries:
        if len(out_bin) < p["offset"]:
            out_bin.extend(b"\x00" * (p["offset"] - len(out_bin)))
        out_bin.extend(p["data"])

    # Append AGPS tail
    tail_offset = 0x03448458
    orig_tail = orig_data[tail_offset:]
    if len(out_bin) % 0x200 != 0:
        out_bin.extend(b"\x00" * (0x200 - (len(out_bin) % 0x200)))
    out_bin.extend(orig_tail)

    with open(output_path, "wb") as f:
        f.write(out_bin)

    print(f"\n[+] SUCCESS! Generated repacked firmware: {output_path}")
    print(f"    Total size: {len(out_bin)} bytes (Original: {len(orig_data)} bytes)")
    return True

if __name__ == "__main__":
    repack_firmware_with_watchface()
