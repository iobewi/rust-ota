#!/usr/bin/env python3
"""Compilation, link and size validation for one chip: `--chip esp32c3` (RISC-V) or `--chip esp32s3` (Xtensa).

One script per architecture family, parametrised by the exact chip because ROM, flash geometry and the bootloader
differ. The same sequence runs in CI and on a developer machine with the chip's toolchain installed (nightly with
rust-src for esp32c3, the `esp` toolchain for esp32s3) and `pip install esptool==5.5.0`.

Stages, in order (later ones use the ELF files built by the first):
  1. every crate of the chip (compile_mcu.PLAN): libraries checked, firmware linked in release, second stage built,
     converted to an image and gated against the flash limits;
  2. console transport matrix; the second stage and the application share one primary console;
  3. signed application profiles (ECDSA P-256, then RSA-PSS with boot proofs) and their flash cost over the unsigned one;
  4. verified-boot second stage: ROM SHA-256 (the qualified backend), diagnostic build, esp-hal and software SHA-256;
  5. esp32s3 only: the wide flash geometry (table at 0x10000) for the second stage and the application.
esp32c3 only: the portable authentication crates also build for the bare-metal target with the stable toolchain.

  ci_mcu.py --chip esp32c3|esp32s3 [--list]
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

import compile_mcu
from ci_lib import Runner

SCRIPTS = ".github/scripts"
OFFSET = "ESP_BOOTLOADER_ESP_IDF_CONFIG_PARTITION_TABLE_OFFSET"
# Public test fixtures only (their private halves are test keys of the host suites, or exist nowhere in this
# repository): the firmware pins these keys, nothing is signed here.
ECDSA_PUBKEY = "04f869e567b81900d7b41aced0678a52a5a8400827784110eb78597ba75a34f9f5067f982914d934e1ecd85c6cf9c7e741eb25c1b197ec5113871b215448cd4c46"
RSA_FIXTURE = Path(".github/fixtures/ota-signing-rsa-test-public.hex")


def py(script, *args):
    return [sys.executable, f"{SCRIPTS}/{script}", *args]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chip", required=True, choices=sorted(compile_mcu.CHIPS))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    chip = args.chip
    toolchain, target = compile_mcu.CHIPS[chip]
    r = Runner(args.list)
    tmp = Path(tempfile.mkdtemp(prefix="ci-mcu-"))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    release = Path("target") / target / "release" / "firmware-ota-system-esp32"
    boot = Path("target") / target / "bootloader" / "iobewi-esp-bootloader"
    cargo = ["cargo", f"+{toolchain}", "build", "-Z", "build-std=core,alloc", "--target", target]
    os.environ["CI_ESPTOOL_READY"] = "1"          # compile_mcu installs esptool only when it is not already there

    with r.group("esptool"):
        r.run([sys.executable, "-m", "pip", "install", "esptool==5.5.0"])

    if chip == "esp32c3":
        with r.group("Portable authentication builds for the bare-metal target (stable toolchain)"):
            # The verifier crates run in the 32 KiB second stage: no_std, no allocation, no host-only code.
            t = "riscv32imc-unknown-none-elf"
            r.run(["cargo", "+stable", "build", "-p", "iobewi-firmware-auth", "--features", "verify-p256", "--target", t])
            r.run(["cargo", "+stable", "build", "-p", "iobewi-firmware-auth", "--target", t])
            r.run(["cargo", "+stable", "build", "-p", "iobewi-firmware-bootauth", "--target", t])

    with r.group(f"Compile the {chip} crates"):
        if r.list_only:
            for item in compile_mcu.plan_for(chip):
                r.run(["cargo", f"+{toolchain}", "build" if item["kind"] != "check" else "check", "-Z", "build-std=core,alloc", "--target", target,
                       "-p", item["package"], "--features", ",".join(f for f in (chip, item["features"]) if f),
                       "--lib" if item["kind"] == "check" else "--bins",
                       *(["--profile", "bootloader"] if item["kind"] == "bootloader" else ["--release"] if item["kind"] == "link" else [])])
        else:
            try:
                compile_mcu.compile_selected(compile_mcu.plan_for(chip), chip)
            except Exception as error:      # CalledProcessError or a boot image gate
                r.failures.append(f"Compile the {chip} crates: {error}")
                print(f"error: {error}", flush=True)

    with r.group(f"Console transport matrix ({chip})"):
        r.run(py("console_matrix.py", "--chip", chip))
    with r.group(f"Bootloader and application share the primary console ({chip})"):
        r.run(py("esp_console.py", "check", boot, release))

    footprint = {"tee": summary} if summary else {}
    with r.group("Signed OTA profile (ECDSA P-256), build and flash cost"):
        if not r.list_only:
            import shutil
            shutil.copy(release, tmp / "unsigned.elf")
        r.run([*cargo, "-p", "example-firmware-ota-system", "--features", f"{chip},signed", "--bins", "--release"],
              env={"IOBEWI_OTA_SIGNING_PUBKEY": ECDSA_PUBKEY})
        if summary:
            Path(summary).open("a").write(f"### OTA flash footprint, {chip}\n")
        r.run(py("elf_size.py", "--compare", tmp / "unsigned.elf", release, "--max-growth", "65536"), **footprint)
    with r.group("RSA-PSS OTA profile with boot proofs, build and flash cost"):
        # Measured growth over the unsigned build: about 14 KiB (C3) and 17 KiB (S3).
        key = RSA_FIXTURE.read_text().strip() if RSA_FIXTURE.exists() else "<hex of the RSA test fixture>"
        r.run([*cargo, "-p", "example-firmware-ota-system", "--features", f"{chip},signed-rsa", "--bins", "--release"],
              env={"IOBEWI_OTA_SIGNING_RSA_KEY": key})
        if summary:
            Path(summary).open("a").write(f"### OTA flash footprint (RSA-PSS), {chip}\n")
        r.run(py("elf_size.py", "--compare", tmp / "unsigned.elf", release, "--max-growth", "32768"), **footprint)

    if chip == "esp32c3":
        with r.group("Verified boot second stage, link and size gate"):
            r.run(py("verified_boot.py", "--chip", chip))
        with r.group("Verified boot diagnostic build (diag-panic), link and size gate"):
            # Off by default, never in the nominal image; it must keep building and fitting (docs/verified-boot-p3-diagnosis.md).
            r.run(py("verified_boot.py", "--chip", chip, "--diag"))
        with r.group("Verified boot, other SHA-256 backends (esp-hal, software), link and size gate"):
            # Selectable at build time, the ROM's is the default and the one qualified on hardware; these two must
            # keep building and fitting (docs/verified-boot-sha.md).
            r.run(py("verified_boot.py", "--chip", chip, "--sha", "hal"))
            r.run(py("verified_boot.py", "--chip", chip, "--sha", "soft"))
    else:
        wide = {OFFSET: "0x10000"}
        with r.group("Verified boot second stage, historical geometry (report only)"):
            # With the historical table at 0x8000 the S3 verified second stage does not fit (docs/verified-boot.md):
            # reported only. The wide geometry below is the gate.
            r.run(py("verified_boot.py", "--chip", chip, "--report-only"))
        with r.group("Wide flash geometry (table at 0x10000), second stage and application"):
            r.run(py("esp_geometry.py", "csv", "examples/ota-system/partitions-s3-16mb-wide.csv"), env=wide)
            r.run(["cargo", f"+{toolchain}", "build", "-Z", "build-std=core,alloc", "--target", target, "--profile", "bootloader",
                   "-p", "iobewi-esp-bootloader", "--features", chip, "--bins"], env=wide)
            r.run([sys.executable, "-m", "esptool", "--chip", chip, "elf2image", "--flash-mode", "dio", "--flash-size", "16MB",
                   "--output", tmp / "boot-wide.bin", boot], env=wide)
            # Flash limits, geometry stamp and RAM placement of the linked second stage.
            r.run(py("esp_geometry.py", "image", chip, tmp / "boot-wide.bin", "--elf", boot, "--profile", "unsigned"), env=wide, **footprint)
            # The verified profile fits this geometry: blocking.
            r.run(py("verified_boot.py", "--chip", chip), env=wide)
            # The application is built for the same table offset or the packaging refuses it.
            r.run([*cargo, "-p", "example-firmware-ota-system", "--features", chip, "--bins", "--release"], env=wide)
            r.run([sys.executable, "-m", "esptool", "--chip", chip, "elf2image", "--flash-size", "16MB",
                   "--output", tmp / "app-wide.bin", release], env=wide)
            if r.list_only:
                print("  test \"$(esp_geometry.py stamp app-wide.bin)\" = 0x10000")
            else:
                import subprocess
                stamp = subprocess.run(py("esp_geometry.py", "stamp", tmp / "app-wide.bin"), capture_output=True, text=True).stdout.strip()
                print(f"application table-offset stamp: {stamp}", flush=True)
                if stamp != "0x10000":
                    r.failures.append(f"application stamped {stamp!r}, expected '0x10000'")
        with r.group("Verified boot diagnostic build (diag-panic), wide geometry"):
            # Last on purpose: it replaces the linked second stage under target/.
            r.run(py("verified_boot.py", "--chip", chip, "--diag"), env=wide)
        with r.group("Verified boot, other SHA-256 backends (esp-hal, software), wide geometry"):
            r.run(py("verified_boot.py", "--chip", chip, "--sha", "hal"), env=wide)
            r.run(py("verified_boot.py", "--chip", chip, "--sha", "soft"), env=wide)
    return r.finish()


if __name__ == "__main__":
    sys.exit(main())
