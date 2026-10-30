//! ATMETA01 export decoder. Keeps bank offsets, authored order and every float/payload word unchanged.
use super::{
    AnimationMetadata, BlendSimplexMetadata, BlendSpaceMetadata, ClipAttribute, ClipMetadata, File, PhaseBlendMetadata,
    SelectionCandidateMetadata, SelectionParameterMetadata, SelectionSpaceMetadata, SelectorMetadata, UnsupportedTree,
};
use hakuba_skate_schema::{Error, Reader};

type Result<T> = std::result::Result<T, Error>;

pub(crate) fn load(bytes: &[u8]) -> std::result::Result<AnimationMetadata, String> {
    let file = decode(bytes).map_err(|e| format!("Invalid native animation metadata: {e}"))?;
    AnimationMetadata::from_file(file)
}

fn decode(bytes: &[u8]) -> Result<File> {
    let mut r = Reader::new(bytes, b"ATMETA01")?;
    let source_bank = r.string()?.to_owned();
    let source_sha256 = r.string()?.to_owned();
    let source_bytes = r.wide()?;
    let clips = items(&mut r, 32, |r| {
        let name = r.string()?.to_owned();
        let source_offset = r.wide()?;
        let fps_bits = r.word()?;
        let frames_bits = r.word()?;
        let base_speed_bits = r.word()?;
        let flags_word = r.word()?;
        let attributes = items(r, 28, |r| {
            let name = r.string()?.to_owned();
            let type_id =
                u8::try_from(r.word()?).map_err(|_| Error("animation attribute type exceeds byte range".into()))?;
            Ok(ClipAttribute {
                name,
                type_id,
                begin_bits: r.word()?,
                end_bits: r.word()?,
                source_offset: r.wide()?,
                payload_words: words(r)?,
            })
        })?;
        Ok(ClipMetadata { name, source_offset, fps_bits, frames_bits, base_speed_bits, flags_word, attributes })
    })?;
    let phase_blends = items(&mut r, 20, |r| {
        Ok(PhaseBlendMetadata {
            name: r.string()?.to_owned(),
            source_offset: r.wide()?,
            parameter: r.string()?.to_owned(),
            children: names(r)?,
        })
    })?;
    let blend_spaces = items(&mut r, 24, |r| {
        Ok(BlendSpaceMetadata {
            name: r.string()?.to_owned(),
            source_offset: r.wide()?,
            parameters: names(r)?,
            children: names(r)?,
            simplexes: items(r, 16, |r| {
                Ok(BlendSimplexMetadata {
                    children: words(r)?.into_iter().map(|v| v as usize).collect(),
                    vertex_bits: matrix(r)?,
                    normal_bits: matrix(r)?,
                    scale_bits: words(r)?,
                })
            })?,
        })
    })?;
    let selectors = items(&mut r, 28, |r| {
        Ok(SelectorMetadata {
            name: r.string()?.to_owned(),
            source_offset: r.wide()?,
            parameter: r.string()?.to_owned(),
            default: r.string()?.to_owned(),
            children: names(r)?,
            values: names(r)?,
        })
    })?;
    let selection_spaces = items(&mut r, 20, |r| {
        Ok(SelectionSpaceMetadata {
            name: r.string()?.to_owned(),
            source_offset: r.wide()?,
            parameters: items(r, 20, |r| {
                Ok(SelectionParameterMetadata {
                    name: r.string()?.to_owned(),
                    mode: r.word()?,
                    weight_bits: r.word()?,
                    minimum_bits: r.word()?,
                    maximum_bits: r.word()?,
                })
            })?,
            candidates: items(r, 8, |r| {
                Ok(SelectionCandidateMetadata { child: r.string()?.to_owned(), value_bits: words(r)? })
            })?,
        })
    })?;
    let unsupported_trees = items(&mut r, 16, |r| {
        Ok(UnsupportedTree { name: r.string()?.to_owned(), source_offset: r.wide()?, type_id: r.word()? })
    })?;
    r.end()?;
    Ok(File {
        version: 1,
        source_bank,
        source_sha256,
        source_bytes,
        clips,
        phase_blends,
        blend_spaces,
        selectors,
        selection_spaces,
        unsupported_trees,
    })
}

fn items<T>(r: &mut Reader<'_>, minimum: usize, mut read: impl FnMut(&mut Reader<'_>) -> Result<T>) -> Result<Vec<T>> {
    let count = r.word()? as usize;
    if count > r.remaining() / minimum {
        return Err(Error("animation metadata count exceeds remaining bytes".into()));
    }
    (0..count).map(|_| read(r)).collect()
}

