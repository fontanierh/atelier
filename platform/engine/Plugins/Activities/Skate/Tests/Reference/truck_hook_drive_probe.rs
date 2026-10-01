//! Public original truck caches/drive order, active normalization and live hook setters/state.
use std::io::{Read,Write};
use math::{Vector3,Basis3};
use physics::{drive_frames::{RetailAffineTransform,RetailDriveFrames},truck_frames::{steering_truck_transforms,steering_drive_frames},
    drive_preparation::{normalize_drive_frames,normalize_active_drive_frames},hook_drive::{HookDriveState,set_child_angular_frame,set_parent_angular_frame}};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
    fn transform(&mut self)->RetailAffineTransform {RetailAffineTransform{basis:Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.scalar()))},translation:Vector3::new(self.scalar(),self.scalar(),self.scalar())}}
}
fn transform(out:&mut Vec<u32>,v:RetailAffineTransform) {for c in v.basis.columns {out.extend(c.map(f32::to_bits));}out.extend([v.translation.x.to_bits(),v.translation.y.to_bits(),v.translation.z.to_bits()]);}
fn frames(out:&mut Vec<u32>,v:RetailDriveFrames) {for f in [v.body_a,v.body_b] {let q=f.orientation;let t=f.translation;out.extend([q.x,q.y,q.z,q.w,t.x,t.y,t.z,0.].map(f32::to_bits));}}
fn state(out:&mut Vec<u32>,v:&HookDriveState,animated:u8) {
    out.extend(v.frames);out.extend(v.dynamics);out.push(animated as u32);let d=v.solver_dynamics();
    for p in [d.linear,d.angular] {out.extend([p.spring_or_max_velocity.to_bits(),p.damping.to_bits(),p.max_strength.to_bits(),p.drive_type as u32]);}
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let count=reader.word();let mut result=Vec::new();
    for index in 0..count {
        let op=reader.word();let mut out=Vec::new();
        match op {
            0=>{let base=[reader.transform(),reader.transform()];let targets=[reader.scalar(),reader.scalar()];for t in steering_truck_transforms(base,targets){transform(&mut out,t);}for f in steering_drive_frames(base,targets){frames(&mut out,f);}},
            1=>{let mut f=reader.words();normalize_drive_frames(&mut f);out.extend(f);},
            2=>{let n=reader.word();let mut f:Vec<[u32;16]>=(0..n).map(|_|reader.words()).collect();let k=reader.word();let active:Vec<_>=(0..k).map(|_|{let id=reader.word();(id!=u32::MAX).then_some(id as usize)}).collect();normalize_active_drive_frames(&mut f,&active);for row in f{out.extend(row);}},
            3=>{let mut f=reader.words();let b=reader.words();if reader.word()!=0{set_parent_angular_frame(&mut f,b);}else{set_child_angular_frame(&mut f,b);}out.extend(f);},
            4=>{
                let mut v=HookDriveState{frames:reader.words(),dynamics:reader.words()};let mut animated=reader.word() as u8;let n=reader.word();out.push(n);state(&mut out,&v,animated);
                for _ in 0..n {
                    match reader.word() {
                        0=>v=HookDriveState::initial(),1=>v.enable_animation_soft(&mut animated),2=>v.enable_angular_soft(),3=>v.enable_angular_only(&mut animated),4=>v.disable_animation(&mut animated),5=>v.disable_linear(),6=>v.disable_angular(),
                        7=>set_child_angular_frame(&mut v.frames,reader.words()),8=>set_parent_angular_frame(&mut v.frames,reader.words()),9=>normalize_drive_frames(&mut v.frames),_=>panic!("Invalid hook command"),
                    }
                    state(&mut out,&v,animated);
                }
            },
            _=>panic!("Invalid drive lifecycle operation"),
        }
        result.extend([index,op,out.len() as u32]);result.extend(out);
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&result.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
