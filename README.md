# iOBEWi Rust OTA

Verified boot and over-the-air update building blocks for ESP32: an authenticated, power-cut-aware A/B update chain,
written in Rust, with a portable core (`common/firmware`) and ESP32 adapters (`arch/esp32/firmware`).

This repository was extracted from [`iobewi/rust-mcu-libs`](https://github.com/iobewi/rust-mcu-libs), where the
sub-system was developed. The extraction is a **move only**: no source file, algorithm, flash format, IAP1 proof,
boot or OTA metadata was modified (see [Provenance](#provenance)).

## Status of the qualification

* **Software verified boot profile, ESP32-S3: qualified on hardware** (signature, digest and canonical length
  refusals, authenticated fallback, signed upload, proof publication, activation, confirmation, persistence,
  rollback). Matrix and reports: [`docs/firmware/verified-boot-evidence.md`](docs/firmware/verified-boot-evidence.md).
* **ESP32-C3: compiled and size-gated in CI only. Not qualified on hardware.**
* Not provided: hardware root of trust (Secure Boot V2, eFuses, JTAG, flash encryption), persistent anti-rollback,
  key rotation and revocation, power-loss qualification on hardware.

## Contents

| Path | Crate | Role |
|---|---|---|
| `common/firmware/auth` | `iobewi-firmware-auth` | IAM1 manifest, pinned keys, RSA-PSS 3072 and P-256 profiles |
| `common/firmware/bootauth` | `iobewi-firmware-bootauth` | IAP1 boot proofs, `UnsignedBoot` / `VerifiedBoot`, canonical length |
| `common/firmware/boot` | `iobewi-firmware-boot` | transactional A/B boot decisions, `otadata` v2 |
| `common/firmware/image` | `iobewi-firmware-image` | SHA-256 digest, ESP image validation, canonical size |
| `common/firmware/update` | `iobewi-firmware-update` | artifact streaming and update transaction engine, `ota_meta` |
| `common/firmware/component/*` | `iobewi-workload`, `-abi`, `-image`, `-native` | supervised native component contracts |
| `arch/esp32/firmware/{boot,a,storage,supervisor}` | `iobewi-esp-boot`, `iobewi-esp-firmware-{a,storage,supervisor}` | ESP32 adapters (ROM SHA-256 and RSA-PSS, slots, storage) |
| `examples/firmware/bootloader` | `iobewi-esp-bootloader` | second stage, `verified-boot` feature |
| `examples/firmware/ota-system`, `ota-supervised` | `example-firmware-*` | reference applications and their component |
| `tools/component-pack` | `iobewi-workload-pack` | component packer |
| `docs/firmware` | | design, qualification protocols, campaigns, evidence matrix |

## Dependencies on rust-mcu-libs

The generic libraries (flash, TLS, HTTP, Wi-Fi, configuration, logging, watchdog, console) stay in
`iobewi/rust-mcu-libs` and are **git dependencies pinned by `rev`** in the manifests of this workspace (pinned at
`79ce788a6bda7b1e31211aedce8e05b97ebd37cc`, the `main` of rust-mcu-libs after the OTA sub-system left it; the first
migration used its parent `59f3b83985caf5b1f617da00dd3dfaa6bd988f28`). Two crates of the OTA family,
`iobewi-firmware-layout` and `iobewi-firmware-slots`, **also stay in rust-mcu-libs**: its generic
`iobewi-esp-config-space` depends on `iobewi-firmware-layout` (which depends on `iobewi-firmware-slots`), and
moving them would create a dependency cycle between the two repositories. They are consumed from there like the
other generic crates. Splitting `iobewi-firmware-layout` into a generic part and an OTA part is a future,
separate change.

To move to a newer rust-mcu-libs, change the `rev` of every `git = "https://github.com/iobewi/rust-mcu-libs"`
dependency together (a single revision must be used, otherwise the same crate would be built twice).

## Continuous integration

`.github/workflows/ci.yml` runs the host tests and Clippy of every crate, the ESP32-S3 and ESP32-C3
builds (S3 on the pinned and the latest Xtensa toolchain), the console matrix, the signed profiles, the
verified-boot second-stage size gates, the flash geometry tool and its self-tests. The CI is one workflow with three parallel
families, Host, RISC-V (ESP32-C3) and Xtensa (ESP32-S3), and a fail-closed gate (see [`.github/CI.md`](.github/CI.md)). `Cargo.lock` is not tracked.

## Follow-up issues

Open issues of this repository: [#1](https://github.com/iobewi/rust-ota/issues/1) ESP32-C3 hardware qualification,
[#2](https://github.com/iobewi/rust-ota/issues/2) hardware root of trust on ESP32-S3,
[#3](https://github.com/iobewi/rust-ota/issues/3) panic after confirmation,
[#4](https://github.com/iobewi/rust-ota/issues/4) fallback availability after a refused upload and rejection diagnostics,
[#5](https://github.com/iobewi/rust-ota/issues/5) additional ESP32-S3 qualification,
[#6](https://github.com/iobewi/rust-ota/issues/6) RP2350 and Teensy study.
Anti-rollback, key rotation and power-loss requirements are tracked in
[`iobewi/rust-mcu-libs#92`](https://github.com/iobewi/rust-mcu-libs/issues/92).

## Provenance

| | |
|---|---|
| Source repository | [`iobewi/rust-mcu-libs`](https://github.com/iobewi/rust-mcu-libs) |
| Source commit | `59f3b83985caf5b1f617da00dd3dfaa6bd988f28` (`main`, squash of PR #101) |
| Qualified code | tag `verified-boot-s3-qualified` (rust-mcu-libs commit `9ba953362e52103c488bb298b218843464a6b5b9`, head of PR #105; rewritten as `331c48b211bdcc966f9ba989c9df4bd0ab001882` in this repository, same tag name) |
| Pull requests | [#101](https://github.com/iobewi/rust-mcu-libs/pull/101) (verified boot), [#105](https://github.com/iobewi/rust-mcu-libs/pull/105) (canonical length) |
| Issues | [#91](https://github.com/iobewi/rust-mcu-libs/issues/91), [#104](https://github.com/iobewi/rust-mcu-libs/issues/104) |
| Qualification reports and final audit | comments of the pull requests and issues above; index in [`docs/firmware/verified-boot-evidence.md`](docs/firmware/verified-boot-evidence.md) |
| Hardware | the qualification campaigns remain valid; the hardware backups and artefacts are not part of this repository |

The Git history of the moved files was preserved (`git filter-branch` on the source history, paths unchanged).
Issue and pull request numbers cited in `docs/firmware` before this migration (for example `#91`, `#101`, `#104`,
`#105`) refer to **`iobewi/rust-mcu-libs`**.
