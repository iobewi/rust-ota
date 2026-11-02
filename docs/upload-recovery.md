# Upload rejection and fallback availability

Issue #4. No persistent format, IAP1 ordering or qualified S3 evidence changes.

Before invalidating a slot proof the reference application checks request identity,
length/capacity, authorization, the fixed 24-byte ESP header (magic, chip, segment
count), metadata conflicts and write-session geometry. It reads the header before
beginning metadata supersession. A short/interrupted/rejected header does not
change the slot or proof. "Untouched" does not assert that the previous image was
authentic: this path does not revalidate the old slot.

The complete image cannot be authenticated or structurally measured from that
header. Segment destinations, entry point, checksum, appended hash, complete
transport/readback digest and canonical length still require the remaining bytes.
The single streaming body reader is retained across preflight and the write.

Once proof erasure is attempted, logs conservatively report the fallback as
unavailable (or unknown on an invalidation failure). Interrupted transport, flash
write/read error, stream finish error, readback digest mismatch, structural error
and canonical-length mismatch have distinct logs. No new proof/publication follows
a readback refusal. Successful profile proof verification is logged before OTM1
publication. These are per-operation diagnostics, not durable health telemetry.

With two slots, an upload overwrites the inactive image. Preserving that entire
image after the first destructive write is impossible without another copy or
staging area. Invalidation before writing prevents an incomplete candidate from
being treated as authentic; it cannot guarantee continued fallback availability.
After a reset, availability must be assessed from flash/proof verification, never
inferred from the last in-memory upload state or a stale log.

## Recovery

1. Keep the confirmed running application powered and reachable. Retry a complete,
   correctly signed upload under its current policy, then activate and confirm it.
2. If it still runs but upload fails, retain the precise diagnostic and check the
   signed target, length and image format; a repeated upload is not evidence of
   recovery until readback, proof verification and publication succeed.
3. If the active image also becomes unusable, the verified bootloader can HALT
   (`NoUsableEntry`). Recovery then requires the independently authorized ROM
   service procedure and known-good compatible image/proof/metadata backups. Do
   not clear or format unknown metadata, bypass signature policy, or program eFuses.
4. Products without physical recovery require an additional staging/recovery
   design before claiming fleet availability. This change does not provide one.

Host tests cover early header refusals, the three readback reasons, every truncated
image prefix and the existing proof/transaction fault simulations. Remaining
hardware work: replay each refusal/interruption on S3, independently read image,
proof and OTM1 before/after, demonstrate recovery by re-upload and preserve the
qualified baseline. No such campaign was executed here; #4 remains open until
review/integration and any required application-level qualification.
