//! Production animation command evaluator. File IO and buffer ownership are
//! host services; frame selection, trajectory and pose math live in core.
use crate::core::animation::{
    output::{self, NativeMatrix, Sqt},
    playback_tree::PoseCommand,
    pose_add, pose_blend, pose_mirror,
    pose_sample::{sample_key, select_frames},
    pose_trajectory::{self, LoopTransform},
};
use crate::data::animation_frames::{AnimationFrames, ClipFrames, SampleWords};

pub(crate) struct PoseEvaluator {
    pub frames: AnimationFrames,
}

impl PoseEvaluator {
    pub(crate) fn from_frames(frames: AnimationFrames) -> Self {
        Self { frames }
    }

    /// Executes the ordered stock tree. This uses the native immediate ACS
    /// arithmetic; the host does not recreate packed animation job commands.
    pub fn evaluate(&self, commands: &[PoseCommand]) -> Result<Vec<Sqt>, String> {
        let mut stack: Vec<Vec<Sqt>> = Vec::new();
        for command in commands {
            match command {
                PoseCommand::Pose { name } => {
                    // Init82B97E38 retains these references from the actor's
                    // initial database. AddBindPose82B98118 reuses them even
                    // when a later motion clip comes from another bank.
                    stack.push(self.frames.named_pose(name)?.samples.iter().copied().map(sqt).collect());
                }
                PoseCommand::Add { motion_is_a } => {
                    let other = stack.pop().ok_or("Animation add has no reference subtree")?;
                    let motion = stack.last_mut().ok_or("Animation add has no motion subtree")?;
                    if motion.len() != other.len() {
                        return Err("Animation add bone counts differ".into());
                    }
                    for (motion, other) in motion.iter_mut().zip(other) {
                        *motion = if *motion_is_a {
                            pose_add::add(*motion, other, true)
                        } else {
                            pose_add::add(other, *motion, false)
                        };
                    }
                }
                PoseCommand::Mirror { trajectory_mode } => {
                    let pose = stack.last_mut().ok_or("Animation mirror has no subtree")?;
                    pose_mirror::mirror(pose, &self.frames.parents, &self.frames.mirror_indices, *trajectory_mode)?;
                }
                PoseCommand::Clip { name, time, previous_time, loops } => {
                    let clip = self.frames.clip(name)?;
                    let mut pose = sample_clip(clip, *time)?;
                    if self.frames.has_trajectory {
                        let previous = sample_bone(clip, *previous_time, 0)?;
                        pose[0] = pose_trajectory::delta(
                            pose[0],
                            previous,
                            (*loops != 0).then_some(LoopTransform {
                                rotation: clip.loop_rotation_bits.map(f32::from_bits),
                                translation: clip.loop_translation_bits.map(f32::from_bits),
                            }),
                        );
                    }
                    stack.push(pose);
                }
                PoseCommand::WeightedBlend { weights } => {
                    let start = stack.len().checked_sub(weights.len()).ok_or("Weighted blend pose stack underflow")?;
                    let pose = crate::core::animation::pose_blend::weighted(&stack[start..], weights)
                        .map_err(|e| format!("Weighted blend: {e:?}"))?;
                    stack.truncate(start);
                    stack.push(pose);
                }
                PoseCommand::Blend { weight } | PoseCommand::ChannelBlend { weight, .. } => {
                    let second = stack.pop().ok_or("Animation blend has no second subtree")?;
                    let first = stack.last_mut().ok_or("Animation blend has no first subtree")?;
                    if first.len() != second.len() {
                        return Err("Animation subtree bone counts differ".into());
                    }
                    for (a, b) in first.iter_mut().zip(second) {
                        *a = match command {
                            PoseCommand::ChannelBlend { use_channels_from_weights, .. } => {
                                pose_blend::channel_blend_sample(*a, b, *weight, *use_channels_from_weights)
                            }
                            _ => pose_blend::blend_sample(*a, b, *weight),
                        };
                    }
                }
            }
        }
        if stack.len() != 1 {
            return Err(format!("Animation evaluation left{} poses", stack.len()));
        }
        Ok(stack.pop().unwrap())
    }

