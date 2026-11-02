# CI

One workflow, `.github/workflows/ci.yml`, three architecture families that run **in parallel**, then a fail-closed gate.

| Job | Family | What it runs | Script |
|---|---|---|---|
| `host` | Host | `cargo fmt --check`; tools' self-tests; unit tests + strict Clippy of the 16 testable crates and their feature variants; OTA contracts (power-cut injection, geometry refusals) | `ci_host.py` |
| `riscv` | RISC-V, ESP32-C3 | compile and link of every C3 crate, signed profiles, verified-boot variants, bare-metal builds of the verifier crates | `ci_mcu.py --chip esp32c3` |
| `xtensa` | Xtensa, ESP32-S3 | same, plus the wide flash geometry; pinned toolchain always, `latest` outside pull requests | `ci_mcu.py --chip esp32s3` |
| `gate` (check name `CI`) | | passes only if `host`, `riscv` and `xtensa` are all `success` (skipped, cancelled, failed or missing = refused) | `ci_gate.py` |

Every sequence is a plain Python script with a precise chip parameter (`esp32c3`, `esp32s3`), so a developer runs
exactly what CI runs (`python3 .github/scripts/ci_host.py`, `python3 .github/scripts/ci_mcu.py --chip esp32s3`, with the
toolchains installed and `pip install esptool==5.5.0 pyyaml`). `--list` prints the commands without running them.
A failing validation does not stop the others in the same job: every failure is reported together at the end.

## Events

| Event | Host | RISC-V | Xtensa pinned | Xtensa latest | Gate |
|---|---|---|---|---|---|
| pull request | ✔ | ✔ | ✔ | – | ✔ |
| push to `main` | ✔ | ✔ | ✔ | ✔ | ✔ |
| nightly (03:47 UTC) | ✔ | ✔ | ✔ | ✔ | ✔ |
| manual (`workflow_dispatch`) | ✔ | ✔ | ✔ | ✔ | ✔ |

There is no change-based selection: the same complete validation runs every time, so no check depends on a diff.
No `paths` filter exists, so the required `CI` check is never left pending. Xtensa pinned is `1.98.1.0`; `latest`
catches upstream toolchain regressions (the repository does not commit `Cargo.lock`, so the nightly also catches
dependency drift).

Concurrency: a new push cancels the previous run of the **same pull request** only. Push, nightly and manual runs
are never cancelled by another event.

Manual dispatch has a `cache` input; switch it off to measure a cold run.

## Caches

`Swatinem/rust-cache` (pinned by SHA), one `shared-key` per environment: `host`, `riscv`, `xtensa-pinned`,
`xtensa-latest`. Caches are saved only on non-pull-request events, so they are written from `main` (and nightly)
and read by pull requests, which cannot write to each other's scope. Each job installs its toolchain once and
builds everything on the same runner and the same `target/` directory: the second stage built for the compile plan is
the ELF the later stages (console check, geometry, size gates) reuse.

## Retained checks

- host: unit tests and Clippy `-D warnings` for `example-firmware-ota-supervised`, `example-firmware-ota-system`,
  `example-supervised-component`, `iobewi-esp-boot` (`rom-verify`), `iobewi-esp-firmware-a` (`runtime`),
  `iobewi-esp-firmware-supervisor`, `iobewi-firmware-{auth,boot,bootauth,image,update}`, `iobewi-workload{,-abi,-image,-native,-pack}`;
  `auth` with and without `verify-p256,host-sign` (ECDSA P-256 / RSA-PSS), `bootauth` with `host-sign,soft-sha256`;
  `example-firmware-ota-system --features signed`; `iobewi-firmware-boot --release` (transactional boot fault
  injection, metadata and simulated power-cut tests); `iobewi-firmware-update` with `runtime`, `runtime config-space`,
  `runtime nor-flash`.
- host: flash geometry accepted at `0x8000` and `0x10000`, refused for `0x10001`, `0x4000`, `0x1c000` (for the
  right reason, not any other breakage); tracked `Cargo.lock` rejected; retired-terms check; self-tests of the CI
  tools and of the gate; the command inventory (`test_ci_inventory.py`).
- MCU (per chip): `PLAN` in `compile_mcu.py` (libraries checked, firmware linked in release, second stage built,
  converted by esptool 5.5.0 and gated against the flash limits and its geometry stamp); console transport matrix and
  shared primary console; ECDSA signed image and RSA-PSS signed image, each with its flash growth budget
  (65536 / 32768 bytes); verified-boot second stage with ROM SHA-256 (qualified backend), diagnostic build, esp-hal
  and software SHA-256, each size-gated.
- ESP32-S3: verified boot at the historical geometry reported only; wide geometry (table at `0x10000`) for the
  unsigned and verified second stage, and the application stamped with that offset.

ESP32-C3 results are compile and link validation. Only the ESP32-S3 verified boot is hardware-qualified
(`docs/firmware/verified-boot-evidence.md`); a green CI is never a hardware qualification.

## Removed with the monorepo logic

Dynamic crate discovery (`discover_ci.py`), reverse-dependency resolution, differential file selection, the
general / firmware-OTA domains, the per-crate job matrices, the 18 `ci.json` files, the `has_*` outputs and their
"not selected means skipped" gate. The Cargo workspace and its 18 crates are unchanged.

## Branch protection

Require the single check `CI` (the gate). Do not require the individual job names.

## Measurements

Full push to `main` (all families, Xtensa pinned and latest), GitHub-hosted `ubuntu-latest`:

| | Old workflow (23 jobs) | New, cold caches (5 jobs) | New, warm caches |
|---|---|---|---|
| Wall clock | 15m48s | 8m41s | 4m52s |
| Runner time | about 37.5 min | about 21.5 min | about 13.8 min |
| Longest job | 12m46s (S3 pinned) | 8m33s (Xtensa pinned) | 4m41s (Xtensa pinned) |

Pull request (new workflow, pinned only, caches from `main` not yet available): about 5m40s wall clock. Per job,
cold then warm: Host 2m33s / 1m56s, RISC-V 3m31s / 2m54s, Xtensa latest 6m45s / 4m07s.
The old critical path was serial (discover, format, host matrix, then the MCU jobs); the three families now start together.

Each environment cache is about 700 MB compressed (RISC-V, each Xtensa variant) and 178 MB (host), about 2.3 GB in
all against the repository's 10 GB limit. Caches are written only outside pull requests.

Failure behaviour was exercised on this branch: a failing Xtensa job produced a failing `CI` gate, and a cancelled
run produced a gate that ran and concluded `failure`. `test_ci_gate.py` checks all 125 result combinations.
