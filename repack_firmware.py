import struct
import zlib
import lzma
import os
import re

ORIGINAL_FW = r"..\cmf-watch-firmware\original.bin"
REPACKED_FW = r"repacked_cmf_firmware.bin"
CUSTOM_WF = r"C:\Users\krtky\Downloads\watchface.bin"

NEW_VERSION_NAME = "1.00_2508181820"
NEW_VERSION_CODE = 0x20000

def bump_and_repack():
    print("=" * 65)
    print("CMF Watch Pro 2 - Version Bump & Repacker (Anti-Rollback Bypass)")
    print(f"Target Version Name: {NEW_VERSION_NAME}")
    print(f"Target Version Code: 0x{NEW_VERSION_CODE:X} ({NEW_VERSION_CODE})")
    print("=" * 65)

    with open(CUSTOM_WF, "rb") as f:
        wf_data = f.read()
    with open(ORIGINAL_FW, "rb") as f:
        orig_data = f.read()

    # 1. Parse outer partition table
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

    # 2. Decompress and modify fonts.bin with custom watchface
    fonts_part = next(p for p in entries if p["name"] == "fonts.bin")
    fonts_raw = fonts_part["data"]
    decomp_fonts = bytearray()
    curr = 0
    while curr < len(fonts_raw):
        m, hdr_sz, comp_sz, dict_sz = struct.unpack("<4sIII", fonts_raw[curr : curr + 16])
        decomp_fonts.extend(lzma.decompress(fonts_raw[curr + 16 : curr + 16 + comp_sz]))
        curr += 16 + comp_sz

    TARGET_SLOT = "local280.wfc"
    name_second, dir_table_end, sz_second, pad_second, crc_second = struct.unpack("<12sII8sI", decomp_fonts[32:64])
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

    sdfs_entries[target_idx]["data"] = wf_data
    sdfs_entries[target_idx]["size"] = len(wf_data)

    rebuilt_sdfs = bytearray(decomp_fonts[:dir_table_end])
    current_payload_offset = dir_table_end
    for idx, e in enumerate(sdfs_entries):
        if idx == 0: continue
        if current_payload_offset % 64 != 0:
            current_payload_offset += (64 - (current_payload_offset % 64))
        e_data = e["data"]
        e_size = len(e_data)
        e_crc = zlib.crc32(e_data)
        name_bytes = e["name"].encode("latin-1").ljust(12, b"\x00")
        entry_bin = struct.pack("<12sII8sI", name_bytes, current_payload_offset, e_size, b"\x00" * 8, e_crc)
        rebuilt_sdfs[e["dir_offset"] : e["dir_offset"] + 32] = entry_bin
        if len(rebuilt_sdfs) < current_payload_offset:
            rebuilt_sdfs.extend(b"\x00" * (current_payload_offset - len(rebuilt_sdfs)))
        rebuilt_sdfs.extend(e_data)
        current_payload_offset += e_size

    total_uncomp_size = len(rebuilt_sdfs)
    rebuilt_sdfs[16:20] = struct.pack("<I", total_uncomp_size)

    # Recompress fonts.bin in 32KB blocks
    compressed_fonts = bytearray()
    CHUNK_SIZE = 32768
    num_chunks = (len(rebuilt_sdfs) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for c_idx in range(num_chunks):
        chunk = rebuilt_sdfs[c_idx * CHUNK_SIZE : (c_idx + 1) * CHUNK_SIZE]
        comp_chunk = lzma.compress(chunk, format=lzma.FORMAT_XZ)
        lzma_hdr = struct.pack("<4sIII", b"LZMA", 16, len(comp_chunk), len(chunk))
        compressed_fonts.extend(lzma_hdr)
        compressed_fonts.extend(comp_chunk)

    fonts_part["data"] = bytes(compressed_fonts)
    fonts_part["size"] = len(compressed_fonts)
    fonts_part["checksum"] = zlib.crc32(fonts_part["data"])

    # 3. Modify TEMP.bin (inner container) version!
    temp_part = next(p for p in entries if p["name"] == "TEMP.bin")
    temp_raw = temp_part["data"]
    decomp_temp = bytearray()
    curr = 0
    while curr < len(temp_raw):
        m, hdr_sz, comp_sz, dict_sz = struct.unpack("<4sIII", temp_raw[curr : curr + 16])
        decomp_temp.extend(lzma.decompress(temp_raw[curr + 16 : curr + 16 + comp_sz]))
        curr += 16 + comp_sz

    # Bump version in TEMP.bin outer header (offset 0x40 and 0x7c)
    decomp_temp[0x40 : 0x40 + 32] = NEW_VERSION_NAME.encode("latin-1").ljust(32, b"\x00")
    decomp_temp[0x7c : 0x80] = struct.pack("<I", NEW_VERSION_CODE)

    # Bump version in TEMP.bin inner ota.xml at offset 0x400
    inner_xml = decomp_temp[0x400 : 0x400 + 952].decode("utf-8")
    inner_xml = re.sub(r"<version_code>0x[0-9a-fA-F]+</version_code>", f"<version_code>0x{NEW_VERSION_CODE:X}</version_code>", inner_xml)
    inner_xml = re.sub(r"<version_res>0x[0-9a-fA-F]+</version_res>", f"<version_res>0x{NEW_VERSION_CODE:X}</version_res>", inner_xml)
    inner_xml = re.sub(r"<version_name>.*?</version_name>", f"<version_name>{NEW_VERSION_NAME}</version_name>", inner_xml)
    inner_xml_bytes = inner_xml.encode("utf-8")
    decomp_temp[0x400 : 0x400 + len(inner_xml_bytes)] = inner_xml_bytes
    # Update inner partition table checksum for inner ota.xml at 0x200
    decomp_temp[0x200 + 16 + 8 : 0x200 + 16 + 12] = struct.pack("<I", zlib.crc32(inner_xml_bytes))

    # Recompress TEMP.bin (uses 2MB chunks)
    compressed_temp = bytearray()
    TEMP_CHUNK = 2097152
    num_t_chunks = (len(decomp_temp) + TEMP_CHUNK - 1) // TEMP_CHUNK
    for c_idx in range(num_t_chunks):
        chunk = decomp_temp[c_idx * TEMP_CHUNK : (c_idx + 1) * TEMP_CHUNK]
        comp_chunk = lzma.compress(chunk, format=lzma.FORMAT_XZ)
        lzma_hdr = struct.pack("<4sIII", b"LZMA", 16, len(comp_chunk), len(chunk))
        compressed_temp.extend(lzma_hdr)
        compressed_temp.extend(comp_chunk)

    temp_part["data"] = bytes(compressed_temp)
    temp_part["size"] = len(compressed_temp)
    temp_part["checksum"] = zlib.crc32(temp_part["data"])

    # 4. Bump version in outer ota.xml
    ota_xml_part = next(p for p in entries if p["name"] == "ota.xml")
    ota_xml_text = ota_xml_part["data"].decode("utf-8")
    ota_xml_text = re.sub(r"<version_code>0x[0-9a-fA-F]+</version_code>", f"<version_code>0x{NEW_VERSION_CODE:X}</version_code>", ota_xml_text)
    ota_xml_text = re.sub(r"<version_res>0x[0-9a-fA-F]+</version_res>", f"<version_res>0x{NEW_VERSION_CODE:X}</version_res>", ota_xml_text)
    ota_xml_text = re.sub(r"<version_name>.*?</version_name>", f"<version_name>{NEW_VERSION_NAME}</version_name>", ota_xml_text)

    # Update font partition entries in ota.xml
    uncomp_crc_hex = f"0x{zlib.crc32(rebuilt_sdfs):X}"
    new_orig_size_hex = f"0x{len(rebuilt_sdfs):X}"
    new_file_size_hex = f"0x{len(compressed_fonts):X}"
    pattern_font = r"(<name>font</name>[\s\S]*?<file_size>)(0x[0-9a-fA-F]+)(</file_size>[\s\S]*?<orig_size>)(0x[0-9a-fA-F]+)(</orig_size>[\s\S]*?<checksum>)(0x[0-9a-fA-F]+)(</checksum>)"
    ota_xml_text = re.sub(pattern_font, rf"\g<1>{new_file_size_hex}\g<3>{new_orig_size_hex}\g<5>{uncomp_crc_hex}\g<7>", ota_xml_text)

    # Update TEMP partition entries in ota.xml
    pattern_temp = r"(<name>fw0_temp</name>[\s\S]*?<file_size>)(0x[0-9a-fA-F]+)(</file_size>[\s\S]*?<orig_size>)(0x[0-9a-fA-F]+)(</orig_size>[\s\S]*?<checksum>)(0x[0-9a-fA-F]+)(</checksum>)"
    temp_uncomp_crc = f"0x{zlib.crc32(temp_part['data']):X}"
    temp_sz_hex = f"0x{len(compressed_temp):X}"
    ota_xml_text = re.sub(pattern_temp, rf"\g<1>{temp_sz_hex}\g<3>{temp_sz_hex}\g<5>{temp_uncomp_crc}\g<7>", ota_xml_text)

    updated_xml_bytes = ota_xml_text.encode("utf-8")
    ota_xml_part["data"] = updated_xml_bytes
    ota_xml_part["size"] = len(updated_xml_bytes)
    ota_xml_part["checksum"] = zlib.crc32(updated_xml_bytes)

    # 5. Calculate sequential offsets aligned to 0x200
    curr_offset = 0x400
    for p in entries:
        if curr_offset % 0x200 != 0:
            curr_offset += (0x200 - (curr_offset % 0x200))
        p["offset"] = curr_offset
        curr_offset += p["size"]

    # 6. Assemble outer binary with bumped outer AOTA header
    out_bin = bytearray()
    outer_header = bytearray(orig_data[:0x200])
    outer_header[0x40 : 0x40 + 32] = NEW_VERSION_NAME.encode("latin-1").ljust(32, b"\x00")
    outer_header[0x7c : 0x80] = struct.pack("<I", NEW_VERSION_CODE)
    out_bin.extend(outer_header)

    # Partition table at 0x200
    ptable = bytearray()
    for p in entries:
        n_b = p["name"].encode("latin-1").ljust(16, b"\x00")
        ptable.extend(struct.pack("<16sIIII", n_b, p["offset"], p["size"], p["pad"], p["checksum"]))
    ptable = ptable.ljust(0x200, b"\x00")
    out_bin.extend(ptable)

    for p in entries:
        if len(out_bin) < p["offset"]:
            out_bin.extend(b"\x00" * (p["offset"] - len(out_bin)))
        out_bin.extend(p["data"])

    # AGPS tail
    tail_offset = 0x03448458
    orig_tail = orig_data[tail_offset:]
    if len(out_bin) % 0x200 != 0:
        out_bin.extend(b"\x00" * (0x200 - (len(out_bin) % 0x200)))
    out_bin.extend(orig_tail)

    with open(REPACKED_FW, "wb") as f:
        f.write(out_bin)

    print(f"\n[+] SUCCESS! Generated bumped firmware: {REPACKED_FW} ({len(out_bin)} bytes)")
    print(f"    New Version Name: {NEW_VERSION_NAME}")
    print(f"    New Version Code: 0x{NEW_VERSION_CODE:X}")
    return True

if __name__ == "__main__":
    bump_and_repack()
