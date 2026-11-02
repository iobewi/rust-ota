# Temporary picoserve source patch for rust-ota #25

This directory contains the published picoserve 0.20.1 crate, excluding its
Cargo.lock and registry bookkeeping, plus the upstream MIT copyright notice.
`UPSTREAM.json` records the archive SHA-256, upstream commit and per-file hashes.
`upstream.patch` is the complete source change (only request.rs and lib.rs).
No original file is otherwise edited, and the upstream test sources are retained.
The normalized published Cargo.toml is used unchanged.

Why vendor: both the published 0.20.1 source and the inspected upstream development
branch still contain the unchecked request-end addition. A route-level guard is
too late: the parser overflows before dispatch. Vendoring supplies a reproducible
workspace-wide crates.io patch without introducing another HTTP parser or waiting
for an upstream release. The crate is excluded from workspace membership; the
existing no_std examples and MCU jobs compile it as a dependency.

The patch rejects an explicitly present non-decimal/non-representable
Content-Length instead of treating parse failure as zero, then checks
`parts_length.checked_add(content_length)` before building a Request. Failure uses
the existing bad-request response/close path with an internal typed error. Missing
Content-Length still means zero. There is no new valid-image size limit, wire
format, persistent format, allocation or public API.

Run `python3 .github/scripts/check_picoserve_patch.py` to reverse the patch in a
temporary copy and verify all original hashes. The normal host runner includes
this check and debug/release HTTP regressions; the C3/S3 jobs cover the same patched
dependency. Upstream's full test suite is not added to rust-ota's workspace suite.

The patch is ready for an upstream contribution but has not been submitted or
accepted there. Remove this directory and the root Cargo.toml patch only after a
fixed upstream version passes the same tests. Without the root patch, an external
workspace using crates.io picoserve remains affected; this is a rust-ota workspace
fix, not a crates.io advisory or an upstream release.

The tests exercise malformed and overflowing lengths before handler dispatch,
exact representable request-end boundaries, connection closure/pipeline isolation,
and authorized/unauthorized normal requests. TLS, duplicate-length framing and
other parser behaviors are outside this narrowly scoped correction. No hardware
qualification or physical interruption campaign is claimed.
