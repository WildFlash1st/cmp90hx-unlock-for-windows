#!/usr/bin/env python3
# Анализ debug booter GA102 (RISC-V): поиск WPR-meta парсинга и сигнатурной обработки
import sys
from capstone import Cs, CS_ARCH_RISCV, CS_MODE_RISCV64

IMG = "/root/booter_ga102_bindata_label_image_dbg.bin"
data = open(IMG, "rb").read()
print(f"image size: 0x{len(data):x}")

# app code: 0x100 .. 0x8A00 (RISC-V)
code = data[0x100:0x8A00]
md = Cs(CS_ARCH_RISCV, CS_MODE_RISCV64)
md.detail = True

# 1) ищем 32-битные константы в коде (поиск по дампу)
import struct
def find_dwords(*vals):
    res = {}
    for v in vals:
        b = struct.pack("<I", v)
        offs = []
        i = 0
        while True:
            j = code.find(b, i)
            if j < 0: break
            offs.append(j + 0x100)
            i = j + 1
        res[hex(v)] = offs
    return res

hits = find_dwords(0xdc3aae21, 0x371a60b3, 0xffffffff, 0x823804, 0x80, 0xa0a0a0a0)
for k, v in hits.items():
    print(f"const {k}: offsets {[hex(x) for x in v[:20]]}")

# 2) дизассемблируем вокруг найденных magic-оффсетов
print("\n=== вокруг magic 0xdc3aae21 ===")
for off in hits[hex(0xdc3aae21)][:4]:
    start = max(0x100, off - 0x40)
    for ins in md.disasm(code[start-0x100:off-0x100+0x80], start):
        print(f"  0x{ins.address:06x}: {ins.mnemonic:8s} {ins.op_str}")
    print("  ---")
