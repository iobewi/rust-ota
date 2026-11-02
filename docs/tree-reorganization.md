# Repository tree reorganization (#14)

Baseline: `ec6035b1270e1ee3a5f282d6a1f2ba15a0ee015e`, after campaign PRs
#11/#12/#13/#18/#19/#20/#21/#22/#23. This PR changes paths only. No algorithm,
public crate name, feature, Cargo profile, persistent format or Git dependency
revision changes. No hardware, flash, reset, eFuse or production-key operation.

| Before | After | Files moved |
|---|---|---:|
| common/firmware/* | common/* | 91 |
| arch/esp32/firmware/* | arch/esp32/* | 36 |
| examples/firmware/* | examples/* | 30 |
| docs/firmware/* | docs/* | 30 |

The counts are verified against the baseline below; 187 tracked files are moved
using `git mv`, with no destination collision or directory renaming exception.
`tools/component-pack` stays in place. `iobewi-firmware-layout` and
`iobewi-firmware-slots` remain external Git dependencies in rust-mcu-libs.

## Rust content comparison

[tree-reorganization-hashes.json](tree-reorganization-hashes.json) records the
old/new path and full before/after SHA-256 for every Rust file: **112 files,
105 byte-identical, seven mechanical exceptions**. No code behavior changes.

| Exception | Sole edit |
|---|---|
| arch/esp32/boot/tests/geometry.rs | Two include_str fixture paths; one rustfmt line wrap |
| common/boot/src/lib.rs | Documentation path in a comment |
| common/boot/src/tests.rs | Documentation path in a comment |
| common/bootauth/src/soft.rs | Documentation path in a comment |
| common/image/src/esp_tests.rs | Relative path to the pre-existing optional legacy image fixture; keeps the same normalized target common/web/firmware/esp32c3/app.bin |
| examples/bootloader/build.rs | Linker search path and its comment |
| examples/ota-supervised/component/build.rs | Component linker path |

The comparison script permits only these path substitutions and whitespace.
It also compares manifest contracts after removing rewired path fields, verifies
that all local Cargo paths exist within this checkout, and compares `.ld`, `.x`,
`.bin`, `.hex` and `.csv` files byte-for-byte. The optional old web image is not
included or produced by this reorganization; its test retains the previous skip
behavior when that fixture is absent. No symlink or copy of the old tree is added.

Reproduce from any full Git checkout containing the baseline commit:

```sh
python3 docs/check_tree_reorganization.py
cargo metadata --no-deps --format-version 1
python3 .github/scripts/ci_host.py
python3 .github/scripts/ci_mcu.py --chip esp32c3 --list
python3 .github/scripts/ci_mcu.py --chip esp32s3 --list
```

The workspace still has 18 members. The current CI workflow and its conditions,
architecture matrix, features and gates are unchanged; only active paths in helper
scripts are updated. MCU build/link/size/geometry validation runs through the same
CI scripts. This PR's check results must be read on its exact head in GitHub.

Packaging helpers retain their behavior: prepare.py and build-component.py now
find the root one directory shallower, the parity script likewise, and the wide
partition-table path used by CI is updated. Their help/plans and Python syntax
are checked without building an image for or accessing a device. Historical parity
execution requires the separately frozen iobewi_old checkout; that legacy campaign
is not repeated here and its existing binary fixtures are unchanged.

## Deliberately preserved historical references

- [porting-audit-s0.md](porting-audit-s0.md) is a frozen migration inventory. Its
  original paths and counts remain verbatim below a new historical-snapshot notice;
  some named paths never became crates in rust-ota. They are not active commands.
- [dual-ota.md](dual-ota.md) explicitly identifies common/firmware/slots as an
  upstream historical path, not a local directory.
- Existing GitHub URLs, commit hashes, qualification tags, raw evidence and vendor
  references remain unchanged. Local navigation/commands are updated to the new
  paths without changing recorded verdicts, measurements or qualified scope.
- The EKV campaign link in examples/ota-system/README.md already pointed outside
  this extracted repository. It now explicitly links to the same document in
  rust-mcu-libs at the pinned dependency revision, verified to exist.
- check_parity.py still uses firmware/* inside its frozen **old** checkout, and
  arch/esp32/storage retains its iobewi_old/firmware/esp32 provenance comment.

No active reference to the four retired local prefixes remains outside these
historical documents and this mapping/report tooling. Internal Markdown file
links resolve; the one pre-existing broken upstream link was corrected above.
The acquired S3 evidence matrix moves to docs/verified-boot-evidence.md; its content
and qualified tags are preserved. A green MCU build is not hardware qualification.

Issue #14 closes only after review, authorized merge and passing CI. This PR does
not carry authorization to merge itself.
