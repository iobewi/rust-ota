use super::*;
use iobewi_firmware_image::esp::{self, ImageError, MemoryMap, Read};
use sha2::{Digest as _, Sha256};
use std::vec::Vec;

fn map() -> MemoryMap {
    MemoryMap {
        chip_id: 9,
        drom: 0x3c00_0000..0x3e00_0000,
        irom: 0x4200_0000..0x4400_0000,
        iram: 0x4037_0000..0x403e_0000,
        dram: 0x3fc8_0000..0x3fcf_0000,
        rtc: 0x600f_e000..0x6010_0000,
        sram_alias_offset: 0x006f_0000,
        boot_window: 0x403d_0000..0x403e_0000,
        mmu_page: 0x10000,
    }
}
fn image() -> Vec<u8> {
    let mut image = std::vec![0; 48];
    image[0] = 0xe9;
    image[1] = 1;
    image[4..8].copy_from_slice(&0x4037_0000u32.to_le_bytes());
    image[12] = 9;
    image[23] = 1;
    image[24..28].copy_from_slice(&0x4037_0000u32.to_le_bytes());
    image[28..32].copy_from_slice(&4u32.to_le_bytes());
    image[32..36].copy_from_slice(&[1, 2, 3, 4]);
    image[47] = 0xef ^ 1 ^ 2 ^ 3 ^ 4;
    let hash = Sha256::digest(&image);
    image.extend_from_slice(&hash);
    image
}
struct Bytes(Vec<u8>);
impl Read for Bytes {
    fn read(&mut self, offset: u32, out: &mut [u8]) -> Result<(), ()> {
        let source = self
            .0
            .get(offset as usize..offset as usize + out.len())
            .ok_or(())?;
        out.copy_from_slice(source);
        Ok(())
    }
}
#[test]
fn early_header_refusals_share_the_full_validators_rules() {
    let bytes = image();
    let header: [u8; 24] = bytes[..24].try_into().unwrap();
    assert_eq!(esp::validate_header(&header, &map()), Ok(()));
    for (offset, value, expected) in [
        (0, 0, ImageError::BadMagic(0)),
        (1, 0, ImageError::BadSegmentCount(0)),
        (1, 17, ImageError::BadSegmentCount(17)),
        (12, 5, ImageError::BadChip(5)),
    ] {
        let mut bad = header;
        bad[offset] = value;
        assert_eq!(esp::validate_header(&bad, &map()), Err(expected));
    }
}
#[test]
fn readback_diagnostics_distinguish_digest_structure_and_canonical_length() {
    let bytes = image();
    let size = bytes.len() as u32;
    assert_eq!(
        validate_readback(
            &mut Bytes(bytes.clone()),
            0,
            size,
            &map(),
            &[1; 32],
            &[2; 32]
        ),
        Err(ReadbackRefusal::Digest)
    );
    let mut corrupt = bytes.clone();
    corrupt[32] ^= 1;
    assert_eq!(
        validate_readback(&mut Bytes(corrupt), 0, size, &map(), &[1; 32], &[1; 32]),
        Err(ReadbackRefusal::Structure(ImageError::BadChecksum))
    );
    let mut trailing = bytes.clone();
    trailing.push(0);
    assert_eq!(
        validate_readback(
            &mut Bytes(trailing),
            0,
            size + 1,
            &map(),
            &[1; 32],
            &[1; 32]
        ),
        Err(ReadbackRefusal::CanonicalLength)
    );
    assert_eq!(
        validate_readback(
            &mut Bytes(bytes.clone()),
            0,
            size,
            &map(),
            &[1; 32],
            &[1; 32]
        ),
        Ok(())
    );
    // Interrupted writes cannot pass even if the transport supplied a valid digest.
    for prefix in 0..bytes.len() {
        assert!(
            validate_readback(
                &mut Bytes(bytes[..prefix].to_vec()),
                0,
                size,
                &map(),
                &[1; 32],
                &[1; 32]
            )
            .is_err()
        );
    }
}
