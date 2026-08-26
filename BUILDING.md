# Building from source

All build variants come from a single source file, `src/unlock_v2.c`, compiled
with [gnu-efi](https://github.com/ncroxon/gnu-efi). Build flags are
load-bearing: they decide which phases even exist in the binary (see the flag
table below — v3.01 was accidentally compute-only because one flag was
missing).

## 1. Prerequisites

```bash
# Debian/Ubuntu
apt install build-essential gnu-efi python3
```

Tested with gcc 12 and gnu-efi 3.0.15 on x86_64 Linux.

## 2. Firmware/payload blobs (not distributed here)

The blobs are embedded into the binary at link time. They are **not** in this
repository: most of them are extracted from NVIDIA's signed driver/VBIOS
images, and one is an exploit payload. You have to produce them yourself:

| Blob | Size | What it is / where it comes from |
|---|---|---|
| `v67_payload.bin` | `0xFA00` | The oversized "signature" that trips the booter canary bug. From bendy2's public CMP90HX research (see README credits). |
| `booter_ucode_prod_patched.bin` | `0xEC00` | SEC2 booter ucode from driver **bindata** (`BINDATA_LABEL_IMAGE_PROD`), with `SIG_PROD[0]` patched at offset `0x8A10`. Procedure: [docs/RE-PATCH-PROCEDURE.md](docs/RE-PATCH-PROCEDURE.md). |
| `booter_ucode_dbg_patched.bin` | `0xEC00` | Same for the DBG variant (`BINDATA_LABEL_IMAGE_DBG` + `SIG_DBG[0]`). Rejected by PROD fuses in the real flow, but still linked/referenced. |
| `gsp_rm_boot_dbg.bin` | `0x6000` | GSP bootloader (GspRmBoot) extracted from the driver. |
| `fwsec_ga102.bin` + `fwsec_ga102_sig.bin` | `0xEA00` + `0x180` | FWSEC ucode + signature, extracted from the card's VBIOS ROM with [`src/tools/extract_fwsec.py`](src/tools/extract_fwsec.py) (replicates `kgspParseFwsecUcodeFromVbiosImg`). |
| `sec2_ucode_vbios_49_patched.bin` / `_89_` | ~20 KB each | SEC2 ucode appid `0x49`/`0x89` from VBIOS, sig[2] patched. Only used by dev-experiment stages. |

Put the eight files into a directory and point the build at it:

```
blobs/
├── v67_payload.bin
├── booter_ucode_dbg_patched.bin
├── booter_ucode_prod_patched.bin
├── gsp_rm_boot_dbg.bin
├── fwsec_ga102.bin
├── fwsec_ga102_sig.bin
├── sec2_ucode_vbios_49_patched.bin
└── sec2_ucode_vbios_89_patched.bin
```

Additionally you need `gsp_ga10x.bin` at runtime (NOT embedded) — copy it from
the NVIDIA **610.43.03** package (`/lib/firmware/nvidia/610.43.03/gsp_ga10x.bin`)
to the USB stick next to `BOOTX64.EFI`.

## 3. Build

```bash
cd src
BLOBS=/path/to/blobs bash build.sh     # or put blobs into src/blobs/
```

Outputs (all built from the same `unlock_v2.c`):

| Binary | Flags | Notes |
|---|---|---|
| `unlock_v3n.efi` | `RELEASE_BUILD MULTI_CARD PCIE_GEN2_REJOIN FULL_NOGEN2` | **Current release (v3.03)** — use this on real hardware |
| `unlock_v3f.efi` | `…PCIE_GEN2_REJOIN` | v3.02-full: adds gen2 link config; known Code 43 issue, see KNOWN-ISSUES |
| `unlock_v3.efi` | `RELEASE_BUILD MULTI_CARD` | v3.01: compute-only (no render table!) |
| `unlock_v2.efi` | dev | Interactive pauses, gen experiments |
| `unlock_v2_test.efi`, `unlock_v3n_test.efi` | +`EFI_AUTOTEST` | QEMU test stand |
| `unlock_v2_wr.efi` | `ENDGAME_WARMRESET` | Plan-B endgame, unused |

Reference checksums of the released binaries (built against our blob set):

```
e27221f5ddd563602423b035b3274f2d  unlock_v3n.efi   (v3.03 release)
cb2345612306e8b853bbcb3ab132478c  unlock_v3f.efi   (v3.02-full)
```

Your md5 will differ if your blobs differ — what matters is that the banner
printed at boot identifies the variant.

## 4. Make the USB image

Classic **MBR + FAT32 with partition type `0xEF`** — both details matter:
GPT images break on sticks with stale backup-GPT tails, and some AMI firmwares
refuse to enumerate removable USB as a boot option unless the MBR partition
type is EFI System.

```bash
IMG=cmp90-unlock.img
truncate -s 256M $IMG
printf 'label: dos\nunit: sectors\n\n%s1 : start=2048, size=522240, type=ef, bootable\n' "$IMG" | sfdisk $IMG
LOOP=$(losetup -P -f --show $IMG)
mkfs.vfat -F 32 -n CMP90UNLOCK "${LOOP}p1"
mount "${LOOP}p1" /mnt/img
mkdir -p /mnt/img/EFI/BOOT
cp unlock_v3n.efi /mnt/img/EFI/BOOT/BOOTX64.EFI
cp /lib/firmware/nvidia/610.43.03/gsp_ga10x.bin /mnt/img/
sync && umount /mnt/img && losetup -d "$LOOP"
```

Write with `dd` to the whole stick (Rufus DD-mode / balenaEtcher also work).

## 5. Verify before flashing

Historical trap: an "updated" image shipped with the OLD bootloader inside.
Always check the content of the image, not just the file:

```bash
LOOP=$(losetup -P -f --show $IMG); mount "${LOOP}p1" /mnt/img
md5sum /mnt/img/EFI/BOOT/BOOTX64.EFI          # == md5sum unlock_v3n.efi
python3 -c "print('v3.03 FULL-NOGEN2'.encode('utf-16-le') in open('/mnt/img/EFI/BOOT/BOOTX64.EFI','rb').read())"
umount /mnt/img; fsck.vfat -n "${LOOP}p1"; losetup -d "$LOOP"
```
