#!/usr/bin/env python3
"""Host validation of the whole workspace: format, the tools' self-tests, then for every crate its unit tests and strict
Clippy with the features it is validated with, and the OTA-specific host checks. One runner, one shared target
directory: each dependency is compiled once per feature set instead of once per crate.

  ci_host.py [--list]
"""
import argparse
import subprocess
import sys

from ci_lib import Runner

# (package, features): every crate that has a host build. The two ESP32-only crates (the bootloader and the
# flash storage adapter) are validated by ci_mcu.py.
CRATES = [
    ("example-firmware-ota-supervised", ""),
    ("example-firmware-ota-system", ""),
    ("example-supervised-component", ""),
    ("iobewi-esp-boot", "rom-verify"),
    ("iobewi-esp-firmware-a", "runtime"),
    ("iobewi-esp-firmware-supervisor", ""),
    ("iobewi-firmware-auth", "verify-p256,host-sign"),
    ("iobewi-firmware-boot", ""),
    ("iobewi-firmware-bootauth", "host-sign,soft-sha256"),
    ("iobewi-firmware-image", ""),
    ("iobewi-firmware-update", ""),
    ("iobewi-workload", ""),
    ("iobewi-workload-abi", ""),
    ("iobewi-workload-image", ""),
    ("iobewi-workload-native", ""),
    ("iobewi-workload-pack", ""),
]
TOOL_TESTS = ["test_esp_console.py", "test_compile_mcu.py", "test_esp_geometry.py", "test_ci_gate.py", "test_elf_size.py",
              "test_ci_inventory.py", "check_retired_terms.py", "check_picoserve_patch.py"]
OFFSET = "ESP_BOOTLOADER_ESP_IDF_CONFIG_PARTITION_TABLE_OFFSET"


def test_and_clippy(r, package, features="", extra=()):
    flags = ["--features", features] if features else []
    r.run(["cargo", "test", "-p", package, *flags, *extra])
    r.run(["cargo", "clippy", "-p", package, *flags, "--all-targets", "--", "-D", "warnings"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    r = Runner(parser.parse_args().list)

    with r.group("Format"):
        r.run(["cargo", "fmt", "--all", "--", "--check"])
    with r.group("CI tools self-tests and repository policy"):
        for script in TOOL_TESTS:
            r.run([sys.executable, f".github/scripts/{script}"])
        tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.splitlines() if not r.list_only else []
        if any(path == "Cargo.lock" or path.endswith("/Cargo.lock") for path in tracked):
            r.failures.append("Cargo.lock files must not be tracked")
            print("Cargo.lock files must not be tracked", flush=True)
        else:
            print("Reject tracked Cargo.lock: none tracked" if not r.list_only else "  (git ls-files: no tracked Cargo.lock)")

    for package, features in CRATES:
        with r.group(f"Tests and Clippy / {package}"):
            test_and_clippy(r, package, features)

    with r.group("HTTP parser overflow regressions, optimized profile"):
        r.run(["cargo", "test", "-p", "example-firmware-ota-system", "--release", "maintenance_http"])

    with r.group("Image authentication, unsigned profile: no asymmetric cryptography is even built"):
        r.run(["cargo", "test", "-p", "iobewi-firmware-auth"])
        r.run(["cargo", "clippy", "-p", "iobewi-firmware-auth", "--all-targets", "--", "-D", "warnings"])
    with r.group("Flash geometry, both table offsets (host)"):
        # The tests cover both reference geometries whatever the build is configured for; running them for each
        # configured offset also proves the build-time setting is read.
        for offset in ("0x8000", "0x10000"):
            r.run(["cargo", "test", "-p", "iobewi-esp-boot"], env={OFFSET: offset})
        # An offset no table can have is refused when building (the build script of iobewi-esp-partitions), not at boot.
        for bad in ("0x10001", "0x4000", "0x1c000"):
            r.run(["cargo", "check", "-q", "-p", "iobewi-esp-partitions"], env={OFFSET: bad},
                  must_fail_with=("failed to run custom build command", "build_script_build"))
    with r.group("OTA reference firmware, signed authentication profile (host)"):
        r.run(["cargo", "test", "-p", "example-firmware-ota-system", "--features", "signed"])
        r.run(["cargo", "clippy", "-p", "example-firmware-ota-system", "--features", "signed", "--all-targets", "--", "-D", "warnings"])
    with r.group("Transactional boot exhaustive fault injection"):
        r.run(["cargo", "test", "--release", "-p", "iobewi-firmware-boot"])
    with r.group("Firmware OTA runtime feature sets"):
        for features in ("runtime", "runtime config-space", "runtime nor-flash"):
            r.run(["cargo", "test", "-p", "iobewi-firmware-update", "--features", features])
            r.run(["cargo", "clippy", "-p", "iobewi-firmware-update", "--features", features, "--all-targets", "--", "-D", "warnings"])
    return r.finish()


if __name__ == "__main__":
    sys.exit(main())
