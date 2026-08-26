#!/bin/bash
# build.sh — build all CMP90HX unlock EFI variants from unlock_v2.c (gnu-efi)
#
# Usage:
#   bash build.sh                 # expects blobs in ./blobs
#   BLOBS=/path/to/blobs bash build.sh
#
# The resulting binaries are byte-identical to the released ones when built
# against the same blobs (release v3.03: unlock_v3n.efi md5 e27221f5ddd56360…).
set -e

WORK="$(cd "$(dirname "$0")" && pwd)"
cd "$WORK"
BLOBS="${BLOBS:-$WORK/blobs}"

echo "=== CMP90HX unlock EFI build ==="

# ---- required firmware/payload blobs (NOT in git — see BUILDING.md) ----
for f in \
    v67_payload.bin \
    booter_ucode_dbg_patched.bin \
    booter_ucode_prod_patched.bin \
    gsp_rm_boot_dbg.bin \
    fwsec_ga102.bin fwsec_ga102_sig.bin \
    sec2_ucode_vbios_49_patched.bin sec2_ucode_vbios_89_patched.bin
do
    [ -f "$BLOBS/$f" ] || { echo "ERROR: $BLOBS/$f not found — see BUILDING.md"; exit 1; }
done
# objcopy encodes the input FILE PATH into generated symbol names, so blobs
# must be embedded under their bare names — copy them next to the script.
cp -f "$BLOBS"/*.bin .

EFI_INC=/usr/include/efi
EFI_LIB=/usr/lib

# objcopy embeds a blob as an object file; auto-generated symbols are named
# after the input FILE NAME (path included!), e.g. foo/bar.bin becomes
# _binary_foo_bar_bin_start. Embed under the BARE name and derive the symbol
# stem mechanically, then VERIFY the target symbol actually appeared —
# with -shared a silent mismatch would leave the reference unresolved and
# produce a broken .efi instead of a link error.
embed() { # embed <bare-file-name-in-cwd> <target-sym>
    local f="$1" tgt="$2"
    local base="${f//./_}"   # v67_payload.bin -> _binary_v67_payload_bin_*
    objcopy --input-target binary --output-target elf64-x86-64 \
        --binary-architecture i386:x86-64 \
        --redefine-sym "_binary_${base}_start=${tgt}" \
        --redefine-sym "_binary_${base}_end=${tgt}_end" \
        --redefine-sym "_binary_${base}_size=${tgt}_size" \
        "$f" "${tgt}.o"
    nm "${tgt}.o" | grep -q " ${tgt}$" || {
        echo "ERROR: symbol $tgt missing in ${tgt}.o"; exit 1;
    }
}
embed "v67_payload.bin"                  v67_payload_bin
embed "booter_ucode_dbg_patched.bin"     booter_ucode_dbg
embed "booter_ucode_prod_patched.bin"    booter_ucode_prod
embed "gsp_rm_boot_dbg.bin"              gsp_rm_boot_dbg
embed "fwsec_ga102.bin"                  fwsec_ga102_bin
embed "fwsec_ga102_sig.bin"              fwsec_ga102_sig
embed "sec2_ucode_vbios_49_patched.bin"  sec2_ucode_vbios_49
embed "sec2_ucode_vbios_89_patched.bin"  sec2_ucode_vbios_89
OBJECTS="v67_payload_bin.o booter_ucode_dbg.o booter_ucode_prod.o \
gsp_rm_boot_dbg.o fwsec_ga102_bin.o fwsec_ga102_sig.o \
sec2_ucode_vbios_49.o sec2_ucode_vbios_89.o"

# build_one <output-base> <extra -D flags...>
# Flags are load-bearing: they decide which phases exist in the binary.
build_one() {
    local out="$1"; shift
    gcc -c -fno-stack-protector -fpic -fshort-wchar -mno-red-zone -O2 \
        -I "$EFI_INC" -I "$EFI_INC/x86_64" \
        -DEFI_FUNCTION_WRAPPER "$@" \
        -o "$out.o" unlock_v2.c
    ld -shared -Bsymbolic -L "$EFI_LIB" -T "$EFI_LIB/elf_x86_64_efi.lds" \
        "$EFI_LIB/crt0-efi-x86_64.o" \
        "$out.o" $OBJECTS \
        -lgnuefi -lefi -o "$out.so"
    objcopy -j .text -j .sdata -j .data -j .dynamic -j .dynsym -j .rel* \
        -j .rela* -j .reloc --target=efi-app-x86_64 \
        "$out.so" "$out.efi"
    echo "[*] Built: $out.efi ($(stat -c%s "$out.efi") bytes)"
}

# dev branch: interactive pauses, gen experiments, full fire machinery
build_one unlock_v2      -DPCIE_GEN_EXPERIMENT -DMULTI_CARD -DPCIE_GEN2_REJOIN

# QEMU test-stand builds (auto-advance, extra dumps)
build_one unlock_v2_test      -DEFI_AUTOTEST -DPCIE_GEN_EXPERIMENT \
                              -DMULTI_CARD -DPCIE_GEN2_REJOIN
build_one unlock_v3n_test     -DEFI_AUTOTEST -DPCIE_GEN_EXPERIMENT \
                              -DMULTI_CARD -DPCIE_GEN2_REJOIN -DFULL_NOGEN2

# plan-B endgame (BootNext + warm reset) — not used in the field
build_one unlock_v2_wr        -DEFI_AUTOTEST -DENDGAME_WARMRESET

# releases
build_one unlock_v3           -DRELEASE_BUILD -DMULTI_CARD
build_one unlock_v3f          -DRELEASE_BUILD -DMULTI_CARD -DPCIE_GEN2_REJOIN
build_one unlock_v3n          -DRELEASE_BUILD -DMULTI_CARD -DPCIE_GEN2_REJOIN \
                              -DFULL_NOGEN2

echo
echo "Deploy to USB (FAT32, EFI/BOOT/BOOTX64.EFI) + gsp_ga10x.bin from the"
echo "NVIDIA 610.43.03 package next to it. For real hardware use"
echo "unlock_v3n.efi (v3.03). See BUILDING.md."
