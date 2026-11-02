# ESP32-C3 audit and deferred qualification

Issue #1. Review baseline: main fab2506 (PR #10). No C3 device access. The S3
qualification (`verified-boot-s3-qualified`, historical rust-mcu-libs #101/#105,
verified-boot-evidence.md) remains acquired and is not transferred to C3.

## Static audit

The existing ROM analysis already covers C3 rev0, rev101 and rev3 ELF images:
see verified-boot-sha.md for artifact hashes, disassembly observations and limits.
No ROM reverse engineering or model reimplementation was repeated in this campaign.
Official ABI references pinned to ESP-IDF v5.4.1:

- [sha.h](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_rom/esp32c3/include/esp32c3/rom/sha.h)
- [rsa_pss.h](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_rom/esp32c3/include/esp32c3/rom/rsa_pss.h)
- [ROM symbols](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_rom/esp32c3/ld/esp32c3.rom.ld)

| Binding | Audit result |
|---|---|
| SHA context | repr(C), 216 bytes / alignment 4; offsets 0,1,4,8,72,200 match the C declaration and existing disassembly evidence; compile-time assertions retained |
| SHA kind and calls | SHA2_256=2; enable/disable no arguments, init context+kind, update context+input+u32 length+bool, finish context+output |
| ROM symbols used by esp-rom-sys 0.1.5 | enable 0x40000644, disable 0x40000648, init 0x40000650, update 0x4000065c, finish 0x40000660, RSA verify 0x40000750; cross-checked with the downloaded dependency linker map |
| RSA buffers | key 776 bytes (384-byte modulus, u32 exponent, 384-byte Montgomery value, u32 mdash), signature 384, digest/output 32, all aligned by adapter |
| Return convention | C RSA returns bool; adapter declares a word and tests its low byte, matching existing ROM-model/disassembly convention. A device ABI check remains required; no speculative change to the qualified shared binding |
| Peripheral ownership | SHA hash completed/dropped before RSA, sole boot phase, no interleaved SHA user. Host model tests exercise ownership and canary bounds |
| Build feature selection | esp32c3 + rom-verify, default ROM SHA; sha-hal/sha-soft mutually exclusive. No runtime S3 address selection |
| RAM/flash | C3 linker IRAM 0x403cb000..0x403d4000 (36 KiB), DRAM 0x3fcd4000..0x3fcdc000 (32 KiB), aliases disjoint and ROM data excluded. Historical table at 0x8000 limits boot image to 32 KiB |

The existing ci_mcu.py --chip esp32c3 builds/links unsigned, signed, signed-rsa,
verified boot, diagnostic and alternate SHA profiles, with image/ELF geometry and
size gates. Historical measurements are in flash-geometry.md (C3 verified ROM
image 27,392 bytes there); issue #1's 27,504-byte number is from another build.
Sizes vary with toolchain/features: only a current exact-head CI measurement is
current evidence. Flash headroom is not stack high-water evidence.

Host ROM tests already cover NIST vectors, million-byte/unaligned/relocated context,
all lengths around block boundaries, 216-byte reach and guards, abandoned hash
cleanup and the old 80-byte regression. These tests model the ABI; they do not
execute a C3 ROM or establish watchdog/stack timing. No demonstrated static defect
requires changing the shared adapter in this audit.

## Deferred C3 protocol

Record exact board/SoC revision, flash RDID/capacity, ROM banner, tooling versions,
firmware SHAs, feature sets, image hashes and measured sizes. Independently back up
full flash and named regions with digests before any authorized future campaign.
Never change eFuses. Use a dedicated board and retain an independently verified ROM
recovery path. Stop if revision/geometry differs from the prepared assumptions.

1. Run a bounded diagnostic SHA/RSA firmware first: NIST, boundary/chunk/unaligned
   vectors; valid RSA, wrong key/signature/digest, salt/encoding failures; guard
   buffers and verified-digest output; record return values and reset cause.
2. Boot authentic slot0 then slot1 under verified boot. Corrupt signature, digest,
   canonical size and proof commit independently. Verify refusal and authentic
   fallback; when neither usable, HALT without metadata writes. Read flash before
   and after every negative case.
3. Signed OTA admit/upload/readback/proof/publication; incompatible/unsigned/corrupt
   candidate refused. Activation absent/foreign proof refused before boot intent.
4. Activate → PendingVerify → confirm → reset with durable identity; interrupt
   confirmation, verify reconciliation. Trigger self-check rejection and watchdog
   reset; verify rollback in both slot directions. Record stack/watchdog bounds.
5. Alternate SHA profiles each need their own runtime vectors; a successful default
   profile does not qualify them. Cold/deep-sleep/reset variants remain explicit.
6. Restore exact initial backups and verify their digests/regions independently.
   Add device evidence and its limits to verified-boot-evidence.md only after it
   exists. #1 remains open; compile/link results never substitute for this report.
