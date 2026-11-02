# Lot 3: security contracts and remaining integration

Issues #8, #15 (floor), #16 (keys), #17 (maintenance/resilience). No persistent
format or production key change. The qualified software S3 profile remains the
only acquired hardware evidence; these contracts do not upgrade its guarantees.

## Security version and confirmation

`security_version` is a security epoch, not a SemVer/build number. Versions in the
same epoch remain interchangeable; lowering the floor is prohibited. Existing
TrustPolicy/Target enforce a configured minimum during signature admission and
boot. Their current build-time floor is not a protected persistent counter.

`auth::floor` implements a pure promotion policy and a FloorStore adapter contract.
It never advances during probation, rejects mismatched running/confirmed identity
and a confirmed version below the floor, and retries idempotently after an old-or-new
commit. Tests simulate interruption on each side of the commit; they do not model
physical flash bit behavior. The module is not wired into confirmation or boot.

Required integration order:

1. Read a protected floor; unavailable/corrupt means unavailable, never initialize
   to zero. Configure both OTA admission and boot policy from the same authority.
2. Authenticate the candidate's version and exact canonical digest. Retain those
   bindings durably; OTM1 currently carries no security epoch. Read/verify IAP1 or
   design a justified companion journal rather than trusting an HTTP version.
3. During PendingVerify, retain the current floor so the known confirmed fallback
   remains allowed. A failed/aborted candidate never promotes anything.
4. Durably confirm the exact running image, then plan and compare-and-advance the
   floor. On ambiguous error/reset reread confirmation, image proof and floor,
   then retry. Gate maintenance until reconciliation completes. Never roll back
   confirmation to pretend a failed floor write was atomic with BOOT.
5. Before raising the floor, ensure the product has an acceptable authenticated
   recovery image at the new epoch. Confirmation alone does not preserve availability
   once the older fallback falls below the new floor.
6. Define boot behavior for interruption between confirmation and floor promotion:
   the old floor is temporarily possible. A protected promotion intent/recovery
   protocol is required before claiming durable anti-rollback. The pure planner
   alone cannot eliminate this window.

FloorStore requires compare-and-advance, no decrement, old-or-new recovery or an
explicit unavailable error, and readback. Adapter storage/protection and endurance
are MCU-specific. A compromised application can fabricate input observations to a
pure planner: protected boot/confirmation authorities are essential to a security
claim. No hardware counter implementation exists in this change.

## Key authority and compromise

Reuse TrustedKey/TrustPolicy (key fingerprint, one bound algorithm, active/revoked
state); admission and activation already reject unknown/revoked/foreign policy
proofs. Host auth-service tests cover revocation between publication and activation.
IAM1 and IAP1 remain distinct encodings, and both boot/application policies must
accept the required signer throughout rotation.

Rotation protocol: first distribute K0+K1 trust using an accepted authority, verify
that firmware AND recovery paths under K1 operate, then stop signing releases with
K0, and revoke K0 only after all required boot/application policies are updated.
Re-sign old recovery images with K1 where possible. Keep recovery authority separate
from routine release signing; exact identity/epoch bindings must survive restart.

A compromised trusted key authorizes malicious images under its allowed target and
algorithm. A new manifest signed only by that same key cannot prove recovery of
trust. Recovery needs an independently protected key/policy authority or an explicit
physical re-provisioning procedure. Static revocation cannot recall already
installed malicious firmware. Software-only bootloader pins are writable by a
physical flash writer; do not present them as hardware-protected revocation.
Dynamic key-policy persistence, generation anti-replay and recovery are outstanding
in #16; no new format is introduced without that compatibility design.

## Maintenance and credentials

The product owns provisioning, TLS/certificate validation, credential storage,
rotation, identity scope and rate/resource limits. A maintenance authorization
must precede changing state or refreshing idle deadlines. Firmware signature
verification never authenticates the remote administrator. Missing/empty credentials
must fail closed. Equal-length secrets require a reviewed constant-time primitive;
length and public request syntax may be rejected early. Do not log tokens or keys.
The system reference handler and the supervised workload timer are separate paths;
changing one is not proof of the other's correctness (#17).

## Interruption matrix

| Phase | Host invariant / required recovery | Device evidence still needed |
|---|---|---|
| Proof invalidation / image erase and write | Incomplete image never gets a new accepted proof; old inactive image may be lost | physical cut/torn erase, flash geometry, cached readback |
| Stream/readback validation | digest/structure/canonical length must pass before proof and publication | readback corruption and transport interruption |
| IAP1 publication | existing writer tests cover command/prefix cuts; rejected proof cannot activate | controller programming order and independent readback |
| OTM1 publication | old/new/error metadata; never format unknown region | EKV recovery; retain rust-mcu-libs#70 |
| Activating / boot entry | persist intent first; preserve last usable confirmed entry | command-level power cuts and reset causes |
| Confirmation | no floor promotion until durable exact-image confirmation | independent BOOT/OTM1 readback and interrupted confirmation |
| Floor promotion | no probation advance; retry from read floor; old/new/error | protected backend, promotion-intent recovery and endurance |
| Key-policy promotion | generation cannot replay; recovery signer remains valid | protected backend and cut/revocation campaign |

The existing BOOT exhaustive NOR, frame-store byte-prefix, IAP1 provisioning and
OTA authorization tests are reused; no second update engine or parallel codec.
No declaration of resistance to power loss is justified by these host models.
