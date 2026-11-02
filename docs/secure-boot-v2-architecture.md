# ESP32-S3 hardware trust: architecture study

Issue #2. Study only: no hardware root of trust implemented, no eFuses touched,
no production key changed. Software VerifiedBoot S3 qualification is preserved.

## Correct size baseline

The issue's historical 28,672-byte ceiling is not the current S3 ROM absolute
limit. The existing flash-geometry.md already distinguishes flash placement,
RAM loading and a future signature sector; do not revert it. Official S3 guidance
states 64 KiB of bootloader image excluding the 4 KiB signature sector:
[bootloader size](https://docs.espressif.com/projects/esp-idf/en/v5.3.5/esp32s3/api-guides/bootloader.html#bootloader-size).

| Constraint | Current study conclusion |
|---|---|
| Historical table at 0x8000, boot offset 0 | 32 KiB region; verified image does not fit even unsigned by ROM |
| Wide table at 0x10000 | 64 KiB region; reserve final 4 KiB for SBV2 signature, so padded unsigned image must be ≤61,440 bytes |
| Measured verified image in flash-geometry.md | 34,896 bytes for its recorded build, so align-up-to-4KiB 36,864 + signature 4,096 = 40,960 bytes; fits wide region |
| RAM | Existing 36 KiB code and 32 KiB data windows remain independently gated by ELF placement; signature/flash fit does not prove ROM staging/stack compatibility |
| Current exact build | Use its CI artifact and measurement, never substitute an older issue/document size |

No compression, new persistent format or larger RAM window is justified merely by
the obsolete 28 KiB number. Packaging checks must eventually validate the SIGNED
artifact, its sector alignment, the partition table and the ROM's load regions.

## Trust chain and formats

[S3 SBV2](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/secure-boot-v2.html)
authenticates the second stage through RSA-PSS and eFuse-anchored public-key
digests. Its signature sector is an Espressif format; IAM1/IAP1 are not that sector.
Do not hand IAP1 to the ROM or assume an IAM1 signature signs padded SBV2 bytes.

Proposed custom chain: ROM authenticates this second stage; the second stage then
runs its existing mandatory IAP1/canonical-image verification before every app
jump, including fallback. The bootloader's embedded application key policy becomes
protected only insofar as the second stage cannot be replaced by an unauthorized
one. This is a proposed custom authenticated chain, not a claim that current apps
implement the standard ESP-IDF SBV2 application packaging. A standard SBV2-app
compatibility profile would need its own verifier/padding design and tests.

Keep bootloader signing keys separate from application release keys. Evaluate all
three hardware key-digest slots and revocation policy before provisioning; revoking
the sole usable bootloader key destroys recovery. IAP1 application-key rotation
must remain consistent with boot policy; application revocation does not revoke a
ROM bootloader signer. Anti-rollback of a signed but obsolete second stage is an
additional requirement: signing alone cannot prevent replay of an older vulnerable
policy. #8/#15/#16 own the protection/version decisions.

## Flash encryption and debug access

Flash encryption is a separate confidentiality mechanism, not authenticity or
anti-rollback. The custom read/hash/load paths currently assume ordinary flash
bytes. Before enabling it, specify where reads are decrypted (ROM, mapped cache,
raw SPI), encrypted-write alignment and image/proof/metadata partition policy.
Hashing ciphertext against an IAM1 plaintext digest must fail; mixing modes is not
a recovery strategy. Encryption/debug/download-mode restrictions need a complete
ROM-recovery threat model and an independent integration campaign. See official
[S3 flash-encryption guidance](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/flash-encryption.html).

## Integration stages (future, separately authorized)

1. Host-only signed packaging with public test fixtures: pin tools, verify SBV2
   signatures and geometry independently, reject tampered/padded/truncated images;
   audit all app-jump paths and key-policy/version provenance. No device writes.
2. Dedicated sacrificial board: inventory revision/eFuse state read-only and verify
   backup/recovery design. An unsigned board test cannot prove ROM enforcement.
3. If supported by the selected ROM, explicitly validate signature verification
   without enabling permanent secure mode; record exactly what this establishes.
4. Present a concrete key-digest/revocation/debug/download/encryption configuration
   with recovery artifacts and obtain explicit approval before ANY irreversible
   step. No first-boot code may silently provision or lock anything.
5. Provision/enable only in the separately approved campaign, test tampered second
   stage/app and both fallback slots, power cuts, key loss/revocation, rollback,
   debug/download restrictions and documented recovery. Encryption is a separate
   stage with its own backups and acceptance criteria.

Issue #2 remains open: packaging implementation, ROM staging behavior, immutable
policy/version enforcement, provisioning/recovery decisions and hardware evidence
are outstanding. This study is not permission to execute any stage.
