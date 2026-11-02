# Reference application's fatal-panic policy

Issue #3. The application arms TIMG0 for a 1-second reset **before** console panic
output, then spins. This applies during startup, PendingVerify and Stable,
including after confirmation disabled the normal probation watchdog. The boot
watchdog policy and normal confirmation path are unchanged. No flash operation,
confirmation, rejection, asynchronous cleanup, logger lock or allocator is used by
the new panic path. The existing console diagnostic remains best effort.

The reset deadline does not rely on diagnostics returning. Re-arming shortens the
normal probation watchdog deadline after a panic. Persisted PendingVerify remains
PendingVerify, so boot selection rolls back instead of confirming a crashed image.
In Stable, the confirmed image is retried. A deterministic panic can cause a reboot
loop; this policy supplies recovery from a transient fault, not a recovery image or
health-driven rollback of an already confirmed firmware. A missing authentic
fallback can still HALT (see issue #4).

Host tests exercise reset selection using the real BOOT v2 planner with unchanged
Stable/PendingVerify entries. They do not execute the panic handler, prove TIMG0
expiry or cover a failed peripheral bus. MCU compile/link CI checks the binding.

## Deferred device qualification (not executed)

Use a dedicated fault-injection build, preserve original image/proof/otadata/config
and baseline qualified firmware. No eFuses or new keys.

1. Confirm a candidate, independently read its Valid entry, provoke a fatal panic
   from the main application, and measure reset within the watchdog bound plus
   boot time. Check console output but repeat with console output unavailable.
   Confirm the same image boots and metadata was not promoted/reformatted by panic.
2. Provoke panic during PendingVerify before confirmation; independently read
   pending intent before the trigger. Check watchdog reset and bootloader rollback
   to the authentic confirmed slot, with no candidate confirmation.
3. Repeat during startup and after a metadata-completion failure. Check reset cause
   and read metadata independently. A blocked logger must not prevent reset.
4. Demonstrate/report an intentionally persistent panic loop and recovery limits,
   then restore exact backups and baseline. Do not restart the acquired historical
   S3 qualification campaign.

Issue #3 stays open until these device checks are authorized and pass.
