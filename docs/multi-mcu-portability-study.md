# VerifiedBoot portability study: RP2350 and Teensy

Issue #6. Architecture study only; no port, device build or qualification claimed.
Reference baseline fab2506. Existing S3 acquired evidence is unchanged.

## Concrete scope

The first proposed Raspberry Pi adapter targets **RP2350A/B, Arm Cortex-M33**,
with external QSPI flash sized from the board BOM. RP2354 stacked-flash variants
are a separate geometry configuration. Hazard3 RISC-V is a separate execution
profile and is excluded from the proposed hardware-secured profile.

The proposed Teensy adapter targets **Teensy 4.0 and 4.1, NXP i.MX RT1062,
Cortex-M7**, with separate standard/Lockable and silicon/board revision profiles.
MicroMod Teensy is a separate board integration, not assumed interchangeable.
Legacy Teensy 3.x/LC (Kinetis) and Teensy 2.x (AVR) are expressly outside this
study/adapter; a request for those requires naming the board/MCU and a new study.
"Teensy" alone must never be a build target or trust guarantee.

## Raspberry Pi evidence and implications

Primary sources: [RP2350 datasheet](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf)
(chapters 5/10; current download checked 2026-11-02),
[security whitepaper](https://pip-assets.raspberrypi.com/categories/1260-security/documents/RP-009377-WP-1-Understanding%20RP2350_s%20security%20features.pdf),
[chip variants](https://www.raspberrypi.com/documentation/microcontrollers/microcontroller-chips.html),
[flash design](https://pip-assets.raspberrypi.com/categories/1214-rp2350/documents/RP-008280-DS-1-hardware-design-with-rp2350.pdf?disposition=inline).

RP2350A/B have no internal program flash; SRAM is 520 KiB. QSPI flash is board
specific; bootable partitions must fit in the first 16 MiB. SHA-256 acceleration
and 8 KiB OTP exist. ROM secure boot uses SHA-256/ECDSA **secp256k1**, not IAM1's
current ECDSA P-256 curve; secure configuration disables the unsecured RISC-V cores.
TrustZone/OTP protections require a specific provisioning and isolation design.
No portable Rust RSA-PSS ROM API is assumed.

IMAGE_DEF blocks describe execution/architecture and LOAD_MAP regions; UF2 is a
transport container, not the bytes to hash as a flat ESP image. Signed-image
measurement must cover the canonical declared load/metadata ranges and reject
ambiguous, cyclic/out-of-bounds or overlapping layouts according to the ROM format.
OTP boot-key hashes and revocation/version controls are MCU authority, distinct
from application IAM1 pins. Native version advancement must be reconciled with
probation before it is enabled, never assumed equivalent to delayed confirmation.

There is no ESP 32-KiB second-stage limit to transplant. Budget the proposed custom
stage inside its flash partition and available SRAM; prove ROM metadata discovery,
load-map ranges, secure/non-secure attribution, stack and XIP boundaries from the
actual linked image. A 4-KiB IMAGE_DEF discovery window is **not** a 4-KiB stage
size limit. A trusted custom loader verifying a portable manifest is one possible
chain; native ROM-signed images are another. Both need a deliberate signing/format
choice, not automatic reuse of RSA IAP1 layout.

## Teensy evidence and implications

Primary sources: [4.0](https://www.pjrc.com/store/teensy40.html),
[4.1](https://www.pjrc.com/store/teensy41.html),
[code security](https://www.pjrc.com/teensy/td_code_security.html),
[i.MX RT1060 reference manual](https://www.pjrc.com/teensy/IMXRT1060RM_rev2.pdf).

The PJRC security path combines HAB authentication (CMS/RSA-2048, SHA-256) with
BEE AES-128 code encryption and fuse-bound trust. It is not Espressif RSA-PSS.
Lockable-board secure mode and standard-board encryption capability have different
guarantees; ordinary boards must not be advertised as equivalent. Some security
fuse details require NXP restricted documentation, so undocumented fuse programming
is not a viable implementation plan.

Teensy 4.0 has 2 MiB program flash with the top 64 KiB reserved; 4.1 has a larger
board flash configuration that must be read from its own linker/BOM. Both use
RT1062 with 1 MiB RAM; partition ITCM/DTCM/OCRAM and cache/XIP ownership explicitly.
Do not use optional external PSRAM as protected boot memory. HEX/EHEX packaging
and the separate PJRC programming controller are not interchangeable with a flat
ESP app/IAP1 pair. Preserve vendor recovery/reserved regions.

For native HAB, define signed Flash Configuration/IVT/BootData/CSF coverage and
EHEX transformations with vendor tools; for a custom software loader, define a
canonical raw payload plus signed load/entry metadata. No current IAM1 Mcu/ImageFormat
discriminant represents this target, so format extension needs compatibility design
and test vectors before code. There is no identified universal 32-KiB stage limit:
choose a nonoverlapping board partition, retain vendor metadata/recovery, and size
the linked stage/stack separately. HAB RSA is a boot service, not assumed to be a
reentrant runtime SignatureVerifier. A portable SHA/P-256 implementation may be
usable for software OTA independently of native HAB; no hardware ECDSA guarantee.

## Shared core versus adapters

| Reuse unchanged | Required new target-specific integration |
|---|---|
| WriteSession durable-byte hashing and bounded buffering | QSPI/flash erase/program geometry, RAM execution during writes, XIP/cache/multicore exclusion |
| transaction/boot state decisions and confirmation/rollback contracts | Native boot selection, reset reasons, watchdog, secure/non-secure entry/jump and vector validation |
| SignatureVerifier, Sha256Stream, trust-policy roles | RP2350 secp256k1/native ROM profile or explicitly selected software verifier; RT1062 HAB/crypto boundary |
| Target and authenticated digest/version semantics | MCU/image-format identifiers with versioned compatibility plan; canonical format parser and relocation bounds |
| FloorStore/promotion concepts (PR #18) | Protected authority/persistence and probation-compatible monotonic advancement; not an OTP stub |
| Atomic metadata publication contracts | Board-specific erase units, interrupted commit recovery and endurance; do not assume EKV safe after a cut |

Do not copy ESP ROM addresses, BOOT placement, partition table labels, MMU aliases,
IAP1 proof-sector offsets, OTA capacity deductions or eFuse meanings into the new
adapters. A shared trait name does not establish equal hardware security.

## Qualification gates before implementation claims

1. Freeze exact board, MCU stepping, boot ROM revision, flash RDID/geometry, memory
   map, factory state and vendor recovery constraints. The final Teensy board has
   not been chosen by the user; 4.0/4.1 are this study's explicit proposed scope.
2. Build host parsers against official/native signed fixtures: canonical length,
   range/entry rules, signature/hash/key failures, malformed metadata, overlap,
   truncation, appended data and incompatible architecture. Fuzz parsers before
   exposing them to untrusted uploads. No MCU adapter is built in this study.
3. Implement one adapter at a time; host flash models must test every erase/program
   interruption and confirmed-fallback invariant. Build bare-metal no_std and gate
   real stage/stack/flash size from target artifacts; derive budgets from each board.
4. On separately authorized dedicated devices, verify native/software boot paths,
   both-slot OTA/rollback/watchdog, canonical measurement, cold/warm reset and cut
   recovery with independent reads. OTP/fuses/lock transitions need a separate
   concrete approval and sacrificial-board plan; none are authorized here.
5. Claim a hardware root only after demonstrating enforcement/debug protection and
   compromise/recovery behavior on the exact secured profile. Software OTA may be
   qualified separately; no ESP32-S3 result transfers to either family.

Study acceptance: concrete candidate MCU scope, native primitives/formats, stage
budget method, common/adapter boundaries and qualification conditions are specified.
Proposed disposition: #6 can close **after this study PR is accepted/merged**, as
an architecture-study issue only. Implementation/adapters and final board selection
remain future work; no supported-target claim follows from study closure.
