//! Probe host only. The check script appends exact frozen host bodies and their
//! hashes; core playback types and all original modules remain unmodified.
#![allow(dead_code,unused_imports)]
use skate_core::animation::{clip_clock::AdvanceResult,output::attributes::{AnimationAttribute,AttributeName,MotionGraphAttribute},playback::{PlaybackService,PlaybackRequest,TransitionSettings},playback_clip::{PlaybackClip,ClipAttribute},phase_blend::PhaseBlend,
    playback_tree::{PlaybackTree,PoseCommand,Evaluation,blend_space::{BlendSpace,Simplex},selection_space::{SelectionSpace,Parameter,Candidate}},playback_transition::PlaybackTransition,posture::{PendingPosture,PosturePose},
    playback_parameters::{ParameterInputs,AttributeSink,SettableAttribute,SettableAttributes},skeleton_input::name::encode};
use skate_data::animation_metadata::{AnimationMetadata,TreeMetadata};
use std::{io::{Read,Write},fs,path::Path,sync::Arc};
#[path="../../crates/skate-host/src/graph_host/motion_animation/tree_builder.rs"] mod original_builder;
#[path="../../crates/skate-host/src/graph_host/motion_animation/selection_space_host.rs"] mod original_selection;
use original_builder::build;
struct MotionAnimation {
    metadata:AnimationMetadata,current:Option<PlaybackTree>,current_name:Option<String>,construction_values:Vec<(AttributeName,AttributeName)>,posture:PendingPosture,posture_bank_valid:bool,
    skater_animation_flags:Option<u32>,attribute_mirror:Arc<skate_core::animation::playback_attributes::AttributeMirror>,channels:motion_channels::MotionChannels,settable:SettableAttributes,tree_attributes:Vec<AnimationAttribute>,property:AdvanceResult,
}
impl MotionAnimation {
    fn new(metadata:AnimationMetadata)->Self {Self{metadata,current:None,current_name:None,construction_values:Vec::new(),posture:PendingPosture::default(),posture_bank_valid:false,skater_animation_flags:None,
        attribute_mirror:Arc::new(skate_core::animation::playback_attributes::AttributeMirror(Vec::new())),channels:motion_channels::MotionChannels::default(),settable:SettableAttributes::default(),tree_attributes:Vec::new(),property:AdvanceResult{crossed_end:false,overshoot:-1.,remaining_before_wrap:-1.}}}
}
impl ParameterInputs for MotionAnimation {
    fn motion_intent(&self,_:&str)->Option<f32> {panic!("unused MotionIntent dependency invoked by tree probe")}
    fn filtered_intent(&self,_:&str)->Option<f32> {panic!("unused FilteredIntent dependency invoked by tree probe")}
    fn last_attribute(&mut self,_:AttributeName)->Result<Option<AnimationAttribute>,String> {panic!("unused LastAttribute dependency invoked by tree probe")}
}
impl AttributeSink for MotionAnimation {fn set_attribute(&mut self,a:SettableAttribute) {self.settable.set_attribute(a);}}
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let s=String::from_utf8(self.bytes[self.at..self.at+n].to_vec()).unwrap();self.at+=n;s}
    fn name(&mut self)->AttributeName {AttributeName(core::array::from_fn(|_|self.word()))}
    fn attribute(&mut self)->AnimationAttribute {let name=self.name();let kind=self.word() as u8;let status=self.word() as u8;let sequence_id=self.word() as i32;let begin_time=self.float();let end_time=self.float();let payload=skate_core::animation::output::attributes::AttributePayload(core::array::from_fn(|_|if self.word()!=0 {Some(self.word())} else {None}));AnimationAttribute{name,kind,status,sequence_id,begin_time,end_time,payload}}
    fn settable(&mut self)->Vec<SettableAttribute> {let n=self.word();(0..n).map(|_|SettableAttribute{name:self.name(),value:self.float(),normalized:self.word()!=0,sequence_id:self.word() as i32}).collect()}
    fn floats(&mut self)->Vec<f32> {let n=self.word();(0..n).map(|_|self.float()).collect()}
    fn matrix(&mut self)->Vec<Vec<f32>> {let n=self.word();(0..n).map(|_|self.floats()).collect()}
    fn transition(&mut self)->TransitionSettings {TransitionSettings{kind:self.word(),seconds:self.float(),under:self.word(),matching:self.word(),use_channels_from_weights:self.word()!=0}}
    fn mirror(&mut self)->Arc<skate_core::animation::playback_attributes::AttributeMirror> {let n=self.word();Arc::new(skate_core::animation::playback_attributes::AttributeMirror((0..n).map(|_|(self.name(),self.name())).collect()))}
    fn construction(&mut self)->Vec<(AttributeName,AttributeName)> {let n=self.word();(0..n).map(|_|(self.name(),self.name())).collect()}
    fn children(&mut self)->Result<Vec<PlaybackTree>,String> {let n=self.word();(0..n).map(|_|self.tree()).collect()}
    fn tree(&mut self)->Result<PlaybackTree,String> {match self.word() {
        0=>{let name=self.string();let frames=self.float();let fps=self.float();let base=self.float();let flags=self.word();let n=self.word();let attrs=(0..n).map(|_|{let name=self.name();let kind=self.word() as u8;let begin=self.float();let end=self.float();let n=self.word();let payload=(0..n).map(|_|self.word()).collect();ClipAttribute{name,kind,begin,end,payload}}).collect();
            let mut clip=PlaybackClip::new(frames,fps,base,flags,attrs);clip.clock.time=self.float();clip.clock.previous_time=self.float();clip.clock.loops_since_evaluation=self.word();Ok(PlaybackTree::Clip{name,clip})},
        1=>{let parameter=self.name();let children=self.children()?;Ok(PlaybackTree::PhaseBlend(PhaseBlend::new(parameter,children)?))},
        2=>{let n=self.word();let params=(0..n).map(|_|self.name()).collect();let children=self.children()?;let n=self.word();let simplexes=(0..n).map(|_|{let n=self.word();let children=(0..n).map(|_|self.word() as usize).collect();let vertices=self.matrix();let normals=self.matrix();let scales=self.floats();Simplex{children,vertices,normals,scales}}).collect();Ok(PlaybackTree::BlendSpace(BlendSpace::new(params,children,simplexes)?))},
        3=>{let n=self.word();let parameters=(0..n).map(|_|Parameter{name:self.name(),mode:self.word(),weight:self.float(),minimum:self.float(),maximum:self.float()}).collect();let n=self.word();let candidates=(0..n).map(|_|{let name=self.string();let values=self.floats();let tree=self.tree()?;Ok(Candidate{name,values,tree})}).collect::<Result<_,String>>()?;Ok(PlaybackTree::SelectionSpace(SelectionSpace::new(parameters,candidates)?))},
        4=>{let from=self.tree()?;let to=self.tree()?;let settings=self.transition();Ok(PlaybackTree::Transition(PlaybackTransition::new(from,to,settings)))},
        5=>{let motion=Box::new(self.tree()?);let posture=PosturePose::from_profile(self.word());let board_backwards=self.word()!=0;let n=self.word();let mirror_modes=(0..n).map(|_|self.word()).collect();let attribute_mirror=self.mirror();Ok(PlaybackTree::BindPose{motion,posture,board_backwards,mirror_modes,attribute_mirror})},
        _=>unreachable!(),
    }}
}
fn word(out:&mut Vec<u8>,v:u32) {out.extend(v.to_le_bytes());}
fn string(out:&mut Vec<u8>,v:&str) {word(out,v.len() as u32);out.extend(v.as_bytes());}
fn attribute(out:&mut Vec<u8>,a:&AnimationAttribute) {for v in a.name.0 {word(out,v);}word(out,u32::from(a.kind));word(out,u32::from(a.status));word(out,a.sequence_id as u32);word(out,a.begin_time.to_bits());word(out,a.end_time.to_bits());for p in a.payload.0 {word(out,u32::from(p.is_some()));if let Some(p)=p {word(out,p);}}}
fn attributes(out:&mut Vec<u8>,a:&[AnimationAttribute]) {word(out,a.len() as u32);for a in a {attribute(out,a);}}
fn status(out:&mut Vec<u8>,r:Result<(),String>) {match r {Ok(())=>word(out,1),Err(e)=>{word(out,0);string(out,&e);}}}
fn boolean(out:&mut Vec<u8>,r:Result<bool,String>) {match r {Ok(v)=>{word(out,1);word(out,u32::from(v));},Err(e)=>{word(out,0);string(out,&e);}}}
fn commands(out:&mut Vec<u8>,commands:&[PoseCommand]) {word(out,commands.len() as u32);for c in commands {match c {
    PoseCommand::Clip{name,previous_time,time,loops}=>{word(out,0);string(out,name);word(out,previous_time.to_bits());word(out,time.to_bits());word(out,*loops);},
    PoseCommand::Blend{weight}=>{word(out,1);word(out,weight.to_bits());},PoseCommand::WeightedBlend{weights}=>{word(out,2);word(out,weights.len() as u32);for v in weights {word(out,v.to_bits());}},
    PoseCommand::ChannelBlend{weight,use_channels_from_weights}=>{word(out,3);word(out,weight.to_bits());word(out,u32::from(*use_channels_from_weights));},
    PoseCommand::Pose{name}=>{word(out,4);string(out,name);},PoseCommand::Add{motion_is_a}=>{word(out,5);word(out,u32::from(*motion_is_a));},PoseCommand::Mirror{trajectory_mode}=>{word(out,6);word(out,*trajectory_mode);},
}}}
fn snapshot(out:&mut Vec<u8>,tree:&PlaybackTree) {
    let(kind,children):(u32,Vec<&PlaybackTree>)=match tree {PlaybackTree::Clip{..}=>(0,vec![]),PlaybackTree::PhaseBlend(s)=>(1,s.children.iter().collect()),PlaybackTree::BlendSpace(s)=>(2,s.children.iter().collect()),PlaybackTree::SelectionSpace(s)=>(3,s.candidates.iter().map(|c|&c.tree).collect()),PlaybackTree::Transition(s)=>(4,vec![&s.from,&s.to]),PlaybackTree::BindPose{motion,..}=>(5,vec![motion])};
    word(out,kind);word(out,tree.length().to_bits());word(out,tree.time().to_bits());word(out,u32::from(has_transition(tree)));
    if let PlaybackTree::SelectionSpace(s)=tree {word(out,u32::from(s.selected.is_some()));if let Some(v)=s.selected {word(out,v as u32);}} else {word(out,0);}
    if let PlaybackTree::BlendSpace(s)=tree {let weights=s.active_weights().collect::<Vec<_>>();word(out,weights.len() as u32);for(i,w)in weights {word(out,i as u32);word(out,w.to_bits());}}else{word(out,0);}
    if let PlaybackTree::Transition(s)=tree {word(out,u32::from(s.complete()));word(out,s.weight().to_bits());}
    if let PlaybackTree::Clip{clip,..}=tree {let c=clip.clock;for v in [c.frames,c.fps,c.base_speed,c.speed,c.length,c.time,c.previous_time] {word(out,v.to_bits());}word(out,c.loops_since_evaluation);word(out,u32::from(c.looping));word(out,u32::from(c.phase_controlled));}
    word(out,children.len() as u32);for child in children {snapshot(out,child);}
}
fn load_metadata(paths:&[&str])->Result<AnimationMetadata,String> {let mut m=AnimationMetadata::load(Path::new(paths[0]))?;for p in &paths[1..] {m.merge(AnimationMetadata::load(Path::new(p))?)?;}Ok(m)}
fn panic_result(f:impl FnOnce())->Result<(),String> {match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {Ok(())=>Ok(()),Err(e)=>Err(e.downcast_ref::<String>().cloned().or_else(||e.downcast_ref::<&str>().map(|s|s.to_string())).unwrap_or("unknown panic".into()))}}
fn operations(input:&mut Input,tree:&mut PlaybackTree,host:&mut MotionAnimation,out:&mut Vec<u8>) ->Result<(),String> {
    let n=input.word();let mut backup=None;for _ in 0..n {match input.word() {
        0=>{tree.set_time(input.float());status(out,Ok(()));},1=>{tree.set_speed(input.float());status(out,Ok(()));},
        2=>{let dt=input.float();let phase=input.float();let mut p=AdvanceResult{crossed_end:input.word()!=0,overshoot:input.float(),remaining_before_wrap:input.float()};status(out,panic_result(||tree.advance(dt,phase,&mut p)));word(out,u32::from(p.crossed_end));word(out,p.overshoot.to_bits());word(out,p.remaining_before_wrap.to_bits());},
        3=>{let a=input.settable();boolean(out,tree.set_attributes(&a));},4=>{let a=input.settable();status(out,host.prepare_selection_spaces(tree,&a));},
        5=>{let parameters=Evaluation{cull_threshold:input.float(),update_history:input.word()!=0};let enabled=input.word()!=0;let mut c=vec![PoseCommand::Pose{name:"SENTINEL".into()}];boolean(out,tree.evaluate(parameters,enabled,&mut c));commands(out,&c);},
        6=>{match tree.attributes(input.word()) {Ok(a)=>{word(out,1);attributes(out,&a);},Err(e)=>{word(out,0);string(out,&e);}}},
        7=>{let name=input.name();let mask=input.word();let mut a=input.attribute();boolean(out,tree.query_attribute(name,mask,&mut a));attribute(out,&a);},
        8=>{*tree=prune(tree.clone());status(out,Ok(()));},9=>{backup=Some(tree.clone());status(out,Ok(()));},10=>{*tree=backup.as_ref().unwrap().clone();status(out,Ok(()));},
        11=>{let to=input.tree()?;let settings=input.transition();*tree=PlaybackTree::Transition(PlaybackTransition::new(tree.clone(),to,settings));status(out,Ok(()));},
        _=>unreachable!(),
    }snapshot(out,tree);}Ok(())
}
fn owner_snapshot(out:&mut Vec<u8>,host:&MotionAnimation) {word(out,u32::from(host.current.is_some()));if let Some(t)=&host.current {snapshot(out,t);}word(out,u32::from(host.current_name.is_some()));if let Some(n)=&host.current_name {string(out,n);}word(out,host.posture.profile());word(out,u32::from(host.posture.is_pending()));word(out,u32::from(host.skater_animation_flags.is_some()));if let Some(f)=host.skater_animation_flags {word(out,f);}word(out,u32::from(host.property.crossed_end));word(out,host.property.overshoot.to_bits());word(out,host.property.remaining_before_wrap.to_bits());attributes(out,&host.tree_attributes);}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let stock=load_metadata(&[&args[1],&args[2]])?;let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{bytes,at:8};let n=input.word();let mut out=Vec::new();
    for _ in 0..n {let kind=input.word();let mut host=MotionAnimation::new(load_metadata(&[&args[3]])?);
        if kind<=2 {let result=if kind==1 {let name=input.string();let construction=input.construction();build(&stock,&name,&construction,&mut Vec::new())}else{input.tree()};match result {Ok(mut tree)=>{word(&mut out,1);snapshot(&mut out,&tree);operations(&mut input,&mut tree,&mut host,&mut out)?;},Err(e)=>{word(&mut out,0);string(&mut out,&e);assert_eq!(input.word(),0);}}}
        else if kind==3 {host.construction_values=input.construction();host.attribute_mirror=input.mirror();host.skater_animation_flags=if input.word()!=0 {Some(input.word())}else{None};host.posture.set_profile(input.word());host.posture.set_requested(input.word()!=0);host.posture_bank_valid=input.word()!=0;let n=input.word();for _ in 0..n {match input.word() {
            0=>{let r=PlaybackRequest{animation:input.string(),speed:input.float(),start_time:input.float(),transition:input.transition()};boolean(&mut out,host.play(r));},
            1=>{let dt=input.float();let phase=input.float();status(&mut out,panic_result(||host.advance(dt,phase)));},
            2=>{for a in input.settable() {host.set_attribute(a);}status(&mut out,host.apply_parameters());},
            3=>{let p=Evaluation{cull_threshold:input.float(),update_history:input.word()!=0};match host.evaluate_pose(p) {Ok(c)=>{word(&mut out,1);commands(&mut out,&c);},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}},
            4=>status(&mut out,host.refresh_tree_attributes()),5=>{host.posture.set_profile(input.word());host.posture.set_requested(input.word()!=0);status(&mut out,Ok(()));},
            6=>{host.skater_animation_flags=if input.word()!=0 {Some(input.word())}else{None};status(&mut out,Ok(()));},
            _=>unreachable!(),
        }owner_snapshot(&mut out,&host);}}
        else {let mut pending=PendingPosture::default();let n=input.word();let mut motion=0u32;for _ in 0..n {match input.word() {0=>{pending.set_profile(input.word());status(&mut out,Ok(()));},1=>{pending.set_requested(input.word()!=0);status(&mut out,Ok(()));},2=>{let success=input.word()!=0;let result=pending.apply::<_,String>(motion,|m,p|if success {Ok(m.wrapping_add(p as u32))}else{Err("Posture construction failed".into())});match result {Ok(m)=>{motion=m;status(&mut out,Ok(()));},Err(e)=>status(&mut out,Err(e))}},_=>unreachable!()}word(&mut out,motion);word(&mut out,pending.profile());word(&mut out,u32::from(pending.is_pending()));word(&mut out,pending.selected_pose().map(|p|p as u32).unwrap_or(0));}}
    }assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&out).map_err(|e|e.to_string())?;Ok(())
}
fn main() {std::panic::set_hook(Box::new(|_|{}));if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
