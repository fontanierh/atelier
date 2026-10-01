// SPDX-License-Identifier: Apache-2.0
//! Entire original core phase with actual original host initial/reset modules.
use std::io::{Read,Write};
use skate_core::{player::input_phase::*,animation::output::{actor_packet::ExternalPhysicsInput,attributes::AttributeName},input::animation_packet::AnimationPacketFields};
mod initial {
// ORIGINAL_INITIAL
}
mod reset {
// ORIGINAL_RESET
}
mod output_reset {
// ORIGINAL_OUTPUT_RESET
}
struct Input{bytes:Vec<u8>,at:usize}
impl Input{fn word(&mut self)->u32{let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}fn wide(&mut self)->u64{let lo=self.word();lo as u64|((self.word() as u64)<<32)}fn float(&mut self)->f32{f32::from_bits(self.word())}fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}}
struct Output(Vec<u8>);
impl Output{fn word(&mut self,w:u32){self.0.extend(w.to_le_bytes());}fn wide(&mut self,w:u64){self.word(w as u32);self.word((w>>32) as u32);}fn float(&mut self,f:f32){self.word(f.to_bits());}fn string(&mut self,s:&str){self.word(s.len() as u32);self.0.extend(s.as_bytes());}fn block(&mut self,row:Self){self.word((row.0.len()/4) as u32);self.0.extend(row.0);}}
// GENERATED_PROTOCOL
struct Frame{fail:u32,manager:u32,pre_state:u32,pre_category:u32,teleport:u32,teleport_state:u32,teleport_category:u32,query56:u32,query44:u32,available:bool,transition:f32,position:RawVector,body_speed:f32,skeleton_a:u32,skeleton_b:u32,skeleton_c:u32,spin:f32,crouch:f32,grind:[u32;2]}
impl Frame{fn read(i:&mut Input)->Self{Self{fail:i.word(),manager:i.word(),pre_state:i.word(),pre_category:i.word(),teleport:i.word(),teleport_state:i.word(),teleport_category:i.word(),query56:i.word(),query44:i.word(),available:i.word()!=0,transition:i.float(),position:i.words(),body_speed:i.float(),skeleton_a:i.word(),skeleton_b:i.word(),skeleton_c:i.word(),spin:i.float(),crouch:i.float(),grind:i.words()}}}
struct Services{frame:Frame,trace:Output,calls:u32}
impl Services{
    fn begin(&mut self,id:u32,p:Option<&PlayerInputState>,f:Option<&PhysicalPlayerInput>,o:Option<&ProcessedPhysicsInput>,packet:Option<&AnimationInputPacket>){let mut e=Output(Vec::new());e.word(id);e.word((p.is_some() as u32)|((f.is_some() as u32)<<1)|((o.is_some() as u32)<<2)|((packet.is_some() as u32)<<3));if let Some(p)=p{observe_PlayerInputState(&mut e,p);}if let Some(f)=f{observe_PhysicalPlayerInput(&mut e,f);}if let Some(o)=o{observe_ProcessedPhysicsInput(&mut e,o);}if let Some(packet)=packet{observe_AnimationInputPacket(&mut e,packet);}self.trace.block(e);self.calls+=1;}
    fn done(&self)->Result<(),String>{if self.frame.fail==self.calls{Err(format!("service {}",self.calls))}else{Ok(())}}
}
impl InputPhaseServices for Services{
    type Error=String;
    fn update_pre_input_manager_82d81610(&mut self,p:&mut PlayerInputState,f:&mut PhysicalPlayerInput)->Result<(),String>{self.begin(1,Some(p),Some(f),None,None);p.state_count_1312=p.state_count_1312.wrapping_add(1);if self.frame.manager!=0{f.state.state_16=self.frame.pre_state;f.state.category_12=self.frame.pre_category;}self.done()}
    fn reset_processed_input_82bf9ef0(&mut self,o:&mut ProcessedPhysicsInput)->Result<(),String>{self.begin(2,None,None,Some(o),None);reset::reset_processed(o);self.done()}
    fn actor_query_slot_56(&mut self)->Result<u32,String>{self.begin(3,None,None,None,None);self.done()?;Ok(self.frame.query56)}
    fn actor_query_slot_44(&mut self)->Result<u32,String>{self.begin(4,None,None,None,None);self.done()?;Ok(self.frame.query44)}
    fn reset_player_probe_82d7a330(&mut self,p:&mut PlayerInputState,f:&mut PhysicalPlayerInput)->Result<(),String>{self.begin(5,Some(p),Some(f),None,None);p.probe=ProbeFields::default();self.done()}
    fn check_teleport_82db88c8(&mut self,p:&mut PlayerInputState,f:&mut PhysicalPlayerInput,o:&mut ProcessedPhysicsInput)->Result<(),String>{self.begin(6,Some(p),Some(f),Some(o),None);if self.frame.teleport!=0{output_reset::reset_outputs(f);f.state.state_16=self.frame.teleport_state;f.state.category_12=self.frame.teleport_category;p.flags_1296|=1<<29;}self.done()}
    fn actor_input_available_slot_4(&mut self)->Result<bool,String>{self.begin(7,None,None,None,None);self.done()?;Ok(self.frame.available)}
    fn transition_action_825903c8(&mut self)->Result<f32,String>{self.begin(8,None,None,None,None);self.done()?;Ok(self.frame.transition)}
    fn calculate_ground_position_82c02840(&mut self,f:&PhysicalPlayerInput)->Result<RawVector,String>{self.begin(9,None,Some(f),None,None);self.done()?;Ok(self.frame.position)}
    fn prepare_board_toolkit_82c013f0(&mut self,p:&mut PlayerInputState,f:&mut PhysicalPlayerInput,o:&mut ProcessedPhysicsInput)->Result<(),String>{self.begin(10,Some(p),Some(f),Some(o),None);o.scalar_2616=self.frame.body_speed;self.done()}
    fn process_skeleton_82bd8918(&mut self,packet:&AnimationInputPacket,f:&mut PhysicalPlayerInput,o:&mut ProcessedPhysicsInput)->Result<(),String>{self.begin(11,None,Some(f),Some(o),Some(packet));o.flags_2468|=self.frame.skeleton_a;o.flags_2472|=self.frame.skeleton_b;o.flags_2476|=self.frame.skeleton_c;o.spin_input_2672=self.frame.spin;o.crouch_2776=self.frame.crouch;self.done()}
    fn update_grind_manager_82d8a828(&mut self,p:&mut PlayerInputState,f:&mut PhysicalPlayerInput,o:&mut ProcessedPhysicsInput)->Result<(),String>{self.begin(12,Some(p),Some(f),Some(o),None);o.grind_words_2532_2536=self.frame.grind;self.done()}
}
fn run()->Result<(),String>{
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{bytes,at:0};let cases=i.word();let mut out=Output(Vec::new());
    for c in 0..cases{
        let p=initial::player(&data)?;out.word(c);observe_PlayerInputState(&mut out,&p);let mut p=read_PlayerInputState(&mut i);let mut f=read_PhysicalPlayerInput(&mut i);let mut o=read_ProcessedPhysicsInput(&mut i);let mut continuation=None;let mut completed:Option<ProcessedPhysicsSnapshot>=None;let commands=i.word();
        for n in 0..commands{
            let op=i.word();let mut trace=Output(Vec::new());let mut calls=0;let result:Result<(),InputPhaseError<String>>=match op{
                0..=2=>{let tick=i.wide();f=read_PhysicalPlayerInput(&mut i);let publication=read_AnimationPacketFields(&mut i);let external=read_ExternalPhysicsInput(&mut i);let packet=read_packet(&mut i,&publication,&external);let mut s=Services{frame:Frame::read(&mut i),trace:Output(Vec::new()),calls:0};let r=if op==0{let r=process_input(&mut p,&mut f,&packet,&mut o,&mut s);if r.is_ok(){completed=Some(ProcessedPhysicsSnapshot::new(tick,o));}r}else if op==1{match start_input(&mut p,&mut f,&packet,&mut o,&mut s){Ok(c)=>{continuation=Some(c);Ok(())},Err(e)=>Err(e)}}else{let c=continuation.take().ok_or("Missing input continuation")?;let r=finish_input(c,&mut p,&mut f,&packet,&mut o,&mut s);if r.is_ok(){completed=Some(ProcessedPhysicsSnapshot::new(tick,o));}r};trace=s.trace;calls=s.calls;r},
                3=>{reset::reset_processed(&mut o);Ok(())},4=>{output_reset::reset_outputs(&mut f);Ok(())},
                5=>{let v=i.floats();let flipped=i.word()!=0;f.skeleton.publish_deck_angles(v,flipped);Ok(())},
                6=>{let mut record=skate_core::physics::skeleton_body::SkeletonPhysicalRecord::default();record.pose[6][3]=i.floats();record.pose[10][3]=i.floats();let forward=i.floats();let up=i.floats();f.skeleton.publish_twist(&record,forward,up);Ok(())},
                7=>{let grind=if i.word()!=0{Some(AttributeName(i.words()))}else{None};let surface=if i.word()!=0{Some(AttributeName(i.words()))}else{None};f.grinds.reset_names(grind,surface);Ok(())},_=>return Err("Invalid input phase operation".into())};
            let (kind,variant,error)=match &result{Ok(())=>(0,0,""),Err(InputPhaseError::Service(s))=>(1,0,s.as_str()),Err(InputPhaseError::InvalidStateVariant(v))=>(2,*v,"")};out.word(c);out.word(n);out.word(op);out.word(result.is_ok() as u32);out.word(kind);out.word(variant);out.string(error);let mut row=Output(Vec::new());observe_PlayerInputState(&mut row,&p);observe_PhysicalPlayerInput(&mut row,&f);observe_ProcessedPhysicsInput(&mut row,&o);row.word(continuation.is_some() as u32);row.word(completed.is_some() as u32);if let Some(s)=&completed{row.wide(s.tick);observe_ProcessedPhysicsInput(&mut row,&s.input);}row.word(calls);row.block(trace);out.block(row);
        }
    }
    assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main(){if let Err(error)=run(){eprintln!("{error}");std::process::exit(2);}}
