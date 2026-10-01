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

Tested on x86_64 Linux. Known-good toolchains: Debian 12 (gcc 12.2,
binutils 2.40, gnu-efi 3.0.15) and Ubuntu 24.04 (gnu-efi 3.0.17).

> **gnu-efi ≥ 3.0.18 pitfall (hit on Debian 13 / trixie).** 3.0.18 moved
> `*(.rodata*)` out of the `.data` output section into its own `.rodata`
> section. Every wide string literal (`L"..."`: all `Print` text and the boot
> banner) lands there, so an `objcopy` line that forgets `-j .rodata*` still
> produces an `.efi` — it links and is the right size — but the strings are not
> in the image, so at boot the app prints garbage and hangs. `src/build.sh`
> keeps `.rodata*`, so building through it works on both old and new gnu-efi.
> If you assemble the toolchain by hand, add `-j .rodata*`.

## 2. Firmware/payload blobs (not distributed here)

The blobs are embedded into the binary at link time. They are **not** in this
repository: most of them are extracted from NVIDIA's signed driver/VBIOS
images, and one is an exploit payload. You have to produce them yourself.
`src/build.sh` checks for all eight and refuses to build if any is missing —
there is no way around this, every variant links the same set (even the
compute-only one).

Two things the columns below do not make obvious: the SEC2 booter and the
GspRmBoot images are **bindata** — they live in `open-gpu-kernel-modules`
(`g_bindata_kgspGetBinArchive*`), *not* in the userspace `.run` package — and
`v67_payload.bin` comes from **bendy2's** public CMP90HX research (see README
credits), not from any NVIDIA artifact.

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

> **Do not compile `unlock_v2.c` by hand.** All the `-D` flags in
> `src/build.sh` are load-bearing: they decide which phases even exist in the
> binary, and a hand-rolled `gcc` line will silently produce the wrong (or a
> non-release) variant. In particular a build **without** `-DRELEASE_BUILD`
> keeps the interactive `WaitForKey` pause and the SFS/`bootmgfw` chainload
> path — that is the "Windows stuff" you see referenced in the source. Such a
> binary is a dev build: it waits for a keypress and tries to chainload
> `\EFI\Microsoft\Boot\bootmgfw.efi` into RAM, which is *not* the released
> behaviour and can look like a hang. Always build with `src/build.sh`.

```bash
cd src
BLOBS=/path/to/blobs bash build.sh     # or put blobs into src/blobs/
```

Outputs (all built from the same `unlock_v2.c`):

| Binary | Flags | Notes |
|---|---|---|
| `unlock_v3n.efi` | `RELEASE_BUILD MULTI_CARD PCIE_GEN2_REJOIN FULL_NOGEN2` | **Current release (v3.05)** — use this on real hardware. Walks only the 3 FEAT-page PLMs; the XVE/XP3G/OPTB Gen2 masks are compiled out |
| `unlock_v3f.efi` | `…PCIE_GEN2_REJOIN` | v3.02-full: full 37-entry mask table + gen2 link config; slow (~10 min) walk on a cold boot and known Code 43 issue, see KNOWN-ISSUES |
| `unlock_v3.efi` | `RELEASE_BUILD MULTI_CARD` | compute-only — no fire machinery, so no GFX/render unlock |
| `unlock_v2.efi` | dev | Interactive pauses, gen experiments |
| `unlock_v2_test.efi`, `unlock_v3n_test.efi` | +`EFI_AUTOTEST` | QEMU test stand |
| `unlock_v2_wr.efi` | `ENDGAME_WARMRESET` | Plan-B endgame, unused |

Reference checksums of the released binaries (built against our blob set):

```
824fab33873b32d174ebe620fe2a8475  unlock_v3n.efi   (v3.05 as released)
d864d8da8b08fdc472403b44115e55d0  unlock_v3.efi    (v3.05 compute-only)
c708f44ef397dbe74cdb4ab4571ca037  unlock_v3f.efi   (v3.02-full, unchanged from v3.04)
```
(`unlock_v2.efi` `017d0a4871710f1f2fb16c3468a636e9` and `unlock_v2_wr.efi`
`80df38e33040d1e2e363f054c4bc446d` are unchanged from earlier releases.)

Historical checksums, for reference:

```
e27221f5ddd563602423b035b3274f2d  unlock_v3n.efi   (v3.03)
0ccc4357794aa4c83102bef3ec081bf5  unlock_v3n.efi   (v3.04)
511801cb82f8a3bf36c95af7ed39a3d9  unlock_v3.efi    (v3.04 compute-only)
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
python3 -c "print('v3.05 FULL-NOGEN2'.encode('utf-16-le') in open('/mnt/img/EFI/BOOT/BOOTX64.EFI','rb').read())"
umount /mnt/img; fsck.vfat -n "${LOOP}p1"; losetup -d "$LOOP"
```