    /// TU3828D3800 then828D3B58. NewACS824744B8 initializes the
    /// detached parent to0, so trajectory deltas do not move the local rig.
    pub fn hierarchy(&self, pose: &[Sqt]) -> Result<Vec<NativeMatrix>, String> {
        if pose.len() != self.frames.parents.len() {
            return Err("Animation pose and hierarchy bone counts differ".into());
        }
        let mut globals: Vec<_> = pose.iter().copied().map(output::sqt_to_matrix).collect();
        output::compose_hierarchy_in_place(globals.len() as i32, &self.frames.parents, 0, &mut globals)
            .map_err(|e| format!("Invalid stock animation hierarchy: {e:?}"))?;
        Ok(globals)
    }
}

fn sample_clip(clip: &ClipFrames, time: f32) -> Result<Vec<Sqt>, String> {
    let selection = select_frames(time, f32::from_bits(clip.fps_bits), clip.frame_count(), true, 0.0)?;
    Ok((0..clip.bone_count()).map(|bone| sample_selected(clip, selection, bone)).collect())
}

fn sample_bone(clip: &ClipFrames, time: f32, bone: usize) -> Result<Sqt, String> {
    let selection = select_frames(time, f32::from_bits(clip.fps_bits), clip.frame_count(), true, 0.0)?;
    Ok(sample_selected(clip, selection, bone))
}

fn sample_selected(
    clip: &ClipFrames,
    selection: crate::core::animation::pose_sample::FrameSelection,
    bone: usize,
) -> Sqt {
    // The exported tracks already contain decoded keys. Keep native frame
    // selection and interpolation, not the raw VBR block-boundary substitute.
    let mut sample = sample_key(sqt(clip.key(selection.first, bone)), sqt(clip.key(selection.second, bone)), selection);
    sample.translation[3] = f32::from_bits(clip.channel_weights[bone]);
    sample
}

fn sqt(words: SampleWords) -> Sqt {
    let [sx, sy, sz, x, y, z, w, tx, ty, tz] = words.map(f32::from_bits);
    Sqt { scale: [sx, sy, sz, 1.0], rotation: [x, y, z, w], translation: [tx, ty, tz, 1.0] }
}

#[cfg(test)]
mod compact_tests {
    use super::*;
    use hakuba_skate_schema::{Package, Reader};
    use std::sync::Arc;

    fn bits(s: Sqt) -> ([u32; 4], [u32; 4], [u32; 4]) {
        (s.scale.map(f32::to_bits), s.rotation.map(f32::to_bits), s.translation.map(f32::to_bits))
    }
    // The former dense decoder, kept only as an independent acceptance oracle.
    fn dense(bytes: &[u8]) -> Vec<Vec<SampleWords>> {
        let mut r = Reader::new(bytes, b"ATCLIP01").unwrap();
        r.string().unwrap();
        r.word().unwrap();
        r.wide().unwrap();
        r.word().unwrap();
        r.take(8 * 4).unwrap(); // Loop transform and channel flag.
        let weights = r.word().unwrap() as usize;
        r.take(weights * 4).unwrap();
        let count = r.word().unwrap() as usize;
        let bones = r.word().unwrap() as usize;
        let mut frames = vec![vec![[0; 10]; bones]; count];
        for bone in 0..bones {
            for component in 0..10 {
                let len = r.word().unwrap() as usize;
                let words: Vec<_> = (0..len).map(|_| r.word().unwrap()).collect();
                for (frame, values) in frames.iter_mut().enumerate() {
                    values[bone][component] = words[if len == 1 { 0 } else { frame }];
                }
            }
        }
        r.end().unwrap();
        frames
    }
    fn dense_sample(clip: &ClipFrames, frames: &[Vec<SampleWords>], time: f32) -> Vec<Sqt> {
        let selection = select_frames(time, f32::from_bits(clip.fps_bits), frames.len(), true, 0.).unwrap();
        frames[selection.first]
            .iter()
            .zip(&frames[selection.second])
            .enumerate()
            .map(|(bone, (&first, &second))| {
                let mut sample = sample_key(sqt(first), sqt(second), selection);
                sample.translation[3] = f32::from_bits(clip.channel_weights[bone]);
                sample
            })
            .collect()
    }

