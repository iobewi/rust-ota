//! Product-neutral credential comparison. Transport parsing, TLS, provisioning,
//! secret storage, rate limits and maintenance lifetimes remain product-owned.
use subtle::ConstantTimeEq;

/// Refuse absent/empty credentials. For equal lengths use `subtle`'s
/// constant-time byte comparison; length is public. Authorize BEFORE state
/// changes or idle-deadline refresh. This does not authenticate firmware images.
pub fn token_matches(expected: &[u8], presented: Option<&[u8]>) -> bool {
    let Some(presented) = presented else {
        return false;
    };
    if expected.is_empty() || presented.len() != expected.len() {
        return false;
    }
    bool::from(expected.ct_eq(presented))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn absence_and_empty_configuration_never_authorize() {
        assert!(!token_matches(b"", None));
        assert!(!token_matches(b"", Some(b"")));
        assert!(!token_matches(b"secret", None));
        assert!(!token_matches(b"secret", Some(b"")));
        assert!(!token_matches(b"secret", Some(b"secre")));
        assert!(!token_matches(b"secret", Some(b"secretx")));
    }
    #[test]
    fn every_single_byte_mismatch_is_refused_without_prefix_acceptance() {
        let expected = [0, 0xff, 0x42, b' ', b'\0', b'x'];
        assert!(token_matches(&expected, Some(&expected)));
        for index in 0..expected.len() {
            for value in 0..=u8::MAX {
                let mut presented = expected;
                presented[index] = value;
                assert_eq!(
                    token_matches(&expected, Some(&presented)),
                    value == expected[index]
                );
            }
        }
    }
}
