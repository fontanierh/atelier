//! Optional authored clips, separate from the SHA-bound stock animation banks.
use bevy::prelude::*;

pub(super) struct Clip {
    pub fps: f32,
    pub names: Vec<String>,
    pub parents: Vec<i32>,
    pub frames: Vec<Vec<[f32; 10]>>,
}

pub(super) struct Clips {
    pub reach: Clip,
    pub mantle: Clip,
}
impl Clips {
    pub fn load(_resources: &crate::resources::Resources) -> Result<Option<Self>, String> {
        Ok(None)
    }
}
impl Clip {
    pub fn duration(&self) -> f32 {
        (self.frames.len() - 1) as f32 / self.fps
    }
    pub fn sample(&self, time: f32) -> Vec<Transform> {
        let frame = (time * self.fps).clamp(0., (self.frames.len() - 1) as f32);
        let i = frame.floor() as usize;
        let j = (i + 1).min(self.frames.len() - 1);
        self.frames[i].iter().zip(&self.frames[j]).map(|(a, b)| blend(decode(a), decode(b), frame.fract())).collect()
    }
    pub fn globals(&self, locals: &[Transform]) -> Vec<Mat4> {
        let mut result = Vec::with_capacity(locals.len());
        for (i, t) in locals.iter().enumerate() {
            let m = t.to_matrix();
            result.push(if self.parents[i] < 0 { m } else { result[self.parents[i] as usize] * m });
        }
        result
    }
    pub fn index(&self, name: &str) -> usize {
        self.names.iter().position(|n| n == name).unwrap()
    }
    pub fn hands(&self, globals: &[Mat4]) -> Vec3 {
        (globals[self.index("LEFTHAND")].w_axis.truncate() + globals[self.index("RIGHTHAND")].w_axis.truncate()) * 0.5
    }
    pub fn feet(&self, globals: &[Mat4]) -> Vec3 {
        (globals[self.index("LEFTFOOT")].w_axis.truncate() + globals[self.index("RIGHTFOOT")].w_axis.truncate()) * 0.5
            - Vec3::Y * 0.11
    }
}
fn decode(s: &[f32; 10]) -> Transform {
    Transform {
        scale: Vec3::new(s[0], s[1], s[2]),
        rotation: Quat::from_xyzw(s[3], s[4], s[5], s[6]).normalize(),
        translation: Vec3::new(s[7], s[8], s[9]),
    }
}
pub(super) fn blend(a: Transform, b: Transform, t: f32) -> Transform {
    Transform {
        translation: a.translation.lerp(b.translation, t),
        rotation: a.rotation.slerp(b.rotation, t),
        scale: a.scale.lerp(b.scale, t),
    }
}
