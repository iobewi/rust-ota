"""Domain partition and CI selection scenarios (fail-closed, no network besides cargo's git fetch).

In this repository every workspace crate belongs to the firmware/OTA domain; the "general" domain
belongs to iobewi/rust-mcu-libs, whose crates are git dependencies here and are not validated by this CI.
"""
from unittest.mock import patch
import discover_ci as d

packages, profiles, features, reverse = d.load_workspace()
names = set(packages)
ota = {n for n, p in packages.items() if d.in_domain(p, "firmware-ota")}
general = {n for n, p in packages.items() if d.in_domain(p, "general")}

# Partition: every crate belongs to the OTA domain, none to the general one.
assert ota == names and not general
assert {n for n, p in packages.items() if d.in_domain(p, "all")} == names
# Pinned so the OTA perimeter cannot silently shrink or drift. iobewi-firmware-layout and
# iobewi-firmware-slots stay in rust-mcu-libs (its iobewi-esp-config-space depends on them).
assert ota == {
    "iobewi-firmware-image", "iobewi-firmware-auth", "iobewi-firmware-bootauth",
    "iobewi-firmware-boot", "iobewi-firmware-update", "iobewi-workload",
    "iobewi-workload-abi", "iobewi-workload-image", "iobewi-workload-native",
    "iobewi-esp-boot", "iobewi-esp-firmware-a", "iobewi-esp-firmware-storage",
    "iobewi-esp-firmware-supervisor", "iobewi-esp-bootloader",
    "example-firmware-ota-system", "example-firmware-ota-supervised",
    "example-supervised-component", "iobewi-workload-pack",
}, sorted(ota)
# The two special OTA test suites must be reachable from the OTA domain.
assert {"iobewi-firmware-boot", "iobewi-firmware-update"} <= ota
print("Domain partition passed:", len(ota), "OTA crates, general domain empty")

def split(changed, base=None):
    chosen = d.select(changed, packages, reverse, base)
    return chosen & ota, chosen & general

def check(label, changed, want_ota, base=None):
    got_ota, got_general = split(changed, base)
    assert bool(got_ota) == want_ota and not got_general, (label, sorted(got_ota), sorted(got_general))
    print(f"ok  {label}: OTA={len(got_ota)}")
    return got_ota

check("OTA crate only", ["common/firmware/update/src/lib.rs"], True)
check("OTA example only", ["examples/firmware/ota-system/src/main.rs"], True)
check("ESP32 firmware adapter", ["arch/esp32/firmware/storage/src/lib.rs"], True)
assert "iobewi-esp-firmware-storage" in check("adapter selects its consumers", ["arch/esp32/firmware/storage/src/lib.rs"], True)
check("no change", [], False)

# Workspace manifest: member list untouched -> nothing; other keys -> everything.
with patch.object(d, "workspace_members_only", return_value=True):
    check("Cargo.toml members unchanged", ["Cargo.toml"], False, base="HEAD")
with patch.object(d, "workspace_members_only", return_value=False):
    check("Cargo.toml dependencies changed", ["Cargo.toml"], True, base="HEAD")

# Global CI tooling and unknown root files validate the whole workspace.
for path in (".github/scripts/discover_ci.py", ".github/workflows/firmware-ota.yml", "Cargo.lock", "AGENTS.md", "unknown-root-file"):
    got = split([path])
    assert got == (ota, general), path
print("ok  CI tooling / global / unknown files select the whole workspace")

# Full mode is fail-closed: an empty domain is an error, never a green no-op.
result, selected, count = d.discover(full=True, domain="firmware-ota")
assert result["include"] and selected and count == len(selected)
try:
    d.discover(full=True, domain="general")
except ValueError:
    print("ok  the general domain owns nothing here and is rejected")
else:
    raise AssertionError("empty general domain accepted")
with patch.object(d, "FIRMWARE_OTA_DIRS", ("nonexistent/",)):
    try:
        d.discover(full=True, domain="firmware-ota")
    except ValueError:
        print("ok  empty domain rejected")
    else:
        raise AssertionError("empty domain accepted")
print("Selection scenarios passed")
