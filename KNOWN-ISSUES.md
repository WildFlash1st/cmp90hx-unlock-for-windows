# Known issues & unsolved problems

An honest list of what does **not** work or remains unverified, as of the
v3.05 release (2026-09-30). See also `docs/GOTCHAS.md` (platform quirks
digest) and `docs/DIAG-REPORT-2026-08-25-CODE43.md` (the Code 43 root cause).

## Fundamental

1. **The unlock is volatile.** Any full reboot (POST re-runs VBIOS) re-locks
   the card. You must boot from the USB stick every cold start. No persistent
   mechanism was found — the masks survive FLR but not POST by design.

2. **PCIe stays at Gen1 x16 in the current release.** The card is silicon-
   clamped to 5 GT/s max, and raising the link requires a pre-OS gen2 config
   phase (`PCIE_GEN2_REJOIN` without `FULL_NOGEN2`, i.e. the v3.02-full
   build) that is currently **excluded** because of issue 3. Measured cost:
   ~3.3 GB/s host↔GPU transfer instead of ~6.6 GB/s at Gen2 x16.

3. **Code 43 regression history of v3.02-full.** Its fire-path could hand
   Windows a GPU with latched WPR2 + live SEC2 ROP spinner → GSP-RM fails to
   start → bugcheck 0x1B0/C000009A → Code 43. Root-caused and fixed in
   v3.03 (tail cleanup: kill SEC2, final FLR, no MMIO after FLR, no NVRAM
   access). The gen2 domain stays disabled until it is re-proven separately.

4. **The v3.03/v3.04 NOGEN2 fire walk crossed the whole 37-entry mask table
   even though it configures no PCIe link** (issue #5). Each entry = one FLR
   mini-cycle (~15 s); on a cold boot with every mask locked that was ~10
   minutes, and two independent boards **rebooted mid-walk** (Kaby Lake at
   36/37, Ryzen at 24/37). v3.05 walks only the three FEAT-page PLMs the
   render path actually needs (0x823804 / 0x823800 / 0x823b04) and drops the
   34 XVE/XP3G/OPTB/LINK_CAP Gen2 masks, so a cold unlock is a couple of
   mini-cycles (~1 min). The full table is still compiled into `unlock_v3f.efi`
   (v3.02-full), the only build that runs the gen2 link config.

## Constraints

5. **Secure Boot must be disabled** — the loader is unsigned. There are no
   plans to sign it (Microsoft would not sign this anyway).

6. **Gaming is not what this card is for.** The CMP 90HX has no display
   outputs, runs PCIe Gen1 x16 here, and rendering additionally requires a
   community-patched NVIDIA driver ([dartraiden/NVIDIA-patcher](https://github.com/dartraiden/NVIDIA-patcher)).
   It works (see README test results) but treat it as a bonus, not the use
   case. Compute/AI is the target.

7. **One card per boot iteration in multi-card systems.** `MULTI_CARD`
   unlocks cards sequentially using NVRAM iteration + return-to-firmware;
   all cards end up unlocked without rebooting, but it takes one pass each.
   Note: in v3.03 the fire path (mask table) did not advance the card index,
   so on systems that enter fire mode the cycle froze after the first fire
   card — remaining cards stayed locked. Fixed in v3.04 (the fire path now
   advances the index, and a cold boot restarts the cycle at card 0).

## Unsolved / workaround-in-place

8. **SimpleFileSystem hangs on AMI F37d (X570 GAMING X).** Any SFS call from
   a loaded application can hang the firmware. Worked around with our own
   FAT32-over-BlockIo parser and a "return to firmware" exit instead of
   chainloading. Never root-caused inside AMI.

9. **NVRAM writes hang the platform once the GPU is in post-unlock state**
   (SMM touches the GPU). Exit-time `SetVariable`/BootNext had to be removed
   (lesson v2.99o). This is why the app simply returns into BDS.

10. **Mask-table stragglers.** Some protected registers only take their
    exact `0xFFFFFFFF` value on a second/third multipass attempt, the OPTB
    block (`0x8200d0..f4`) hard-hangs guests when written (skipped, matching
    upstream cmpunlocker findings), and the `0x8E1DC`/XVE_D* family reads
    back RO patterns regardless — cosmetic, functionally irrelevant.

11. **A live GSP guards the PCIe link registers** on the QEMU stand (writes
    to TLS/LNKCTL2 are discarded after the OS driver starts GSP). Pre-OS
    configuration avoids this on real hardware; post-OS Gen2 recovery from a
    fully cold state remains out of scope.

12. **Host-side quirk:** `nvidia-persistenced` does not work with driver 610
    on this card ("Failed to query NVIDIA devices"); use legacy persistence
    mode (`nvidia-smi -pm 1`) instead.

## Scope

13. Only PCI ID `10de:220d` (CMP 90HX / GA102) is supported. Other CMP SKUs
    (90HXA, 170HX…) share ancestry but were not tested; register offsets may
    differ.
