import tempfile
from pathlib import Path
from compile_mcu import check_size, LIMIT

with tempfile.TemporaryDirectory() as directory:
    image = Path(directory)/"boot.bin"
    for size in (1, LIMIT):
        image.write_bytes(bytes(size))
        assert check_size(image) == size
    for size in (0, LIMIT+1, 33488):  # historical Full verification overflow
        image.write_bytes(bytes(size))
        try:
            check_size(image)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid size {size}")
print("Boot image gate boundaries passed")

# The default (unsigned) second stage is gated by the geometry tool, per chip and table offset.
import esp_geometry
for chip, offset, current in (("esp32c3", 0x8000, 23008), ("esp32s3", 0x8000, 30016), ("esp32s3", 0x10000, 30016)):
    limits = esp_geometry.limits(chip, offset)
    assert limits["unsigned"] - current >= 512, "budget keeps room for ordinary growth"
    assert limits["unsigned"] <= limits["hard"]
print("Per-chip boot budgets passed")

# A firmware's MCU gate is a release link, never a cargo check; a library is a check; the second stage uses its profile.
from unittest.mock import patch
import compile_mcu
for chip in ("esp32c3", "esp32s3"):
    with patch.object(compile_mcu.subprocess, "run") as run:
        compile_mcu.compile_selected([{"package": "reference-test", "kind": "link", "features": ""}], chip)
        command = run.call_args.args[0]
        assert "build" in command and "--release" in command and "--bins" in command
        assert "check" not in command
    with patch.object(compile_mcu.subprocess, "run") as run:
        compile_mcu.compile_selected([{"package": "lib-test", "kind": "check", "features": "runtime"}], chip)
        command = run.call_args.args[0]
        assert "check" in command and "--lib" in command and "--release" not in command
        assert command[command.index("--features") + 1] == f"{chip},runtime"
print("Link / check kinds preserved")

# The static plan: every crate is built for the chips that support it, the second stage for both.
for chip in ("esp32c3", "esp32s3"):
    kinds = {item["package"]: item["kind"] for item in compile_mcu.plan_for(chip)}
    assert kinds["iobewi-esp-bootloader"] == "bootloader" and kinds["example-firmware-ota-system"] == "link"
assert "example-firmware-ota-supervised" not in {i["package"] for i in compile_mcu.plan_for("esp32c3")}
assert "example-firmware-ota-supervised" in {i["package"] for i in compile_mcu.plan_for("esp32s3")}
print("Per-chip plan passed")
