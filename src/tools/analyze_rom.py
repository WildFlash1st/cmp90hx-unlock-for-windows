import struct
data = open('/root/vbios_current_backup.rom','rb').read()
def u16(o): return struct.unpack_from('<H', data, o)[0]
def u32(o): return struct.unpack_from('<I', data, o)[0]
print('ROM size:', hex(len(data)))
print('--- ROM start (PCI ROM header?):')
for o in range(0, 0x40, 16):
    print(f'  {o:06x}: {data[o:o+16].hex()}')
print('--- bytes @0x230..0x430 (token data area):')
for o in range(0x230, 0x430, 16):
    print(f'  {o:06x}: {data[o:o+16].hex()}')
print('--- all BIT signatures:')
for i in range(len(data)-4):
    if data[i:i+4] == b'BIT\0':
        print(f'  BIT@0x{i:x}: prev2={data[i-2:i].hex()}')