    #[test]
    fn prepared_resources_reuse_input_allocation_for_every_clip() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../assets/simulations/skate-simulation/skate-simulation.skatepack");
        let bytes = std::fs::read(path).unwrap();
        let original_allocation = bytes.as_ptr();
        let resources = crate::PreparedResources::from_bytes(bytes).unwrap();
        let retained = resources.clone();
        drop(resources);

        let frames = &retained.0.animation.evaluator.frames;
        let first = frames.clip(frames.clip_names().next().unwrap()).unwrap();
        let archive = first.archive();
        assert_eq!(original_allocation, archive.as_ptr());
        for name in frames.clip_names() {
            let clip = frames.clip(name).unwrap();
            assert!(Arc::ptr_eq(archive, clip.archive()), "{name} copied its archive");
            let _ = clip.key(0, 0);
        }
    }

    #[test]
    fn all_exported_compact_clips_match_dense_keys_sampling_and_trajectory_bits() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../assets/simulations/skate-simulation/skate-simulation.skatepack");
        let resources = crate::PreparedResources::from_bytes(std::fs::read(path).unwrap()).unwrap();
        let frames = &resources.0.animation.evaluator.frames;
        let first = frames.clip(frames.clip_names().next().unwrap()).unwrap();
        let archive = first.archive();
        let package = Package::parse(archive).unwrap();
        let index_before: usize = frames.clip_names().map(|name| frames.clip(name).unwrap().index_bytes()).sum();
        let mut visited = 0;
        let mut dense_bytes = 0;
        for (path, payload) in
            package.entries().filter(|(path, _)| path.starts_with("animation/clips/") && path.ends_with(".skate"))
        {
            let mut header = Reader::new(payload, b"ATCLIP01").unwrap();
            let name = header.string().unwrap();
            let clip = frames.clip(name).unwrap();
            assert!(Arc::ptr_eq(archive, clip.archive()), "{path} copied its archive");
            let dense = dense(payload);
            dense_bytes += dense.len() * clip.bone_count() * std::mem::size_of::<SampleWords>();
            assert_eq!(dense.len(), clip.frame_count(), "{name}");
            for (frame, keys) in dense.iter().enumerate() {
                for (bone, &key) in keys.iter().enumerate() {
                    assert_eq!(key, clip.key(frame, bone), "{name} frame {frame} bone {bone}");
                }
            }
            let fps = f32::from_bits(clip.fps_bits);
            let last = (clip.frame_count() - 1) as f32;
            // First/last/same-key, interior fractional keys and VBR block boundaries.
            for position in [0., 0.25, 1., 7., 7.25, 7.75, 8., last * 0.5, last, last + 1.] {
                let time = position / fps;
                let compact = sample_clip(clip, time).unwrap();
                let old = dense_sample(clip, &dense, time);
                assert_eq!(
                    compact.iter().copied().map(bits).collect::<Vec<_>>(),
                    old.iter().copied().map(bits).collect::<Vec<_>>(),
                    "{name} at {position}"
                );
                let previous_time = (position - 0.5).max(0.) / fps;
                let previous = sample_bone(clip, previous_time, 0).unwrap();
                let old_previous = dense_sample(clip, &dense, previous_time)[0];
                for loops in [false, true] {
                    let transform = loops.then_some(LoopTransform {
                        rotation: clip.loop_rotation_bits.map(f32::from_bits),
                        translation: clip.loop_translation_bits.map(f32::from_bits),
                    });
                    assert_eq!(
                        bits(pose_trajectory::delta(compact[0], previous, transform)),
                        bits(pose_trajectory::delta(old[0], old_previous, transform)),
                        "{name} trajectory at {position}"
                    );
                }
            }
            visited += 1;
        }
        assert_eq!(visited, 3324);
        let index_after: usize = frames.clip_names().map(|name| frames.clip(name).unwrap().index_bytes()).sum();
        assert_eq!(index_before, index_after);
        assert_eq!(index_after, visited * frames.bone_names.len() * std::mem::size_of::<[(usize, usize); 10]>());
        println!(
            "{visited} clips: {} shared archive bytes + {index_after} component-index bytes; {dense_bytes} dense sample bytes never retained",
            archive.len()
        );
    }
}
