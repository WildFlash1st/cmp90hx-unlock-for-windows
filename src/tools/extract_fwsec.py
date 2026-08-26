#!/usr/bin/env python3
"""Извлечение FWSEC ucode из VBIOS ROM (репликация kgspParseFwsecUcodeFromVbiosImg).

Раскладка ROM (из kernel_gsp_vbios_tu102.c / kernel_gsp_fwsec.c):
  IFR → PCI ROM images (0x55AA + PCIR @+0x18) → BIT (0xB8FF+"BIT\0") → токены
  BIT_TOKEN_FALCON_DATA(0x70,v2) → FALCON_UCODE_TABLE → записи (appid 0x05/0x45/0x85)
  → FALCON_UCODE_DESC (V2 "15d" / V3 "9d1w2b2w") → код/данные в образе.

Все смещения BIT-парсера — ОТНОСИТЕЛЬНО базового VBIOS-образа (pciOffset).
"""
import struct, sys, hashlib

BIT_HEADER_ID = 0xB8FF
BIT_HEADER_SIG = 0x00544942
FALCON_DATA_TOKEN_ID = 0x70
FWSEC_LIC = 0x05     # FIRMWARE_SEC_LIC
FWSEC_DBG = 0x45
FWSEC_PROD = 0x85

def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def u32(b, o): return struct.unpack_from("<I", b, o)[0]

def find_pci_image_base(img):
    """Найти базовый PCI ROM образ: 0x55AA + валидный PCIR по ptr@0x18."""
    for i in range(0, len(img) - 0x20):
        if img[i:i+2] != b'\x55\xaa':
            continue
        pcir_off = i + u16(img, i + 0x18)
        if pcir_off + 0x18 <= len(img) and img[pcir_off:pcir_off+4] == b'PCIR':
            return i
    return None

def find_bit_header(img, base):
    for addr in range(base, len(img) - 8):
        if u16(img, addr) == BIT_HEADER_ID and u32(img, addr + 2) == BIT_HEADER_SIG:
            hdr_sz = img[addr + 8]
            if addr + hdr_sz <= len(img) and (sum(img[addr:addr+hdr_sz]) & 0xFF) == 0:
                return addr
    return None

