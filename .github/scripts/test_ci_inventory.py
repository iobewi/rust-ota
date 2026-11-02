"""The validation inventory: what ci_host.py and ci_mcu.py run is listed (`--list`) and every mandatory check must be in it.

This replaces the dynamic discovery: the sequences are static, so dropping a validation shows up here as a failed test.
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]


def listing(script, *args):
    out = subprocess.run([sys.executable, str(HERE / script), *args, "--list"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def need(lines, *fragments, label=None):
    assert any(all(f in line for f in fragments) for line in lines), f"missing from the inventory: {label or fragments}"


host = listing("ci_host.py")
for crate in ("example-firmware-ota-supervised", "example-firmware-ota-system", "example-supervised-component", "iobewi-esp-boot",
              "iobewi-esp-firmware-a", "iobewi-esp-firmware-supervisor", "iobewi-firmware-auth", "iobewi-firmware-boot",
              "iobewi-firmware-bootauth", "iobewi-firmware-image", "iobewi-firmware-update", "iobewi-workload",
              "iobewi-workload-abi", "iobewi-workload-image", "iobewi-workload-native", "iobewi-workload-pack"):
    need(host, "cargo test", f"-p {crate}", label=f"test {crate}")
    need(host, "cargo clippy", f"-p {crate}", "-D warnings", label=f"clippy {crate}")
need(host, "cargo fmt", "--check")
need(host, "check_picoserve_patch.py")
need(host, "cargo test", "-p example-firmware-ota-system", "--release", "maintenance_http")
need(host, "verify-p256,host-sign", "-p iobewi-firmware-auth")                    # ECDSA P-256
need(host, "-p iobewi-firmware-auth", "cargo test")                                # unsigned
need(host, "host-sign,soft-sha256", "-p iobewi-firmware-bootauth")                 # software SHA-256
need(host, "--features signed", "-p example-firmware-ota-system")                  # signed image profile
need(host, "--release", "-p iobewi-firmware-boot")                                 # release-mode boot tests
need(host, "-p iobewi-firmware-update", "runtime config-space")
need(host, "-p iobewi-firmware-update", "runtime nor-flash")
for offset in ("0x8000", "0x10000", "0x10001", "0x4000", "0x1c000"):
    need(host, f"PARTITION_TABLE_OFFSET={offset}", label=f"geometry {offset}")
for tool in ("test_esp_console.py", "test_compile_mcu.py", "test_esp_geometry.py", "test_ci_gate.py", "test_elf_size.py",
             "test_ci_inventory.py", "check_retired_terms.py"):
    need(host, tool)
print("Host inventory passed")

for chip, target, toolchain in (("esp32c3", "riscv32imc-unknown-none-elf", "+nightly"), ("esp32s3", "xtensa-esp32s3-none-elf", "+esp")):
    mcu = listing("ci_mcu.py", "--chip", chip)
    for package in ("example-firmware-ota-system", "iobewi-esp-boot", "iobewi-esp-bootloader", "iobewi-esp-firmware-a",
                    "iobewi-esp-firmware-storage", "iobewi-esp-firmware-supervisor"):
        need(mcu, toolchain, f"--target {target}", f"-p {package}", label=f"{chip} {package}")
    need(mcu, "-p iobewi-esp-bootloader", "--profile bootloader")
    for package in ("example-firmware-ota-system",):
        need(mcu, "build", "--release", f"-p {package}", f"--features {chip}", label=f"{chip} link {package}")
    need(mcu, "console_matrix.py", f"--chip {chip}")
    need(mcu, "esp_console.py check")
    need(mcu, "IOBEWI_OTA_SIGNING_PUBKEY=", "signed")                    # ECDSA signed image
    need(mcu, "--max-growth 65536")
    need(mcu, "IOBEWI_OTA_SIGNING_RSA_KEY=", "signed-rsa")               # RSA-PSS signed image
    need(mcu, "--max-growth 32768")
    need(mcu, "verified_boot.py", f"--chip {chip}")                       # ROM SHA-256 (default backend)
    need(mcu, "verified_boot.py", "--diag")                               # diagnostic bootloader
    need(mcu, "verified_boot.py", "--sha hal")
    need(mcu, "verified_boot.py", "--sha soft")
    if chip == "esp32s3":
        need(mcu, "xtensa-esp32s3-none-elf", "-p example-firmware-ota-supervised")
        need(mcu, "-p example-supervised-component")
        need(mcu, "PARTITION_TABLE_OFFSET=0x10000", "verified_boot.py")    # wide geometry
        need(mcu, "esp_geometry.py", "image")
        need(mcu, "esp_geometry.py", "stamp")
        need(mcu, "--report-only")                                        # historical geometry: reported only
    else:
        need(mcu, "+stable", "riscv32imc-unknown-none-elf", "-p iobewi-firmware-bootauth")
print("MCU inventories passed")
