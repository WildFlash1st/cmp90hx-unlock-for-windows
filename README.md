# 🎮 CMP 90HX Unlock for Windows

🇬🇧 English | [🇷🇺 Русский](README.ru.md)

Unlock the full computing and graphics power of the **NVIDIA CMP 90HX** (GA102, 10 GB, PCI ID `10de:220d`) on any system with Windows — using a simple USB stick, an EFI bootloader, and **no reboots**.

The unlock runs **before any OS boots**, so Windows simply starts with the card already at full power.

> ⚠️ **Honest expectations:** this is a mining card, and it is *not* a gaming
> GPU replacement — no display outputs, PCIe Gen1 ×16 in the current release,
> and gaming requires a community-patched driver (see below). Compute/AI is
> what it excels at after the unlock. Details in [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

## What is the CMP 90HX?

The CMP 90HX is a GA102 die sold by NVIDIA as a **"mining-only" card**. NVIDIA crippled it in firmware: CUDA compute and graphics features are disabled, and the card runs at a fraction of its real performance. The typical locked card delivers ~230 t/s on llama-bench; an unlocked one delivers **~3700 t/s** (16× more).

This project re-enables the full die using an EFI application that runs from the bootable USB, before the OS loads. **It is now open source** — see [`src/`](src/) and [BUILDING.md](BUILDING.md).

## How the unlock works

1. **Preload.** The Windows boot manager (`bootmgfw.efi`) is read into RAM using raw block I/O and a built-in FAT32 parser. (No UEFI SimpleFileSystem is used — it hangs on some AMI boards.)
2. **Unlock.** A custom EFI application drives the GPU's SEC2 (Falcon) microcontroller through its secure boot sequence:
   - opens the memory-write-protection registers (WPR2),
   - loads a signed "canary" payload (V67) into the SEC2 booter,
   - opens the GPU's protected mode (PLM),
   - sets the compute selectors (SS0/SS1) and render masks.
3. **Reset.** A Function Level Reset (FLR) clears the latched protection registers while the compute selectors survive.
4. **Boot.** The app returns into the firmware without a POST, and Windows loads with the card already unlocked. **The system is never rebooted** — a POST would reset the GPU and drop the unlock.

The exploit itself: the NVIDIA-signed SEC2 booter has a stack-canary bug (Jon Pry, *"A Canary in the Crypto Mine"*). When it validates our oversized 64 KB "signature", execution runs into a ROP chain that performs arbitrary privileged register writes — including PLM open.

## What happens after you pick the USB in the boot menu (F12)

| Scenario | Result |
|---|---|
| **Windows boots** | The unlock ran, and Windows loads with the card at full power. ✅ |
| **Back to the boot menu** | If the chainload path can't proceed, the app returns to the firmware **without rebooting**, so you can pick any other boot device. The unlock state persists until the next full reboot (POST). |

## Test results

Verified on two real systems.

### llama-bench (CUDA, llama-2-7B Q4_0, `-ngl 99`)
```
| model        | size     | params | backend | ngl | test  | t/s              |
| llama 7B Q4_0| 3.56 GiB | 6.74 B | CUDA    | 99  | pp512 | 3705.40 ± 410.21 |
| llama 7B Q4_0| 3.56 GiB | 6.74 B | CUDA    | 99  | tg16  | 139.20 ± 2.56    |
```
Device 0: NVIDIA CMP 90HX, compute capability 8.6, VRAM: **10239 MiB** (full 10 GB).

### Gaming (with caveats!)

**Resident Evil Requiem** was tested and is playable when streamed via Moonlight (screenshot and HWiNFO log in [`tests/`](tests/)):

| Metric | Value |
|---|---|
| FPS | **31 – 63**, average **48.7** |
| GPU core clock | **1875 MHz** (full boost) |
| VRAM in use | up to **6.9 GB** of 10 GB |
| GPU power draw | up to **145 W** |
| GPU temperature | 44 – 57 °C |

That session used soldered capacitors (hardware mod) and PCIe Gen 1 ×16. Treat gaming as a bonus: no display outputs on the card, limited link bandwidth, and a patched driver is mandatory.

### Modified driver for rendering/gaming

The stock NVIDIA driver still blocks CMP cards from rendering (the restriction lives in the driver too, not only the firmware). To run graphics after the unlock, install a patched NVIDIA driver:

👉 **[https://github.com/dartraiden/NVIDIA-patcher](https://github.com/dartraiden/NVIDIA-patcher)**

## Requirements

- NVIDIA CMP 90HX (PCI ID `10de:220d`)
- UEFI motherboard with a boot menu (F12)
- Windows installed on a GPT disk with an EFI System Partition
- **Secure Boot disabled** (the loader is unsigned)
- A USB stick (≥ 256 MB)

## Installation

1. Download the latest release image from the [Releases](https://github.com/WildFlash1st/cmp90hx-unlock-for-windows/releases) page.
2. Write the image to the USB stick with [Balena Etcher](https://etcher.balena.io/), [Rufus](https://rufus.ie/) (DD mode), or `dd`:
   ```bash
   dd if=<image>.img of=/dev/sdX bs=4M status=progress
   ```
   ⚠️ Double-check the device name — this wipes the target stick!
3. Verify the md5 against the one published with the release.
4. Reboot, press **F12** (or your board's boot-menu key), select the USB stick.
5. The unlock runs automatically — Windows loads at full power. No keys to press, nothing to configure.
6. *(For rendering/games only)* Install the patched NVIDIA driver from [NVIDIA-patcher](https://github.com/dartraiden/NVIDIA-patcher).

### Re-applying after a reboot

The unlock is **volatile**: a full reboot (POST) resets the GPU. To unlock again, simply boot from the USB stick again and let it chainload Windows. That's it.

## Building from source

```bash
git clone https://github.com/WildFlash1st/cmp90hx-unlock-for-windows
cd cmp90hx-unlock-for-windows/src
BLOBS=/path/to/blobs bash build.sh
```

See **[BUILDING.md](BUILDING.md)** for prerequisites, blob provenance and the USB-image recipe. Known limitations and unsolved problems live in **[KNOWN-ISSUES.md](KNOWN-ISSUES.md)**.

## Repository layout

- `src/unlock_v2.c` — the entire EFI application (all build variants come from it)
- `src/build.sh` — build script (gnu-efi); `src/tools/` — firmware extraction helpers
- `docs/` — platform gotchas, register notes, Code 43 diagnostic report, blob patching procedure
- `tests/` — proof artifacts: game screenshot, HWiNFO log, llama-bench output
- Release images are attached to the [Releases](https://github.com/WildFlash1st/cmp90hx-unlock-for-windows/releases) page

## Credits

This unlock builds on years of public research and tooling. Special thanks to:

- **[bendy2](https://github.com/bendy2/cmp90hx)** — the V67 exploit and the direct-compute patch for driver `580.159.03` — *the key that opened PLM*
- **Jon Pry (Zenodo)** — *"A Canary in the Crypto Mine: Defeating Stack Protection in a GPU Secure Coprocessor"* ([DOI: 10.5281/zenodo.20916112](https://zenodo.org/records/20916112)) — the debug-booter overflow disclosure
- **[cmpunlocker](https://github.com/jdowning100/cmpunlocker)** — the rejoin16 PLM/render-mask method and Gen2 research this project ports
- **d3dx9** — the Python Falcon emulator & ROP chain

## Donations

This project took many nights of reverse engineering. If it helped you, consider supporting further development:

- **TON (Gram):** `UQCuMe07ZsrRpo6q5UdXw4y-AANG2nN8QJGpM8IZkf9M78yH`
- **Litecoin:** `LTC1QTA33QANK4L6JLDVRCR9WP4C8MT555V3FA0RX5M`

Thank you! 🙏

## Disclaimer

This project is for **educational and research purposes**. It modifies GPU behavior, may void warranties, and interacts with signed firmware in ways NVIDIA did not intend. Use at your own risk. The authors are not responsible for any damage, instability, or loss caused by using this software.
