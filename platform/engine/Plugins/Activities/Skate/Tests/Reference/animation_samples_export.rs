//! One-time sample export through the original bank/pose decoder.
use skate_data::{animation_banks::AnimationBanks,animation_frames::{AnimationFrames,ClipFrames},abin::RecordData};
use std::{io::{Write,BufWriter},path::Path,fs::{self,File},sync::Arc};
fn word(out:&mut impl Write,value:u32) {out.write_all(&value.to_le_bytes()).unwrap();}
fn wide(out:&mut impl Write,value:u64) {out.write_all(&value.to_le_bytes()).unwrap();}
fn string(out:&mut impl Write,value:&str) {word(out,value.len() as u32);out.write_all(value.as_bytes()).unwrap();}
fn clip(out:&mut impl Write,bank:usize,clip:&ClipFrames) {
    out.write_all(b"ATCLRAW1").unwrap();string(out,&clip.name);word(out,bank as u32);wide(out,clip.source_offset);word(out,clip.fps_bits);
    for value in clip.loop_translation_bits {word(out,value);}
    for value in clip.loop_rotation_bits {word(out,value);}
    word(out,u32::from(clip.channel_animation));word(out,clip.channel_weights.len() as u32);
    for &value in &clip.channel_weights {word(out,value);}
    word(out,clip.frames.len() as u32);word(out,clip.channel_weights.len() as u32);
    for frame in &clip.frames {for sample in frame {for &value in sample {word(out,value);}}}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();
    let root=Path::new(&args[1]);let output=Path::new(&args[2]);fs::create_dir_all(output).map_err(|e|e.to_string())?;
    let banks=AnimationBanks::load(root)?;
    let h=banks.banks[0].hierarchy().ok_or("Missing animation hierarchy")?;
    let mut rig=BufWriter::new(File::create(output.join("rig.raw")).map_err(|e|e.to_string())?);
    rig.write_all(b"ATSKEL01").unwrap();word(&mut rig,h.parents.len() as u32);word(&mut rig,u32::from(h.has_trajectory));
    for i in 0..h.parents.len() {string(&mut rig,&h.bone_names[i]);word(&mut rig,h.parents[i] as u32);word(&mut rig,h.mirrors[i] as u32);}
    let pose_count=banks.banks.iter().flat_map(|bank|bank.records()).filter(|r|matches!(r.data,RecordData::Pose(_))).count();
    word(&mut rig,pose_count as u32);
    let mut names=BufWriter::new(File::create(output.join("clips.txt")).map_err(|e|e.to_string())?);
    let mut counts=Vec::new();
    for (bank_id,bank) in banks.banks.iter().enumerate() {
        // A single-bank view exposes every pose record, including overwritten names.
        let single=AnimationBanks{banks:vec![Arc::clone(bank)],identities:vec![banks.identities[bank_id].clone()]};
        let frames=AnimationFrames::from_banks(&single)?;
        let directory=output.join(format!("clips/{bank_id}"));fs::create_dir_all(&directory).map_err(|e|e.to_string())?;
        let mut samples=0usize;let mut clips=0usize;
        for name in frames.clip_names() {
            let value=frames.clip(name)?;
            let mut file=BufWriter::new(File::create(directory.join(format!("{name}.raw"))).map_err(|e|e.to_string())?);
            clip(&mut file,bank_id,value);file.flush().map_err(|e|e.to_string())?;
            writeln!(names,"{bank_id}/{name}").unwrap();
            clips+=1;samples+=value.frames.len()*value.channel_weights.len();
        }
        for record in bank.records() {
            if !matches!(record.data,RecordData::Pose(_)) {continue;}
            let pose=frames.reference_pose(record.header.offset as u64)?;
            word(&mut rig,bank_id as u32);string(&mut rig,&pose.name);wide(&mut rig,pose.source_offset);word(&mut rig,pose.samples.len() as u32);
            for sample in &pose.samples {for &value in sample {word(&mut rig,value);}}
        }
        counts.push(serde_json::json!({"bank":bank_id,"clips":clips,"bone_samples":samples,"source_sha256":banks.identities[bank_id]}));
    }
    rig.flush().map_err(|e|e.to_string())?;names.flush().map_err(|e|e.to_string())?;
    let report=serde_json::json!({"bones":h.parents.len(),"poses":pose_count,"banks":counts});
    fs::write(output.join("export.json"),serde_json::to_vec_pretty(&report).unwrap()).map_err(|e|e.to_string())?;
    println!("{report}");Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(1);}}
