# Windows CMP 90HX compute-unlock — процедура повторного патчинга nvlddmkm.sys

Сессии с 2026-08-18. Цель: перенести Linux rejoin14/15 (V67) на Windows-драйвер
610.74. Этот документ — самодостаточный рецепт: при обновлении драйвера
повторить шаги ниже, не переделывая RE с нуля.

## 1. Итоговая модель (что доказано на 610.74)

**Карта функций (RVA, image base 0x140000000, сток 610.74):**

| RVA | Роль |
|-----|------|
| 0x125020 | read-helper `(rcx=[pGpu+0x4358], edx=0, r8d=0, r9d=regaddr, [rsp+0x20]=flags) → eax` |
| 0x1258f0 | write-helper (те же аргументы, [rsp+0x20]=value) |
| 0x260190 | memdescGetPhysAddr(memdesc, 1, 0) → rax=phys |
| 0x26a680 | memdescByIndex(bootDesc, idx): массив записей 16Б {index u32 @+0, pad, memdesc u64 @+8}, count=[0] |
| 0x26a6e0 | memdescGetSize(memdesc) → eax |
| 0x26a860 | memdescCopyTo(memdesc, dst, size) |
| 0x25e110 | memdescCreate(&slot, pGpu, size, r9=0, [rsp+0x20]=1,[0x28]=1,[0x30]=0,[0x38]=attr) |
| 0x25d840 | memdescInit(memdesc); перед ним обязательно `[memdesc+0x9c]=0x28` |
| 0x260f50 | memdescMap(memdesc,0,size,1, [0x20]=3, [0x28]=&va, [0x30]=&va2) |
| 0x262580 | memdescFlush(memdesc, 1, va, va2) |
| 0x25f410 | memdescDestroy(memdesc) |
| 0x974440 | populateBootArgs(pGpu, pKernelGsp, [pKernelGsp+0x200], 0x35c, 0x14, 0, 0) → вызывает 0x974530→fill_bootargs |
| 0xb761d0 | fill_bootargs: memdesc 0x23 копируется в sysmem-буфер, phys → **[bootArgs+4]** |
| 0xb74240 | booter_load(pGpu, pKernelGsp): команды 0x554/0x57c/0x596, статусы 0x65/0x55, PGSP_MAILBOX 0x110804 |
| 0xb75170 | kgspBootstrap: GSP_init(0xb75340) → GFW wait `mov rax,[pGpu+0x4c0]; call guard` @0xb751da → call 0x974440 @**0xb75210** → booter_load call @**0xb752c9** → [pKernelGsp+0x1d9]=1 |
| 0xb74e20 | возвращает [pGpu+0x2198] (BootDescriptor) |
| 0x5fcd60 | slot-функция проверки vendor/device через PCI config (не для нас, но доказывает: [pGpu+0x230] = PCI config read fn) |

**Структуры:**
- pGpu (первый аргумент всех GSP-функций):
  - +0x230 — указатель на PCI config read `(pGpu, edx=offset, r8=&out32) → статус`; out32 = {device<<16|vendor} @0, {subdevice<<16|subvendor} @0x100
  - +0x4358 — BAR0-база для read/write-helper
  - +0x4c0/+0x4c8/+0x4d0 — слоты-функции (GFW wait = +0x4c0)
  - +0x2198 — BootDescriptor (массив memdesc, см. 0x26a680)
  - +0x200 (это pKernelGsp) — BootArgs (0x35c байт), `+4 = sysmemAddrOfSignature`
  - флаги pKernelGsp: 0x1d9 booted, 0x1da/0x1dd retry-режимы (при !=0 bootstrap пропускает booter_load)
- memdesc 0x23 в BootDescriptor = pSignatureMemdesc (аналог Linux pKernelGsp->pSignatureMemdesc)

**Диспетчеризация**: kgspBootstrap вызывается через halObj-слоты (FUN_1417f3800
пишет +0x150=bootstrap, +0x140=GSP_init); прямых статических вызовов нет —
патчим ВНУТРИ bootstrap, вызывающий не важен.

## 2. Дизайн патча (портированный Linux rejoin5 two-stage booter)

Новая секция `.cmp90` (RVA 0x7370000, exec|read|write) с функциями:

- **cmp90_swap_wrap** — вызывается ВМЕСТО `call 0x974440` @0xb75210.
  Сохраняет аргументы, вызывает cmp90_swap(pGpu, pKernelGsp), затем оригинальный
  0x974440 с аргументами (rcx=pGpu, rdx=pKernelGsp, r8=[pKernelGsp+0x200],
  r9d=0x35c, [rsp+0x20]=0x14, [rsp+0x28]=0, [rsp+0x30]=0).
