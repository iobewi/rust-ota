//! Portable planning contract for security-floor promotion, not an integrated
//! anti-rollback implementation. The platform supplies authenticated identity,
//! durable confirmation and protected persistence. No flash format is defined.
use iobewi_firmware_image::Digest;

/// Confirmation observed independently from durable boot metadata. The version
/// must come from a verified manifest bound to `running`, never from request data.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Confirmation {
    Unconfirmed,
    Confirmed { running: Digest, confirmed: Digest },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Refusal {
    IdentityMismatch,
    BelowFloor,
}

/// A monotonic, conditional persistence request. Private fields prevent callers
/// from constructing a decrement without going through the promotion policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Advance {
    expected: u32,
    next: u32,
}
impl Advance {
    pub const fn expected(self) -> u32 {
        self.expected
    }
    pub const fn next(self) -> u32 {
        self.next
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Promotion {
    /// No floor write during startup/probation or after rejection.
    Deferred,
    /// Already durable: a retry must not consume another monotonic counter step.
    Unchanged,
    Advance(Advance),
}

/// Pure decision only. Confirmation must be durable BEFORE this is called with
/// `Confirmed`. Its caller must verify identity/version provenance and block new
/// maintenance operations until any required promotion has completed.
pub fn plan(
    current: u32,
    authenticated_version: u32,
    confirmation: Confirmation,
) -> Result<Promotion, Refusal> {
    let Confirmation::Confirmed { running, confirmed } = confirmation else {
        return Ok(Promotion::Deferred);
    };
    if running != confirmed {
        return Err(Refusal::IdentityMismatch);
    }
    if authenticated_version < current {
        return Err(Refusal::BelowFloor);
    }
    if authenticated_version == current {
        return Ok(Promotion::Unchanged);
    }
    Ok(Promotion::Advance(Advance {
        expected: current,
        next: authenticated_version,
    }))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StoreError<E> {
    Backend(E),
    /// Unreadable/corrupt is not a zero floor or permission to initialize.
    Corrupt,
    Conflict {
        actual: u32,
    },
}

/// An adapter must serialize compare-and-advance with other writers. A reset
/// during advance must recover old OR new (never lower/partial), or return an
/// error which the product treats as unavailable. Failure may have committed:
/// reread and replan before retrying. Read back after success before advertising
/// completion. No implementation/protection/power-loss safety is implied here.
pub trait FloorStore {
    type Error;
    fn read(&self) -> Result<u32, StoreError<Self::Error>>;
    fn advance(&mut self, change: Advance) -> Result<(), StoreError<Self::Error>>;
}

#[cfg(test)]
mod tests {
    use super::*;
    const IMAGE: Digest = Digest([1; 32]);
    fn confirmed() -> Confirmation {
        Confirmation::Confirmed {
            running: IMAGE,
            confirmed: IMAGE,
        }
    }
    #[test]
    fn probation_never_promotes_even_at_boundaries() {
        for current in [0, 1, 7, u32::MAX] {
            for version in [0, 1, 7, u32::MAX] {
                assert_eq!(
                    plan(current, version, Confirmation::Unconfirmed),
                    Ok(Promotion::Deferred)
                );
            }
        }
    }
    #[test]
    fn identity_monotonicity_and_idempotence_are_required() {
        assert_eq!(
            plan(
                1,
                2,
                Confirmation::Confirmed {
                    running: IMAGE,
                    confirmed: Digest([2; 32])
                }
            ),
            Err(Refusal::IdentityMismatch)
        );
        for current in [0, 1, 7, u32::MAX] {
            for version in [0, 1, 7, u32::MAX] {
                match plan(current, version, confirmed()) {
                    Err(Refusal::BelowFloor) => assert!(version < current),
                    Ok(Promotion::Unchanged) => assert_eq!(version, current),
                    Ok(Promotion::Advance(change)) => {
                        assert_eq!(change.expected(), current);
                        assert_eq!(change.next(), version);
                        assert!(version > current);
                        assert_eq!(
                            plan(version, version, confirmed()),
                            Ok(Promotion::Unchanged)
                        );
                    }
                    other => panic!("unexpected promotion: {other:?}"),
                }
            }
        }
    }
    /// A deterministic transactional adapter MODEL. A real MCU adapter must prove
    /// the old-or-new/error contract independently, including rust-mcu-libs#70.
    struct Model {
        floor: u32,
        cut: Option<bool>,
    }
    impl FloorStore for Model {
        type Error = ();
        fn read(&self) -> Result<u32, StoreError<()>> {
            Ok(self.floor)
        }
        fn advance(&mut self, change: Advance) -> Result<(), StoreError<()>> {
            if self.floor != change.expected {
                return Err(StoreError::Conflict { actual: self.floor });
            }
            if self.cut != Some(false) {
                self.floor = change.next;
            }
            if self.cut.is_some() {
                Err(StoreError::Backend(()))
            } else {
                Ok(())
            }
        }
    }
    #[test]
    fn interruption_before_or_after_commit_replans_without_endangering_probation() {
        for cut in [Some(false), Some(true), None] {
            let mut store = Model { floor: 1, cut };
            assert_eq!(
                plan(store.read().unwrap(), 3, Confirmation::Unconfirmed),
                Ok(Promotion::Deferred)
            );
            assert_eq!(store.floor, 1); // old confirmed firmware remains admissible
            let Promotion::Advance(change) = plan(1, 3, confirmed()).unwrap() else {
                panic!()
            };
            let _ = store.advance(change); // success OR failure can have committed
            store.cut = None;
            match plan(store.read().unwrap(), 3, confirmed()).unwrap() {
                Promotion::Advance(retry) => store.advance(retry).unwrap(),
                Promotion::Unchanged => {}
                _ => panic!(),
            }
            assert_eq!(store.floor, 3);
            assert_eq!(plan(3, 3, confirmed()), Ok(Promotion::Unchanged));
            assert_eq!(
                store.advance(change),
                Err(StoreError::Conflict { actual: 3 })
            );
        }
    }
}
