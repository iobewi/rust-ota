# Maintenance token authorization and request budgets

Issues #8 / #17. Both the system OTA and supervised workload handlers parse
Bearer using the existing HTTP helper, then call
`auth::maintenance::token_matches`. Absent/empty credentials and length
mismatches fail closed; equal-length bytes use `subtle::ConstantTimeEq`.
The portable primitive tests cover absent/empty/short/extended credentials and
all 256 values at every position of a binary secret.

Authorization is checked before manifest decoding, deployment/version String
allocation, component locking or application state/flash operations. No format,
key or image-signature policy is changed. The primitive is no_std and does not
add asymmetric crypto to the unsigned profile. Length is public; this is not a
claim of whole-request constant-time execution or measured timing qualification.

## HTTP availability policy

The reference HTTPS listener still accepts one connection at a time, with a
2048-byte HTTP buffer. It now closes after one request, including `/health`,
instead of allowing a persistent peer to hold the single service indefinitely.
Clients must reconnect for upload/activation/status. TLS RX/TX buffers remain
4096 bytes each; no connection pool, rate limiter or new listener is added.

The HTTP first-byte and response-write budgets retain picoserve defaults
(5 seconds to the first byte, 1 second per response-write operation). After the first byte, headers and ordinary request-body reads
have a 3-second absolute budget. Only an authorized system or supervised upload
reader gets a separate 120-second absolute body-read budget. This preserves the
existing budget for full-slot uploads (historical S3 measurement about 28 seconds)
without granting it to unauthenticated header delivery. These are async read
budgets, not a preemptive upper bound on flash operations or executor stalls.
TLS handshake timeouts, network admission and rate limiting remain transport/
product responsibilities; repeated new connections can still consume service.

### Unauthorized requests with a body

picoserve 0.20 `RequestBodyConnection::finalize` drains missing body bytes before
responding. Calling it directly on denial could hold the connection for the
upload budget. The shared reference helper `maintenance_http::reject_unauthorized`
instead uses the public `with_different_timeout_signal(ready(()))` reader. It
consumes only already-buffered body bytes and never polls the underlying reader
for additional bytes. This is not a timer reset or a second upload budget.

- Empty or fully buffered body: return `401`, then close.
- Body requiring more transport bytes: propagate the immediate read timeout;
  the server closes without promising a `401` response.
- No application mutation, slot write, manifest decoding or maintenance deadline
  refresh is performed in either rejection path.

The host tests execute this helper inside the real picoserve server with a mock
socket and frozen clock. Incomplete and immediately available large bodies must
finish in one poll, without another transport read or application mutation.
Tests also cover an empty/complete denial, an unauthorized pipelined follow-up,
one-request connection policy, and successful authorized multi-buffer reads.
This tests HTTP behavior, not TLS or physical-device timing.

## Timer audit and remaining criteria

The current system and supervised routes contain no maintenance inactivity timer
or refresh hook. The supervised runtime's probation/progress deadlines have a
different purpose; they are not refreshed on these authorization refusals. The
historical idle-timer problem must not be described as fixed merely by system
PR #19. Inspection of the current two handlers found no corresponding idle-timer
integration to change. Any future timer must be refreshed only after authorization
and appropriate accepted activity, with a product-defined maximum session life.

The product still owns provisioning, TLS identity, protected secret storage,
credential scopes and rotation/revocation. This example uses a build-time token;
changing it requires replacing the running firmware, and existing credentials
remain valid until that replacement takes effect. No runtime credential store,
expiry/revocation transaction, or hardware root of trust is provided.

Issue #17 remains open for persistence/interruption integration, credential
lifecycle and device criteria. The interruption matrix in
[security-lot3-contracts.md](security-lot3-contracts.md) remains applicable; host
simulation does not prove power-loss safety. Existing hardware qualifications
are retained without rerunning them.

The parser arithmetic defect discovered in
[#25](https://github.com/iobewi/rust-ota/issues/25) is corrected for this workspace
by a source patch of picoserve 0.20.1. Invalid/non-representable lengths and an
overflowing request-end offset receive 400/close before handler dispatch.
See [the patch provenance and removal conditions](../vendor/picoserve/README.rust-ota.md).
This does not claim a fixed crates.io release or comprehensive HTTP framing audit.
