#!/usr/bin/env python3
"""Извлечение FWSEC (V3, FROM_HS) из VBIOS ROM — точная реплика
s_vbiosFillFlcnUcodeFromDescV3 (610.43.03). Параметры (драйвер V2-27):
pciOffset=0x9200, expansionRomOffset=0x14800, FALCON_DATA ptr=0x72C61.
Раскладка: [desc 44Б][sigs (descSize-44)][образ ALIGN_UP(StoredSize,256)]."""
import struct, sys, hashlib

data = open('/root/vbios_current_backup.rom', 'rb').read()
BASE = 0x9200
EXP = 0x14800

def u16(b, o): return struct.unpack_from('<H', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]

# токен FALCON_DATA (idx=14 в BIT@image 0x1B0)
to = BASE + 0x1B0 + 12 + 14 * 6
data_ptr = u16(data, to + 4)
table_ptr = u32(data, BASE + data_ptr)
tbl = BASE + EXP + table_ptr
ver_t, t_hdr, t_ent, t_cnt = data[tbl], data[tbl+1], data[tbl+2], data[tbl+3]
print(f'ucode table @ROM 0x{tbl:x}: ver={ver_t} hdrSz={t_hdr} entSz={t_ent} cnt={t_cnt}')

# FWSEC PROD (0x85) — как драйвер (debug off); DBG (0x45) — запасной
entries = {}
for e in range(t_cnt):
    eo = tbl + t_hdr + e * t_ent
    entries[data[eo]] = u32(data, eo + 2) + EXP
print(f'  entries: FWSEC_DBG(0x45)={hex(entries.get(0x45,0))} FWSEC_PROD(0x85)={hex(entries.get(0x85,0))}')

for appid, name in [(0x85, 'PROD'), (0x45, 'DBG')]:
    if appid not in entries:
        continue
    dp = entries[appid]
    d = BASE + dp
    vdesc = u32(data, d)
    dver = (vdesc >> 8) & 0xFF
    dsz = (vdesc >> 16) & 0xFFFF
    print(f'--- FWSEC {name} appid=0x{appid:02x} desc@ROM 0x{d:x}: vDesc=0x{vdesc:08x} ver={dver} size={dsz}')
    if dver != 3 or dsz < 44:
        print('  (не V3)'); continue
    (stored, pkc_off, iface_off, imem_phys, imem_load, imem_virt,
     dmem_phys, dmem_load, engmask16, ucodeid, sigcount, sigver16,
     reserved) = struct.unpack_from('<8IH2B2H', data, d + 4)
    print(f'  StoredSize=0x{stored:x} PKCDataOffset=0x{pkc_off:x} InterfaceOffset=0x{iface_off:x}')
    print(f'  IMEM: phys=0x{imem_phys:x} load=0x{imem_load:x} va=0x{imem_virt:x}')
    print(f'  DMEM: phys=0x{dmem_phys:x} load=0x{dmem_load:x}')
    print(f'  engMask=0x{engmask16:x} ucodeId={ucodeid} sigCount={sigcount} sigVer=0x{sigver16:x}')
    img_size = (stored + 0xFF) & ~0xFF
    sigs = data[d + 44 : d + 44 + (dsz - 44)]
    img = data[d + dsz : d + dsz + img_size]
    print(f'  sigs: {len(sigs)} б ({len(sigs)//384} x RSA3K); образ: {len(img)} б @0x{d+dsz:x}')
    if len(img) < img_size:
        print('  ВНИМАНИЕ: образ обрезан'); continue
    # проверка по драйверу: imemLoad=0xE200, dmemLoad=0x800, pkc=0x5A4, ucodeId=9
    ok = (imem_load == 0xE200 and dmem_load == 0x800 and pkc_off == 0x5A4 and ucodeid == 9)
    print(f'  сверка с драйвером: {"OK" if ok else "НЕ СОВПАДАЕТ"}')
    open('/root/cmpunlocker-efi/fwsec_ga102.bin', 'wb').write(img)
    open('/root/cmpunlocker-efi/fwsec_ga102_sigs.bin', 'wb').write(sigs)
    print(f'  fwsec_ga102.bin: {len(img)} б md5 {hashlib.md5(img).hexdigest()}')
    print(f'  fwsec_ga102_sigs.bin: {len(sigs)} б md5 {hashlib.md5(sigs).hexdigest()}')
    for i in range(sigcount):
        s = sigs[i*384:(i+1)*384]
        print(f'  sig[{i}] первые16={s[:16].hex()} md5={hashlib.md5(s).hexdigest()}')
    break