def parse(vbios_path, want_debug=False):
    img = open(vbios_path, "rb").read()
    print(f"ROM: {len(img)} байт")
    base = find_pci_image_base(img)
    if base is None:
        print("PCI ROM образ не найден"); return
    print(f"PCI image base @0x{base:x} (device 0x{u16(img, base+0x18+6):04x}:0x{u16(img, base+0x18+4):04x})")
    bit = find_bit_header(img, base)
    if bit is None:
        print("BIT header не найден"); return
    print(f"BIT header @0x{bit:x} (image 0x{bit-base:x})")
    hdr_sz = img[bit + 8]; tok_sz = img[bit + 9]; entries = img[bit + 10]
    print(f"  headerSize={hdr_sz} tokenSize={tok_sz} entries={entries}")
    tok_base = bit + hdr_sz
    for i in range(entries):
        to = tok_base + i * tok_sz
        tid = img[to]; ver = img[to + 1]
        if tok_sz >= 8:
            data_size = u16(img, to + 2); data_ptr = u32(img, to + 4)
        else:
            data_size = u16(img, to + 2); data_ptr = u16(img, to + 4)
        if tid != FALCON_DATA_TOKEN_ID or ver != 2:
            continue
        # FALCON_DATA_V2: u32 FalconUcodeTablePtr (offset в образе)
        table_ptr = u32(img, base + data_ptr) if data_ptr + 4 <= len(img) else 0
        print(f"  FALCON_DATA токен: data@image 0x{data_ptr:x} -> ucodeTable @image 0x{table_ptr:x} (ROM 0x{base+table_ptr:x})")
        tbl = table_ptr
        if base + tbl + 6 > len(img):
            print("  таблица вне образа"); continue
        ver_t, t_hdr, t_ent, t_cnt = img[base+tbl], img[base+tbl+1], img[base+tbl+2], img[base+tbl+3]
        print(f"  ucode table: ver={ver_t} hdrSz={t_hdr} entSz={t_ent} cnt={t_cnt}")
        if ver_t != 1 or t_hdr < 6 or t_ent < 6:
            print("  неверный формат таблицы"); continue
        for e in range(t_cnt):
            eo = tbl + t_hdr + e * t_ent
            appid = img[base+eo]; desc_ptr = u32(img, base + eo + 2)
            print(f"    entry[{e}]: appid=0x{appid:02x} descPtr=0x{desc_ptr:x}")
            if appid not in (FWSEC_LIC, FWSEC_DBG, FWSEC_PROD):
                continue
            if want_debug and appid != FWSEC_DBG: continue
            if not want_debug and appid in (FWSEC_DBG,): continue
            vdesc = u32(img, base + desc_ptr)
            dver = (vdesc >> 8) & 0xFF
            dsz = (vdesc >> 16) & 0xFFFF
            print(f"    FWSEC appid=0x{appid:02x}: vDesc=0x{vdesc:08x} ver={dver} size={dsz}")
            if dver == 2 and dsz >= 60:
                d = struct.unpack_from("<15I", img, base + desc_ptr + 4)
                (stored, uncomp, ventry, iface_off, imem_phys, imem_load,
                 imem_virt, imem_sec_base, imem_sec_size, dmem_off, dmem_phys,
                 dmem_load, alt_imem, alt_dmem) = d
            elif dver == 3 and dsz >= 44:
                # V3 "9d1w2b2w"
                d = struct.unpack_from("<9I2HI", img, base + desc_ptr + 4)
                (stored, pkc_off, iface_off, imem_phys, imem_load, imem_virt,
                 dmem_phys, dmem_load, engmask16, ucodeid, sigcount, sigver16,
                 reserved) = d
                imem_sec_base = imem_sec_size = dmem_off = 0
            else:
                print("    неизвестный формат desc"); continue
            print(f"      stored={stored} virtEntry={ventry} ifaceOff=0x{iface_off:x}")
            print(f"      imemPhys=0x{imem_phys:x} imemLoad=0x{imem_load:x} imemVirt=0x{imem_virt:x}")
            if imem_sec_base: print(f"      imemSecBase=0x{imem_sec_base:x} imemSecSize=0x{imem_sec_size:x}")
            print(f"      dmemOff=0x{dmem_off:x} dmemPhys=0x{dmem_phys:x} dmemLoad=0x{dmem_load:x}")
            # код: desc_ptr+60 (V2) или +44 (V3); данные: dmemOff от desc_ptr
            desc_sz = 60 if dver == 2 else 44
            code_off = base + desc_ptr + desc_sz
            data_off = base + desc_ptr + dmem_off
            code = img[code_off:code_off + imem_load]
            data = img[data_off:data_off + dmem_load]
            print(f"      code @0x{code_off:x} +0x{imem_load:x} ({len(code)} б), data @0x{data_off:x} +0x{dmem_load:x} ({len(data)} б)")
            if len(code) < imem_load or len(data) < dmem_load:
                print("      ВНИМАНИЕ: образ короче ожидаемого (обрезка)")
            tag = "dbg" if appid == FWSEC_DBG else ("lic" if appid == FWSEC_LIC else "prod")
            out = f"/root/cmpunlocker-efi/fwsec_{tag}.bin"
            open(out, "wb").write(code + data)
            print(f"      -> {out} ({len(code)+len(data)} б), md5 {hashlib.md5(code+data).hexdigest()}")
            open(f"/root/cmpunlocker-efi/fwsec_{tag}.desc", "wb").write(img[base+desc_ptr:base+desc_ptr+desc_sz])
            return
    print("FWSEC не найден")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/root/vbios_current_backup.rom"
    debug = "--dbg" in sys.argv
    parse(path, debug)
