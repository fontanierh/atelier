//! Probe only: the playback and arithmetic implementations come from frozen Git.
use skate_core::animation::{clip_clock::AdvanceResult,playback_clip::{PlaybackClip,ClipAttribute,sample_curve},output::{Sqt,attributes::{AnimationAttribute,AttributeName,AttributePayload,MotionGraphAttribute,PacketAttributes}},
    playback_attributes,playback_parameters::{SettableAttribute,SettableAttributes,AttributeSink},channel_playback::{ChannelSettings,ChannelPlayback},playback_tree::selection_space::{Parameter,distance},pose_sample,pose_blend};
use std::{io::{Read,Write},fs,path::Path};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn new(bytes:Vec<u8>)->Self {Self{bytes,at:8}}
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn wide(&mut self)->u64 {u64::from(self.word())|(u64::from(self.word())<<32)}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let s=String::from_utf8(self.bytes[self.at..self.at+n].to_vec()).unwrap();self.at+=n;s}
    fn words(&mut self)->Vec<u32> {let n=self.word();(0..n).map(|_|self.word()).collect()}
    fn name(&mut self)->AttributeName {AttributeName(core::array::from_fn(|_|self.word()))}
    fn attribute(&mut self)->AnimationAttribute {let name=self.name();let kind=self.word() as u8;let status=self.word() as u8;let sequence_id=self.word() as i32;let begin_time=self.float();let end_time=self.float();let payload=AttributePayload(core::array::from_fn(|_|if self.word()!=0 {Some(self.word())} else {None}));AnimationAttribute{name,kind,status,sequence_id,begin_time,end_time,payload}}
    fn attributes(&mut self)->Vec<AnimationAttribute> {let n=self.word();(0..n).map(|_|self.attribute()).collect()}
    fn sqt(&mut self)->Sqt {Sqt{scale:core::array::from_fn(|_|self.float()),rotation:core::array::from_fn(|_|self.float()),translation:core::array::from_fn(|_|self.float())}}
    fn settings(&mut self)->ChannelSettings {ChannelSettings{priority:self.word() as i32,keep_alive:self.word()!=0,mirrored:self.word()!=0,speed:self.float(),blend_in:self.float(),hold_during_blend_in:self.word()!=0,blend_out:self.float(),hold_during_blend_out:self.word()!=0,use_attributes:self.word()!=0}}
}
fn word(out:&mut Vec<u8>,v:u32) {out.extend(v.to_le_bytes());}
fn wide(out:&mut Vec<u8>,v:u64) {out.extend(v.to_le_bytes());}
fn string(out:&mut Vec<u8>,v:&str) {word(out,v.len() as u32);out.extend(v.as_bytes());}
fn attribute(out:&mut Vec<u8>,a:&AnimationAttribute) {for n in a.name.0 {word(out,n);}word(out,u32::from(a.kind));word(out,u32::from(a.status));word(out,a.sequence_id as u32);word(out,a.begin_time.to_bits());word(out,a.end_time.to_bits());for p in a.payload.0 {word(out,u32::from(p.is_some()));if let Some(v)=p {word(out,v);}}}
fn attributes(out:&mut Vec<u8>,a:&[AnimationAttribute]) {word(out,a.len() as u32);for a in a {attribute(out,a);}}
fn sqt(out:&mut Vec<u8>,s:Sqt) {for v in s.scale.into_iter().chain(s.rotation).chain(s.translation) {word(out,v.to_bits());}}
fn settings(out:&mut Vec<u8>,s:ChannelSettings) {word(out,s.priority as u32);word(out,u32::from(s.keep_alive));word(out,u32::from(s.mirrored));word(out,s.speed.to_bits());word(out,s.blend_in.to_bits());word(out,u32::from(s.hold_during_blend_in));word(out,s.blend_out.to_bits());word(out,u32::from(s.hold_during_blend_out));word(out,u32::from(s.use_attributes));}
fn status(out:&mut Vec<u8>,r:Result<(),String>) {match r {Ok(())=>word(out,1),Err(e)=>{word(out,0);string(out,&e);}}}
fn frame(out:&mut Vec<u8>,r:Result<pose_sample::FrameSelection,&str>) {match r {Ok(s)=>{word(out,1);wide(out,s.first as u64);wide(out,s.second as u64);word(out,s.coefficient.to_bits());},Err(e)=>{word(out,0);string(out,e);}}}
fn clip(input:&mut Input)->PlaybackClip {
    let frames=input.float();let fps=input.float();let base=input.float();let flags=input.word();let n=input.word();let mut attrs=Vec::new();
    for _ in 0..n {let name=input.name();let kind=input.word() as u8;let begin=input.float();let end=input.float();let payload=input.words();attrs.push(ClipAttribute{name,kind,begin,end,payload});}
    let mut c=PlaybackClip::new(frames,fps,base,flags,attrs);c.clock.time=input.float();c.clock.previous_time=input.float();c.clock.loops_since_evaluation=input.word();c
}
fn dump_clock(out:&mut Vec<u8>,c:&PlaybackClip,r:AdvanceResult) {
    for v in [c.clock.time,c.clock.previous_time,c.clock.length,c.clock.speed,c.clock.sample_time()] {word(out,v.to_bits());}word(out,c.clock.loops_since_evaluation);
    word(out,u32::from(r.crossed_end));word(out,r.overshoot.to_bits());word(out,r.remaining_before_wrap.to_bits());
    for (b,e) in [(-1.,-1.),(0.,0.),(0.,1.),(0.25,0.75),(1.,1.),(1.,0.),(-0.0,0.5)] {word(out,u32::from(c.clock.attribute_status(b,e)));}
}
fn sample_words(input:&mut Input)->Sqt {let w:[f32;10]=core::array::from_fn(|_|input.float());Sqt{scale:[w[0],w[1],w[2],1.],rotation:[w[3],w[4],w[5],w[6]],translation:[w[7],w[8],w[9],1.]}}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input::new(bytes);let cases=input.word();let mut out=Vec::new();
    for _ in 0..cases {match input.word() {
        1=>{let mut c=clip(&mut input);let n=input.word();for _ in 0..n {let mut r=AdvanceResult{crossed_end:input.word()!=0,overshoot:input.float(),remaining_before_wrap:input.float()};match input.word() {0=>{let dt=input.float();let phase=input.float();c.clock.advance(dt,phase,&mut r);},1=>c.clock.set_speed(input.float()),2=>c.clock.set_time(input.float()),3=>c.clock.commit_evaluation(),_=>unreachable!()}dump_clock(&mut out,&c,r);}},
        2=>{let words=input.words();let n=input.word();for _ in 0..n {match sample_curve(&words,input.float()) {Ok(v)=>{word(&mut out,1);word(&mut out,v.to_bits());},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}}},
        3=>{let c=clip(&mut input);let n=input.word();for _ in 0..n {let mask=input.word();let name=input.name();match c.attributes(mask) {Ok(a)=>{word(&mut out,1);attributes(&mut out,&a);},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}
            match c.attribute(name,mask) {Ok(Some(a))=>{word(&mut out,1);attribute(&mut out,&a);},Ok(None)=>word(&mut out,2),Err(e)=>{word(&mut out,0);string(&mut out,&e);}}}},
        4=>{let op=input.word();let mut a=input.attribute();let b=input.attribute();let weight=input.float();let n=input.word();let names=(0..n).map(|_|(input.name(),input.name())).collect();let result=match op {0=>playback_attributes::blend(&mut a,&b,weight),1=>playback_attributes::scale(&mut a,weight),2=>playback_attributes::add_weighted(&mut a,&b,weight),3=>{a.copy_from(&b);Ok(())},4=>playback_attributes::AttributeMirror(names).apply(&mut a),_=>unreachable!()};status(&mut out,result);attribute(&mut out,&a);},
        5=>{let s=input.settings();let mut c=ChannelPlayback::new(s);let n=input.word();for _ in 0..n {let mut advances=false;match input.word() {0=>{let dt=input.float();let length=input.float();let time=input.float();c.influence=input.float();advances=c.advance(dt,length,time);},1=>c.end(),2=>{let seconds=input.float();let hold=input.word()!=0;c.end_with(seconds,hold);},3=>{let settings=input.settings();let resurrect=input.word()!=0;c.transition(settings,resurrect);},4=>c.did_advance(AdvanceResult{crossed_end:input.word()!=0,overshoot:0.,remaining_before_wrap:0.}),_=>unreachable!()}
            word(&mut out,u32::from(advances));word(&mut out,c.weight.to_bits());word(&mut out,c.influence.to_bits());word(&mut out,u32::from(c.expired()));word(&mut out,u32::from(c.can_transition(false)));word(&mut out,u32::from(c.can_transition(true)));settings(&mut out,c.settings);}
            let a=input.attributes();let b=input.attributes();attributes(&mut out,&c.merge_attributes(a,&b));},
        6=>{let n=input.word();let mut ps=Vec::new();let mut vs=Vec::new();let mut cs=Vec::new();for _ in 0..n {ps.push(Parameter{name:AttributeName([0;5]),mode:input.word(),weight:input.float(),minimum:input.float(),maximum:input.float()});vs.push(input.float());cs.push(input.float());}word(&mut out,distance(&ps,&vs,&cs).to_bits());},
        7=>{let time=input.float();let fps=input.float();let frames=input.wide() as usize;let blend=input.word()!=0;let offset=input.float();frame(&mut out,pose_sample::select_frames(time,fps,frames,blend,offset));},
        8=>{let op=input.word();let weight=input.float();let first_weights=input.word()!=0;let n=input.word();let mut poses=Vec::new();let mut weights=Vec::new();for _ in 0..n {weights.push(input.float());let bones=input.word();poses.push((0..bones).map(|_|input.sqt()).collect::<Vec<_>>());}
            if op==2 {match pose_blend::weighted(&poses,&weights) {Ok(p)=>{word(&mut out,1);word(&mut out,p.len() as u32);for s in p {sqt(&mut out,s);}},Err(e)=>{word(&mut out,0);string(&mut out,&format!("{e:?}"));}}}
            else {word(&mut out,1);word(&mut out,1);sqt(&mut out,if op==0 {pose_blend::blend_sample(poses[0][0],poses[1][0],weight)} else {pose_blend::channel_blend_sample(poses[0][0],poses[1][0],weight,first_weights)});}},
        9=>{let mut packet=PacketAttributes::default();let n=input.word();for _ in 0..n {match input.word() {0=>packet.clear(),1=>packet.append(&input.attribute()),2=>{let m=input.word();let motion=(0..m).map(|_|MotionGraphAttribute{name:input.name(),value:input.float()}).collect::<Vec<_>>();let tree=input.attributes();packet.replace_from(&motion,&tree);},_=>unreachable!()}attributes(&mut out,packet.entries());}},
        10=>{let name=input.string();let mut raw=Input::new(fs::read(Path::new(&args[1]).join("clips").join(format!("{name}.raw"))).map_err(|e|e.to_string())?);
            let _name=raw.string();let _bank=raw.word();let _offset=raw.wide();let fps=raw.float();for _ in 0..7 {raw.word();}let _channel=raw.word();let weights=raw.words();let frames=raw.word() as usize;let bones=raw.word();
            let samples=(0..frames).map(|_|(0..bones).map(|_|sample_words(&mut raw)).collect::<Vec<_>>()).collect::<Vec<_>>();let n=input.word();for _ in 0..n {
                match pose_sample::select_frames(input.float(),fps,frames,true,0.) {Ok(selection)=>{word(&mut out,1);word(&mut out,bones);for b in 0..bones as usize {let mut sample=pose_sample::sample_key(samples[selection.first][b],samples[selection.second][b],selection);sample.translation[3]=f32::from_bits(weights[b]);sqt(&mut out,sample);}},Err(e)=>{word(&mut out,0);string(&mut out,e);}}
            }},
        11=>{let left=input.attributes();let right=input.attributes();let weight=input.float();match playback_attributes::intersection(left,&right,weight) {Ok(a)=>{word(&mut out,1);attributes(&mut out,&a);},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}},
        12=>{let mut entries=SettableAttributes::default();let n=input.word();for _ in 0..n {if input.word()==0 {entries.clear();} else {entries.set_attribute(SettableAttribute{name:input.name(),value:input.float(),normalized:input.word()!=0,sequence_id:input.word() as i32});}word(&mut out,entries.entries().len() as u32);for e in entries.entries() {for w in e.name.0 {word(&mut out,w);}word(&mut out,e.value.to_bits());word(&mut out,u32::from(e.normalized));word(&mut out,e.sequence_id as u32);}}},
        13=>{let mut c=clip(&mut input);c.clock.length=input.float();let mut r=AdvanceResult{crossed_end:input.word()!=0,overshoot:input.float(),remaining_before_wrap:input.float()};let dt=input.float();let phase=input.float();let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||c.clock.advance(dt,phase,&mut r)));
            match result {Ok(())=>word(&mut out,1),Err(e)=>{word(&mut out,0);let message=e.downcast_ref::<String>().map(String::as_str).or_else(||e.downcast_ref::<&str>().copied()).unwrap_or("unknown panic");string(&mut out,message);}}dump_clock(&mut out,&c,r);},
        _=>unreachable!(),
    }}
    if input.at!=input.bytes.len() {return Err("Trailing playback probe input".into());}std::io::stdout().write_all(&out).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
