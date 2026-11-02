#!/usr/bin/env python3
"""Verify the vendored crate differs from the published source only by its patch.

No network or installed Cargo cache required. Reverse the patch in a temporary
copy, then compare every original file to its recorded SHA-256.
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor/picoserve"
metadata = json.loads((VENDOR / "UPSTREAM.json").read_text())
original = metadata["files"]
extra = {"LICENSE", "README.rust-ota.md", "UPSTREAM.json", "upstream.patch"}
actual = {str(p.relative_to(VENDOR)) for p in VENDOR.rglob("*") if p.is_file()}
if actual != set(original) | extra:
    raise SystemExit(f"Unexpected vendor files: {actual ^ (set(original) | extra)}")
with tempfile.TemporaryDirectory(prefix="picoserve-audit-") as directory:
    copy = pathlib.Path(directory) / "source"
    shutil.copytree(VENDOR, copy)
    subprocess.run(
        ["git", "apply", "--reverse", "--unidiff-zero", "--unsafe-paths", f"--directory={copy}",
         str(VENDOR / "upstream.patch")], check=True, cwd=ROOT,
    )
    for name, expected in original.items():
        actual_hash = hashlib.sha256((copy / name).read_bytes()).hexdigest()
        if actual_hash != expected:
            raise SystemExit(f"Unrecorded upstream source change: {name}")
print(f"picoserve {metadata['version']}: {len(original)} upstream files match after reversing upstream.patch")
