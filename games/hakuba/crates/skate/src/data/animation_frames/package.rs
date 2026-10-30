//! Index compact component tracks into the one retained, validated project archive.
use super::*;
use hakuba_skate_schema::{Package, Reader};

pub(super) struct ProjectFrames {
    clips: BTreeMap<String, ClipFrames>,
    poses: BTreeMap<(usize, u64), ReferencePose>,
}
fn error(s: &str) -> hakuba_skate_schema::Error {
    hakuba_skate_schema::Error(s.into())
}
fn words(r: &mut Reader<'_>, n: usize) -> Result<Vec<u32>, hakuba_skate_schema::Error> {
    if n > r.remaining() / 4 {
        return Err(error("Animation word count exceeds bytes"));
    }
    (0..n).map(|_| r.word()).collect()
}
impl AnimationFrames {
    pub(crate) fn from_package(
        package: &Package<'_>,
        archive: Arc<Vec<u8>>,
        metadata: &AnimationMetadata,
    ) -> Result<Self, String> {
        fn decode(
            package: &Package<'_>,
            archive: Arc<Vec<u8>>,
            metadata: &AnimationMetadata,
        ) -> Result<AnimationFrames, hakuba_skate_schema::Error> {
            let mut r = Reader::new(package.get("animation/rig.skate")?, b"ATSKEL01")?;
            let n = r.word()? as usize;
            let trajectory = r.word()?;
            if n == 0 || n > 255 || trajectory > 1 {
                return Err(error("Invalid rig bone count/trajectory"));
            }
            let (mut bone_names, mut parents, mut mirrors) = (Vec::new(), Vec::new(), Vec::new());
            for i in 0..n {
                bone_names.push(r.string()?.to_owned());
                let p = r.int()?;
                let m = r.int()?;
                if p < -1 || p >= i as i32 || m < -1 || m >= n as i32 {
                    return Err(error("Invalid rig parent/mirror"));
                }
                parents.push(p);
                mirrors.push(m);
            }
            let mut names = std::collections::BTreeSet::new();
            for (i, name) in bone_names.iter().enumerate() {
                let m = mirrors[i];
                if name.is_empty() || !names.insert(name) || (m >= 0 && mirrors[m as usize] != i as i32) {
                    return Err(error("Invalid rig name/mirror mapping"));
                }
            }
            let mut poses = BTreeMap::new();
            for _ in 0..r.word()? {
                let bank = r.word()? as usize;
                let name = r.string()?.to_owned();
                let source_offset = r.wide()?;
                if r.word()? as usize != n {
                    return Err(error("Rig reference bone count differs"));
                }
                let mut samples = Vec::new();
                for _ in 0..n {
                    samples.push(words(&mut r, 10)?.try_into().unwrap());
                }
                validate_samples(&samples, n).map_err(|s| error(&s))?;
                if poses.insert((bank, source_offset), ReferencePose { name, source_offset, samples }).is_some() {
                    return Err(error("Duplicate rig pose"));
                }
            }
            r.end()?;
            let mut clips = BTreeMap::new();
            for (path, bytes) in
                package.entries().filter(|(p, _)| p.starts_with("animation/clips/") && p.ends_with(".skate"))
            {
                let archive_start = package.range(path)?.start;
                let mut r = Reader::new(bytes, b"ATCLIP01")?;
                let name = r.string()?.to_owned();
                let bank = r.word()? as usize;
                let source_offset = r.wide()?;
                let fps_bits = r.word()?;
                let loop_translation_bits: [u32; 3] = words(&mut r, 3)?.try_into().unwrap();
                let loop_rotation_bits: [u32; 4] = words(&mut r, 4)?.try_into().unwrap();
                let channel = r.word()?;
                if channel > 1 {
                    return Err(error("Invalid channel animation flag"));
                }
                let weights = r.word()? as usize;
                if weights != n {
                    return Err(error("Clip weight count differs"));
                }
                let channel_weights = words(&mut r, n)?;
                let count = r.word()? as usize;
                let bones = r.word()? as usize;
                if count == 0 || bones != n {
                    return Err(error("Clip dimensions differ"));
                }
                let source = metadata.clip(&name).map_err(|s| error(&s))?;
                if source.source_offset != source_offset
                    || source.fps_bits != fps_bits
                    || f32::from_bits(source.frames_bits) != count as f32
                    || (source.flags_word & (1 << 29) != 0) != (channel != 0)
                {
                    return Err(error("Clip metadata differs"));
                }
                if channel_weights
                    .iter()
                    .chain(loop_translation_bits.iter())
                    .chain(loop_rotation_bits.iter())
                    .any(|w| !f32::from_bits(*w).is_finite())
                {
                    return Err(error("Nonfinite clip header/weights"));
                }
                let mut tracks = Vec::with_capacity(n);
                for _ in 0..n {
                    let mut bone = [(0, 0); 10];
                    for component in &mut bone {
                        let len = r.word()? as usize;
                        if len != 1 && len != count {
                            return Err(error("Invalid clip component track length"));
                        }
                        let start = r.position();
                        let data = r.take(len.checked_mul(4).ok_or_else(|| error("Animation track size overflow"))?)?;
                        if data
                            .chunks_exact(4)
                            .any(|w| !f32::from_bits(u32::from_le_bytes(w.try_into().unwrap())).is_finite())
                        {
                            return Err(error("Nonfinite clip component"));
                        }
                        *component = (archive_start + start, len);
                    }
                    tracks.push(bone);
                }
                r.end()?;
                let clip = ClipFrames {
                    name: name.clone(),
                    source_offset,
                    fps_bits,
                    loop_translation_bits,
                    loop_rotation_bits,
                    channel_animation: channel != 0,
                    channel_weights,
                    bank,
                    archive: Arc::clone(&archive),
                    tracks,
                    frame_count: count,
                };
                if bank > 1
                    || !path.starts_with(&format!("animation/clips/{bank}/"))
                    || metadata.source_for(&name).map(|s| &s.source_sha256)
                        != metadata.sources().get(bank).map(|s| &s.source_sha256)
                    || clips.insert(name, clip).is_some()
                {
                    return Err(error("Ambiguous clip identity"));
                }
            }
            if clips.len() != metadata.clip_count() {
                return Err(error("Animation sample and metadata clip counts differ"));
            }
            Ok(AnimationFrames {
                source_sha256: metadata.source_sha256.clone(),
                parents,
                bone_names,
                mirror_indices: mirrors,
                has_trajectory: trajectory != 0,
                project: ProjectFrames { clips, poses },
            })
        }
        decode(package, archive, metadata).map_err(|e| e.to_string())
    }
}
impl ProjectFrames {
    pub(super) fn clip(&self, name: &str) -> Result<&ClipFrames, String> {
        self.clips.get(&name.to_ascii_uppercase()).ok_or_else(|| format!("Missing animation clip {name}"))
    }
    pub(super) fn reference_pose(&self, bank: usize, offset: u64) -> Result<&ReferencePose, String> {
        self.poses.get(&(bank, offset)).ok_or_else(|| format!("Missing reference pose {bank}:{offset}"))
    }
    pub(super) fn named_pose(&self, bank: usize, name: &str) -> Result<&ReferencePose, String> {
        self.poses
            .iter()
            .rev()
            .find(|((b, _), p)| *b == bank && p.name.eq_ignore_ascii_case(name))
            .map(|(_, p)| p)
            .ok_or_else(|| format!("Missing reference pose {name} in bank {bank}"))
    }
    pub(super) fn clip_count(&self) -> usize {
        self.clips.len()
    }
    pub(super) fn clip_names(&self) -> impl Iterator<Item = &str> {
        self.clips.keys().map(String::as_str)
    }
    pub(super) fn clip_bank(&self, name: &str) -> Result<usize, String> {
        self.clips.get(&name.to_ascii_uppercase()).map(|c| c.bank).ok_or_else(|| format!("Missing clip bank {name}"))
    }
}
