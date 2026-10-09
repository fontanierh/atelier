#![allow(non_snake_case)]
use std::io::{Read,Write};
use std::cell::RefCell;
use skate_core::player::{state::PhysicalStateId,selector::{StateSelector,StateSelectionInput,input::ProcessedStateInput,conditions::*},lifecycle::*,pre_state::*,state_phase::*,post_state::*};
struct Input{bytes:Vec<u8>,at:usize}
impl Input{fn word(&mut self)->u32{let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}fn float(&mut self)->f32{f32::from_bits(self.word())}fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}}
struct Output(Vec<u8>);
impl Output{fn word(&mut self,w:u32){self.0.extend(w.to_le_bytes());}fn float(&mut self,f:f32){self.word(f.to_bits());}fn string(&mut self,s:&str){self.word(s.len() as u32);self.0.extend(s.as_bytes());}}
// GENERATED_PROTOCOL
struct StateCalls<'a>{trace:&'a RefCell<Output>,reported:PhysicalStateId}
impl PhysicalStateCalls for StateCalls<'_>{fn get_type(&mut self,b:StateBinding)->PhysicalStateId{let mut trace=self.trace.borrow_mut();trace.word(3);observe_StateBinding(&mut trace,&b);self.reported}fn exit(&mut self,c:StateCall){let mut trace=self.trace.borrow_mut();trace.word(4);observe_StateCall(&mut trace,&c);}fn enter(&mut self,c:StateCall){let mut trace=self.trace.borrow_mut();trace.word(5);observe_StateCall(&mut trace,&c);}}
struct ControllerActions<'a>{trace:&'a RefCell<Output>}
impl SkateboardControllerActions for ControllerActions<'_>{fn hold_skateboard(&mut self){self.trace.borrow_mut().word(1);}fn let_go_of_skateboard(&mut self){self.trace.borrow_mut().word(2);}}
struct PhaseCalls<'a>{trace:&'a mut Output,supplied:PreStatePacket}
impl PreStateServices for PhaseCalls<'_>{fn fill_packet_vtable_24(&mut self,p:&mut PreStatePacket){self.trace.word(10);observe_PreStatePacket(self.trace,p);*p=self.supplied;}fn update_component_1840_82d74270(&mut self){self.trace.word(11);}fn update_before_state_vtable_4(&mut self){self.trace.word(12);}}
impl StatePhaseServices for PhaseCalls<'_>{fn update_current_state_vtable_8(&mut self){self.trace.word(20);}fn update_controller_82d75f00(&mut self){self.trace.word(21);}fn update_controller_mode_1_82d751d8(&mut self){self.trace.word(22);}fn update_controller_mode_2_82d750f0(&mut self){self.trace.word(23);}fn update_controller_mode_3_82d75bb8(&mut self){self.trace.word(24);}fn update_controller_mode_4_82d75d58(&mut self){self.trace.word(25);}fn touch_skateboard_vtable_116(&mut self){self.trace.word(26);}fn apply_skateboard_force_queue_82c03718(&mut self){self.trace.word(27);}fn update_skateboard_fixed_step_cache_82db61f0(&mut self){self.trace.word(28);}}
impl PostStateServices for PhaseCalls<'_>{fn update_current_state_vtable_12(&mut self){self.trace.word(30);}}
fn snapshot(o:&mut Output,selector:&StateSelector,lifecycle:&PhysicalPlayerStateLifecycle,data:&StateChangeData,player:&PreStatePlayerFields,skeleton:&PreStateSkeletonFields,phase:&StatePhaseFields){observe_StateSelector(o,selector);observe_StateBinding(o,&lifecycle.active());observe_StateChangeData(o,data);observe_PreStatePlayerFields(o,player);observe_PreStateSkeletonFields(o,skeleton);observe_StatePhaseFields(o,phase);}
fn main(){
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{bytes,at:0};let mut out=Output(Vec::new());out.word(PhysicalStateId::ALL.len() as u32);for id in PhysicalStateId::ALL{out.word(id as u32);out.word(id.native_owner_offset());out.word(id.category());out.word(id.is_grind() as u32);out.string(&format!("{id:?}"));}
    let cases=i.word();for c in 0..cases{let mut selector=read_StateSelector(&mut i);let mut lifecycle=PhysicalPlayerStateLifecycle::new(PhysicalStateId::try_from(i.word()).unwrap());let mut data=read_StateChangeData(&mut i);let mut player=read_PreStatePlayerFields(&mut i);let mut skeleton=read_PreStateSkeletonFields(&mut i);let mut phase=read_StatePhaseFields(&mut i);out.word(c);snapshot(&mut out,&selector,&lifecycle,&data,&player,&skeleton,&phase);let count=i.word();
        for n in 0..count{let op=i.word();let mut ok=true;let mut result=0;let mut unknown=0;let mut trace=Output(Vec::new());match op{
            0=>selector=read_StateSelector(&mut i),
            1=>{let raw=i.word();let input=read_StateSelectionInput(&mut i);match PhysicalStateId::try_from(raw){Ok(current)=>result=selector.calculate(current,&input) as u32,Err(e)=>{ok=false;unknown=e.0;}}trace.word(condition_is_off_ground_skitching(input.board_body,input.skitching_off_ground) as u32);trace.word(condition_is_off_ground(input.board_body,input.normal_off_ground) as u32);trace.word(is_skateboard_animated(input.skeleton) as u32);},
            2=>data=read_StateChangeData(&mut i),
            3=>{let raw=i.word();let reported=PhysicalStateId::try_from(i.word()).unwrap();let call_trace=RefCell::new(Output(Vec::new()));{let mut states=StateCalls{trace:&call_trace,reported};let mut actions=ControllerActions{trace:&call_trace};match lifecycle.set_physics_state(raw,&mut data,&mut states,&mut actions){Ok(binding)=>result=binding.state as u32,Err(e)=>{ok=false;unknown=e.0;}}}trace=call_trace.into_inner();},
            4=>{let supplied=read_PreStatePacket(&mut i);run_pre_state(&mut player,&mut skeleton,&mut PhaseCalls{trace:&mut trace,supplied});},
            5=>{phase.timestep_2604=i.float();phase.controller_state_448=i.word();phase.controller_system_on_452=i.word()!=0;run_state_phase(&mut phase,&mut PhaseCalls{trace:&mut trace,supplied:PreStatePacket::ZERO});},
            6=>phase=read_StatePhaseFields(&mut i),
            7=>run_post_state(&mut PhaseCalls{trace:&mut trace,supplied:PreStatePacket::ZERO}),
            8=>{player=read_PreStatePlayerFields(&mut i);skeleton=read_PreStateSkeletonFields(&mut i);},_=>panic!("unknown probe command")}
            out.word(c);out.word(n);out.word(op);out.word(ok as u32);out.word(result);out.word(unknown);out.word((trace.0.len()/4) as u32);out.0.extend(trace.0);snapshot(&mut out,&selector,&lifecycle,&data,&player,&skeleton,&phase);
        }
    }assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&out.0).unwrap();
}
