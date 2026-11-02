# Deferred complementary S3 qualification

Issue #5. Historical software VerifiedBoot S3 qualification remains unchanged in
verified-boot-evidence.md and the `verified-boot-s3-qualified` tag; do not rerun it
as a prerequisite. This is the outstanding delta, not a device execution report.

Before any separately authorized execution: capture board revision/RDID/ROM banner,
exact firmware/toolchain/features, hashes of independent full/region backups, known
good image/proof pairs, and a restoration plan. Each case must record stimulus,
raw serial/reset cause, independent before/after flash reads, boot selection,
OTM1/BOOT/IAP1 state, verdict and exact restored hashes. No eFuses/production keys.

| Outstanding path | Future stimulus and acceptance evidence | Existing host support |
|---|---|---|
| Hardware watchdog | Hang while PendingVerify; TIMG0 must expire, reset cause must identify watchdog, next boot returns to authentic confirmed image without candidate promotion | pending_check timeout and BOOT pending-reset planner; cooperative timeout is not physical watchdog proof |
| Explicit self-check rejection | reject-self-check under signed-rsa; observe durable Invalid/rejection and authentic fallback after reset | boot service rejection and BOOT invalid-state tests |
| No authentic image | Independently corrupt each proof/image pair; HALT NoUsableEntry, exact metadata unchanged; authorized restore recovers | verified_boot refusal and boot_selection integration tests |
| Reverse fallback | Start confirmed ota_0, candidate ota_1; reject/interrupt candidate, prove ota_1→ota_0 with independent reads | symmetric slot/planner tests; no inference from forward device test |
| ECDSA OTA | Build signed P-256 profile, test valid/foreign/revoked key, digest/target mismatch, publication/activation and restart | real host P-256 auth_service tests; this does not qualify RSA IAP1 boot for ECDSA |
| Physical cuts | Controlled cut at erase, slot write, validation, IAP1 commit, OTM1 publish, BOOT activation and confirmation; every recovered image authentic or explicit HALT; report fallback loss, never format unknown state | BOOT exhaustive NOR model, frame/NOR prefix faults, proof_write/provision command cuts |
| Rejected/interrupted upload | Header refusal must preserve slot/proof bytes; later digest/structure/size refusal must not publish; interrupted overwrite may destroy fallback; successful re-upload recovers | PR #12 header/readback/truncated-prefix tests and upload-recovery.md |
| Panic after/before confirm | Stable resets and retries; PendingVerify resets then rolls back; blocked diagnostic cannot suppress reset | PR #13 policy/planner test and panic-recovery.md |

For physical cuts, include before/during/after each controller command and multiple
trials. Identify whether the flash controller was busy at loss of power; an API
error injection is not an electrical cut. Inspect both metadata copies and old/new
proof bytes. Include a cut during the very first publication and after an ambiguous
commit error. Report unavailable/corrupt outcomes rather than replacing them with
success. Keep rust-mcu-libs#70 (EKV interruption) explicit.

New lot-3 protected floor/key-policy promotion will require additional cuts when
implemented; it is not exercised by this existing firmware. Host coverage already
contains command/byte-prefix models; this campaign reuses them instead of inventing
a second simulator. The upload-prefix test in PR #12 strengthens rejection coverage.

Do not write PASS into the acquired evidence matrix until independent device
artifacts exist. #5 remains open. No new resistance-to-power-loss claim is made.
