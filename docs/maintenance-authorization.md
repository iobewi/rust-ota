# Maintenance token authorization

Issues #8 / #17. The system OTA handler parses Bearer using the existing HTTP
helper, then calls auth::maintenance::token_matches. Absent/empty credentials and
length mismatches fail closed; equal-length bytes use subtle::ConstantTimeEq,
replacing ordinary string equality. Tests cover absent/empty/short/extended
credentials and all 256 values at every position of a binary secret.

This primitive is no_std, allocates nothing, and does not add asymmetric crypto
to the unsigned profile. It does not parse HTTP, store credentials, refresh a
maintenance timeout or authorize signed firmware. Length is public; this is not a
claim of whole-request constant-time execution or a measured timing qualification.
The existing TLS transport and signed-image checks retain their separate roles.

The product still owns credential provisioning/rotation, TLS identity, protected
secret storage, access scope, connection/rate/resource limits and authorized-only
deadline refresh. The system handler has no maintenance idle timer to refresh.
The supervised workload timer is a separate historical path and remains to be
reviewed under #17; this change makes no assertion that it is fixed. No secrets
or production keys were changed and no device qualification was run.