- **cmp90_swap (F1)** — проверки (IsCmp90Hx через [pGpu+0x230] + SS0!=0x88888888),
  создаёт V67-memdesc 0xfa00 (create→init→map→fill→flush), подменяет
  bootDesc[0x23] = новый, сохраняет старый в g_old (статики секции).
- **cmp90_booter_wrap** — вызывается ВМЕСТО `call 0xb74240` @0xb752c9:
  call 0xb74240 (#1) → cmp90_handoff → если вернул 1 → call 0xb74240 (#2) → вернуть статус #2.
- **cmp90_handoff (F2)** — если g_new!=NULL и PLM(0x823804)==0xffffffff:
  WR SS1(0x823820)=8, SS0(0x82381c)=0x88888888 → restore bootDesc[0x23]=g_old →
  [bootArgs+4]=phys(g_old) → destroy g_new → очистить статики → вернуть 1.
- **cmp90_iscmp** — PCI config: vendor==0x10de && device==0x220d && subdevice==0x1555.
- **cmp90_read_ss0** — read 0x82381c.
- **cmp90_fillv67** — fill 0xfa00 байт dword 0x19c + цепочка:
  0x1100=7, 0xf948=0xffffffff, 0xf950=0xd44, 0xf960=0x823804, 0xf968=0x1fce,
  0xf974=0, 0xf97c=0x1101, 0xf980=0x84c8, 0xf984=0x8e18, 0xf98c=0x84c8,
  0xf990=0, 0xf998=0x1fce, 0xf9a4=0xffbc, 0xf9ac=0x5789, 0xf9bc=0xd44,
  0xf9cc=3, 0xf9d4=0x1fce, 0xf9e8=0xd52, 0xf9ec=0x81ee.

Порядок исполнения после патча:
GFW wait → F1 (V67 подмена) → populate bootArgs (sysmem 0xfa00, +4=phys) →
booter_load#1 (V67) → PLM open (0xffffffff) → F2: SS1/SS0 write → restore сигнатуры
→ booter_load#2 (сток) → GSP-RM грузится → карта разблокирована. БЕЗ FLR (Linux rejoin5).

## 3. Точки патча (сток 610.74)

- 0xb75210: `E8 <rel32>` call 0x974440 → call cmp90_swap_wrap (5 байт E8).
- 0xb752c9: `E8 <rel32>` call 0xb74240 → call cmp90_booter_wrap (5 байт E8).
- rel32 = target_VA - (ins_VA + 5).

## 4. Сборка (tools/build_patch.py)

1. Сток: `tools/stock61074/Display.Driver/nvlddmkm.sys` (120,313,064 байт).
2. Код ассемблируется keystone 0.9.2 (`pip install keystone-engine`), origin 0x140737000.
   - **ВАЖНО (баг keystone)**: виснет на forward-вызовах в большом коде → порядок функций:
     определения (swap, handoff, iscmp, readss0, fillv67) ПЕРЕД wrappers (swap_wrap, booter_wrap).
   - keystone НЕ поддерживает `lea reg,[rip+label]` — писать `lea reg,[rip+0]`
     (48 8D 05/0D + 00000000) и патчить disp после сборки; statics g_old/g_new (16 байт)
     после кода (offset = align(len(code),8)); всего 8 lea-плейсхолдеров.
   - Вызовы функций драйвера — абсолютные `call 0x140xxxxxx` (keystone сам считает rel32).
3. PE-правки (все — в bytearray, писать файл ВРУЧНУЮ, НЕ через pefile.write!):
   - e_lfanew=0x108 (из 0x3C), optional header @0x120, opt_size=0x178 (NVIDIA-специфика).
   - Таблица секций @ e_lfanew+4+20+opt_size = **0x210**; свободное место для новой
     записи — 0x710..0x738 (SizeOfHeaders 0x800). Запись .cmp90: VA=0x7370000 (после
     .reloc VA-end 0x736fc8c → align 0x1000), raw=0x72b8600 (после .reloc raw-end),
     Characteristics 0xE0000020, VS=len(payload), RAW=align(0x200).
   - **DataDirectory начинается с opt+0x70** (не 0x78!): Security = DD[4] @
     opt+0x70+4*8 = **0x1B0** — обнулить 8 байт (старый NV-сертификат);
     DD[5]=BaseReloc @0x1B8 НЕ трогать!
   - Вставка raw: `data[0x72b8600:0x72b8600] = payload` — сдвигает стоковый
     сертификат-overlay в конец (НЕ обрезать файл иначе signtool: badexeformat).
   - SizeOfImage = align(0x7370000 + VS, 0x1000) = 0x7371000; NumberOfSections=33;
     CheckSum=0 перед расчётом; расчёт стандартный (sum words + len, fold 16bit).
4. Патчи bootstrap (5 байт E8 rel32): 0xb75210 → .cmp90+0 (swap_wrap),
   0xb752c9 → .cmp90+0x461 (booter_wrap). rel = target - (ins+5).

## 5. Подпись (tools/make_certs.ps1 + tools/fix_checksum.py)

Secure Boot ВЫКЛЮЧЕН (проверено). Схема: свой root + code-signing cert.
- `C:\Windows\signtool.exe` — ПОДДЕЛЬНЫЙ (Mozilla/Unix) — использовать настоящий:
  `C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe`.
- Создание cert (НЕ требует админ): New-SelfSignedCertificate в `Cert:\CurrentUser\My`:
  root (KeyUsage CertSign,CRLSign,DigitalSignature, TextExtension ca=1) + code
  (KeyUsage DigitalSignature, EKU 2.5.29.37={text}1.3.6.1.5.5.7.3.3, -Signer root).
- Export-PfxCertificate (code, с паролем) + Export-Certificate (root .cer).
- Подпись: `signtool sign /f code.pfx /p PASS /sha1 <code-thumbprint> /fd sha256 file`
  (обязателен /sha1 — pfx содержит и root, и code; иначе "Multiple certificates").
- Установка root в LocalMachine\Root + TrustedPublisher — требует админ:
  `powershell -File tools\install_elevated.ps1` (запускать ОТ АДМИНА).
- ПОСЛЕ подписи пересчитать PE checksum (`tools\fix_checksum.py`) — Authenticode
  исключает CheckSum из хеша, подпись не ломается.
- Проверка: Get-AuthenticodeSignature → Valid (после установки root в LocalMachine).

## 6. Установка (tools/install_elevated.ps1, от админа)

1. Import root.cer → LocalMachine\Root + TrustedPublisher.
2. Backup nvlddmkm.sys → nvlddmkm.sys.stock; заменить на nvlddmkm.cmp90.sys.
3. `setup.exe -noeula -nosplash -n -enableTelemetry:false` (как Y:\nvdisppatch\472.12\Install.bat).
4. Перезагрузка, затем бенчмарк.

## 6. Верификация

```
G:\llama\llama-bench.exe -m "G:\LLM\.lmstudio\models\lmstudio-community\gemma-4-12B-it-QAT-GGUF\gemma-4-12B-it-QAT-Q4_0.gguf" -p 512 -n 16 -ngl 99 -dev CUDA1 -r 3
```
База затроттлена: pp512 ≈ 223 t/s. Цель после патча: ~1770 t/s.
Регистры для проверки: PLM 0x823804 → 0xffffffff, SS0 0x82381c → 0x88888888,
SS1 0x823820 → 8 (nvidia-smi/NVAPI или свой ридер).

## 7. Открытые вопросы / риски

- **Размер сигнатуры**: [bootArgs+4] обновляется при restore, но поле
  "sizeOfSignature" в bootArgs не найдено (fill_bootargs его не пишет). Если
  booter читает размер из отдельного поля — надо найти и обновлять его.
  Проверка: если после патча PLM не открывается — поле размера не 0xfa00.
- keystone-зависание (п.4) — главный блокер сборки на текущий момент.
- Статики g_old/g_new — один слот (одна CMP-карта); для 2+ CMP нужен массив по
  gpuInstance (как Linux rejoin14: s_cmp90Pc*ByGpu[8]).

## 8. Инструменты

- PyGhidra (обход сломанной OSGi-компиляции Java-скриптов!):
  `set JAVA_HOME=W:\cmpunlocker-continue\tools\jdk21\jdk-21.0.12+8 && python tools/py_*.py`
  install_dir передавать явно: `pyghidra.start(install_dir=r"...ghidra_12.1.2_PUBLIC")`;
  открытие проекта: `pyghidra.open_program(None, project, "nvlddmkm", analyze=False,
  program_name="nvlddmkm.sys", nested_project_location=False)`; адреса в
  `flat.toAddr("0x%x" % (0x140000000+rva))`.
- Python-скрипты tools/: dump_candidates, disasm_bootstrap_booter, disasm_fillboot,
  dump_dispatch_tables, find_holes, build_patch, test_ks*.
- Ghidra 12.1.2 + JDK21, GHIDRA_HEADLESS_MAXMEM=10G, проект tools/ghidra_project.