fn words(r: &mut Reader<'_>) -> Result<Vec<u32>> {
    items(r, 4, |r| r.word())
}

fn names(r: &mut Reader<'_>) -> Result<Vec<String>> {
    items(r, 4, |r| Ok(r.string()?.to_owned()))
}

fn matrix(r: &mut Reader<'_>) -> Result<Vec<Vec<u32>>> {
    items(r, 4, words)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::animation_metadata::TreeMetadata;

    // Exact first authored records in each supported arena of the on-board bank.
    // The full two-dimensional BlendSpace retains all ten simplexes, including -0.
    // These bytes are independent of this decoder and come from the motion export.
    fn golden() -> Vec<u8> {
        concat!(
            "41544d45544130310c0000004f6e426f6172642e6162696e40000000333061613332346436643763353163333235643533653932363863316164393137383362",
            "30313534643231626265663564633561363165616538333333626437788ca40000000000010000000f0000004b45455044454641554c54414e494d8005000000",
            "000000000070420000ca420000803f01688c00010000000d0000004753545244495354544f434f4700000000000080bf000080bfc01a00000000000004000000",
            "3a5b7c3f000000000000000000000000010000001c000000425f414e5449435f494e544f5f484947485f5354525f43454e54455270b404000000000009000000",
            "44495354544f434f47020000001d000000525f414e5449435f43524f5543485f4f4c4c49455f4e5f305f494e544f16000000525f414e5449435f4f4c4c49455f",
            "4e5f305f494e544f010000000f000000424c454e445f46535f545745414b32b0c92100000000000200000007000000545745414b5f5807000000545745414b5f",
            "59090000001200000047525f475241425f4e5f46535f305f4359431700000047525f5354494646595f4e5f46535f494e544f5f4359431400000047525f535449",
            "4646595f4e5f46535f305f4359431300000047525f544b4e45455f4e5f46535f305f4359431300000047525f4e424f4e455f4e5f46535f305f43594313000000",
            "47525f54424f4e455f4e5f46535f305f4359431a00000047525f475241425f4653414e4454424f4e455f4e5f305f4359431d00000047525f475241425f54424f",
            "4e45414e44544b4e45455f4e5f305f4359431c00000047525f475241425f5442544b414e44544b4e45455f4e5f305f4359430a00000003000000040000000000",
            "0000030000000300000002000000000000000000803f020000000000000000000000020000000000803f000000000300000002000000000000800000803f0200",
            "0000f30435bff30435bf020000000000803f00000000030000000000803ff304b53f0000803f0300000006000000070000000500000003000000020000000ad7",
            "23bc6666e6be020000005c8f023f5c8f02bf0200000000000000000080bf03000000020000000e5d31bf529a383f020000002cf57f3fbceb943c020000000cc0",
            "eabd0c507ebf0300000019991e404db6f63f8ec3ea3f0300000006000000070000000000000003000000020000000ad723bc6666e6be020000005c8f023f5c8f",
            "02bf0200000000000000000000000300000002000000f40435bff40435bf02000000d3ef7f3fe0ffb5bc020000000cc0ea3d0c507e3f0300000099c24440bd95",
            "f53fb9cc0e400300000008000000000000000300000003000000020000008fc2353f52b89ebe020000000000000000000000020000000000803f000000000300",
            "00000200000000000000000080bf0200000011f33abf63e32e3f020000005cdfcc3eaf9c6a3f030000009d734e40fd46af3f81f11f4003000000080000000700",
            "00000000000003000000020000008fc2353f52b89ebe020000005c8f023f5c8f02bf0200000000000000000000000300000002000000f404353ff404353f0200",
            "00005cdfccbeaf9c6abf02000000f30435bff304353f030000002f4662401e0d73404e78b13f0300000001000000040000000200000003000000020000005c8f",
            "02bf0ad7233c02000000000000000000803f02000000000080bf000000000300000002000000f304353ff30435bf020000001c26a7bc5bf27f3f02000000d693",
            "63bf4979ea3e03000000d18f3c40a2b1823f567c14400300000001000000040000000000000003000000020000005c8f02bf0ad7233c02000000000000000000",
            "803f0200000000000000000000000300000002000000000080bf0000008002000000b998a03c67f37f3f02000000d693633f4979eabe03000000fbfafa3f4d06",
            "803f51c00b400300000001000000060000000000000003000000020000005c8f02bf0ad7233c020000000ad723bc6666e6be0200000000000000000000000300",
            "000002000000d3ef7fbfe0ffb53c02000000b998a0bc67f37fbf0200000094532d3ffa653c3f03000000d9eefa3f07300e400c623d4003000000010000000500",
            "00000200000003000000020000005c8f02bf0ad7233c0200000000000000000080bf02000000000080bf000000000300000002000000f304353ff304353f0200",
            "00001c26a73c5bf27fbf02000000e18464bf18c8e6be03000000f3043540a7ee7a3fa8d310400300000001000000060000000500000003000000020000005c8f",
            "02bf0ad7233c020000000ad723bc6666e6be0200000000000000000080bf03000000020000002cf57fbfbceb94bc02000000e184643f18c8e63e020000009453",
            "2dbffa653cbf03000000f432024087e68540b5ce20400100000016000000535f47525f5354414c45475241425f4e5f315f43594320dd21000000000009000000",
            "50524f534b415445521400000047525f5354414c45475241425f4e5f315f435943020000001400000047525f5354414c45475241425f4e5f315f435943160000",
            "0050524f5f474f4e5a5f5354414c45475241425f435943020000000700000044454641554c5405000000474f4e5a4f010000001100000053535f44534c494445",
            "4f55545f42535f52c03545000000000001000000050000005457495354000000000000803f0000000000000000030000001b000000425f44534c4944455f4253",
            "5f54574953545f305f455849545f525401000000000000001b000000425f44534c4944455f42535f54574953545f4c5f455849545f525401000000000080bf1b",
            "000000425f44534c4944455f42535f54574953545f525f455849545f5254010000000000803f00000000",
        )
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
    }

    #[test]
    fn authored_metadata_bytes_keep_bits_offsets_and_tree_references() {
        let metadata = load(&golden()).unwrap();
        assert_eq!(metadata.source_bank, "OnBoard.abin");
        assert_eq!(metadata.sources()[0].source_bytes, 10_783_864);
        assert_eq!(metadata.source_sha256, "30aa324d6d7c51c325d53e9268c1ad91783b0154d21bbef5dc5a61eae8333bd7");
        let clip = metadata.clip("keepdefaultanim").unwrap();
        assert_eq!(clip.source_offset, 1408);
        assert_eq!(clip.fps_bits, 60.0_f32.to_bits());
        assert_eq!(clip.frames_bits, 101.0_f32.to_bits());
        assert_eq!(clip.flags_word, 9_201_665);
        let attribute = &clip.attributes[0];
        assert_eq!(attribute.name, "GSTRDISTTOCOG");
        assert_eq!(attribute.source_offset, 6848);
        assert_eq!(attribute.begin_bits, (-1.0_f32).to_bits());
        assert_eq!(attribute.end_bits, (-1.0_f32).to_bits());
        assert_eq!(attribute.payload_words, [0x3f7c5b3a, 0, 0, 0]);
        let TreeMetadata::PhaseBlend(tree) = metadata.tree("b_antic_into_high_str_center").unwrap() else {
            panic!("phase blend")
        };
        assert_eq!(tree.source_offset, 308336);
        assert_eq!(tree.parameter, "DISTTOCOG");
        assert_eq!(tree.children, ["R_ANTIC_CROUCH_OLLIE_N_0_INTO", "R_ANTIC_OLLIE_N_0_INTO"]);
        let TreeMetadata::BlendSpace(tree) = metadata.tree("blend_fs_tweak2").unwrap() else { panic!("blend space") };
        assert_eq!(tree.source_offset, 2214320);
        assert_eq!(tree.parameters, ["TWEAK_X", "TWEAK_Y"]);
        assert_eq!(tree.children.len(), 9);
        assert_eq!(tree.simplexes.len(), 10);
        assert_eq!(tree.simplexes[0].children, [4, 0, 3]);
        assert_eq!(tree.simplexes[0].normal_bits[0], [0x80000000, 0x3f800000]);
        assert_eq!(tree.simplexes[0].scale_bits, [0x3f800000, 0x3fb504f3, 0x3f800000]);
        let TreeMetadata::Selector(tree) = metadata.tree("s_gr_stalegrab_n_1_cyc").unwrap() else { panic!("selector") };
        assert_eq!(tree.parameter, "PROSKATER");
        assert_eq!(tree.default, "GR_STALEGRAB_N_1_CYC");
        assert_eq!(tree.children, ["GR_STALEGRAB_N_1_CYC", "PRO_GONZ_STALEGRAB_CYC"]);
        assert_eq!(tree.values, ["DEFAULT", "GONZO"]);
        let TreeMetadata::SelectionSpace(tree) = metadata.tree("ss_dslideout_bs_r").unwrap() else {
            panic!("selection space")
        };
        assert_eq!(tree.source_offset, 4535744);
        assert_eq!(tree.parameters[0].name, "TWIST");
        assert_eq!(tree.parameters[0].mode, 0);
        assert_eq!(tree.parameters[0].weight_bits, 1.0_f32.to_bits());
        assert_eq!(tree.candidates[1].child, "B_DSLIDE_BS_TWIST_L_EXIT_RT");
        assert_eq!(tree.candidates[1].value_bits, [(-1.0_f32).to_bits()]);
        assert_eq!(metadata.source_for(&tree.name).unwrap(), &metadata.sources()[0]);
    }

    #[test]
    fn metadata_bytes_reject_truncation_counts_and_invalid_records() {
        let bytes = golden();
        for end in 0..bytes.len() {
            assert!(load(&bytes[..end]).is_err(), "accepted prefix {end}");
        }
        let mut trailing = bytes.clone();
        trailing.push(0);
        assert!(load(&trailing).is_err());
        let mut bad_count = bytes.clone();
        bad_count[100..104].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(load(&bad_count).is_err());
        // An attribute kind is a byte, never a silently truncated u32.
        let mut bad_type = bytes.clone();
        let kind_at = bytes.windows(13).position(|w| w == b"GSTRDISTTOCOG").unwrap() + 13;
        bad_type[kind_at..kind_at + 4].copy_from_slice(&256_u32.to_le_bytes());
        assert!(load(&bad_type).is_err());
        let mut bad_header = decode(&bytes).unwrap();
        bad_header.clips[0].fps_bits = f32::NAN.to_bits();
        assert!(AnimationMetadata::from_file(bad_header).is_err());
        let mut bad_simplex = decode(&bytes).unwrap();
        bad_simplex.blend_spaces[0].simplexes[0].children[0] = usize::MAX;
        assert!(AnimationMetadata::from_file(bad_simplex).is_err());
    }

    #[test]
    fn opaque_attribute_words_are_not_float_decoded() {
        let mut bytes = golden();
        let at =
            bytes.windows(16).position(|w| w == [0x3a, 0x5b, 0x7c, 0x3f, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]).unwrap();
        let opaque = [0x7fc01234_u32, 0x80000000, 0xffffffff, 0x01234567];
        for (word, out) in opaque.iter().zip(bytes[at..at + 16].chunks_exact_mut(4)) {
            out.copy_from_slice(&word.to_le_bytes());
        }
        let metadata = load(&bytes).unwrap();
        assert_eq!(metadata.clip("KEEPDEFAULTANIM").unwrap().attributes[0].payload_words, opaque);
    }

    #[test]
    fn latest_source_record_and_unsupported_tree_binding_are_retained() {
        let bytes = golden();
        let mut file = decode(&bytes).unwrap();
        let mut later = file.clips[0].clone();
        later.source_offset += 16;
        later.flags_word = 123;
        file.clips.push(later);
        file.unsupported_trees.push(UnsupportedTree {
            name: "KEEPDEFAULTANIM".into(),
            source_offset: 7000,
            type_id: 42,
        });
        let metadata = AnimationMetadata::from_file(file).unwrap();
        assert_eq!(metadata.clip_count(), 2);
        assert_eq!(metadata.clip("keepdefaultanim").unwrap().flags_word, 123);
        assert!(metadata.tree("keepdefaultanim").err().unwrap().contains("tree type 42"));
        assert_eq!(metadata.source_for("keepdefaultanim").unwrap(), &metadata.sources()[0]);

        // Stock banks have no unsupported trees. Append an explicit unknown kind
        // to the authored fixture to check that the reader preserves it too.
        let mut unknown = bytes;
        let count_at = unknown.len() - 4;
        unknown[count_at..].copy_from_slice(&1_u32.to_le_bytes());
        unknown.extend(15_u32.to_le_bytes());
        unknown.extend(b"KEEPDEFAULTANIM");
        unknown.extend(7000_u64.to_le_bytes());
        unknown.extend(42_u32.to_le_bytes());
        let metadata = load(&unknown).unwrap();
        assert_eq!(metadata.clip("keepdefaultanim").unwrap().source_offset, 1408);
        assert!(metadata.tree("keepdefaultanim").err().unwrap().contains("tree type 42"));
        assert_eq!(metadata.source_for("keepdefaultanim").unwrap(), &metadata.sources()[0]);
    }
}
