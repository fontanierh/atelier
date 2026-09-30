//! Temporary full original-host oracle, compiled from unchanged pinned modules.
#![allow(dead_code,unused_imports)]
// The harness stages unchanged source files in their normal module layout.
// A path attribute on physics.rs would make its child `mod` paths incorrect.
mod physics;
mod graph_host;
mod graph_runtime;
mod skater_animation;
mod animation_pose;
mod camera;
mod difficulty;
mod grind_world;
mod input;
mod scoring_runtime;
mod skate_world;
mod animation;
mod crash_context;
mod tuning;
mod session_marker;
pub use physics::bridge;
#[path="../../crates/skate-host/src/graph_host/action_board_adjust.rs"] mod original_board_adjust;
#[path="../../crates/skate-host/src/graph_host/motion_sliding.rs"] mod original_sliding;
// The sliding module's animation provider is an explicit read-only boundary.
// It queries the same original encoded IntentMap and supplies no animation math.
mod motion_animation {
    use skate_core::{graph::intents::IntentMap,animation::{playback_parameters::ParameterInputs,output::attributes::{AnimationAttribute,AttributeName}}};
    #[derive(Default)] pub struct MotionAnimation {pub motion_intents:IntentMap}
    impl ParameterInputs for MotionAnimation {
        fn motion_intent(&self,name:&str)->Option<f32>{self.motion_intents.get(name).copied()}
        fn filtered_intent(&self,_:&str)->Option<f32>{panic!("unused filtered provider")}
        fn last_attribute(&mut self,_:AttributeName)->Result<Option<AnimationAttribute>,String>{panic!("unused attribute provider")}
    }
}
use skate_core::{graph::{conditions::{ActionCondition,ConditionInputs,SpeedInputs,PhysicalStateInputs,PushBrakeInputs},intent_handlers::{ConstMgIntent,TimeMgIntent},intents::IntentMap,
    controller::{Controller,Host,Frame}},input::{graph_intents::IntentMutation,set_turning::SlideLatch}};
use skate_data::{collections::Collections,state_graph::{StateGraph,GraphAttribute,attributes::Attributes,binding::{Binding,OperationFactory,OperationKind,Node}}};
use graph_host::action_nodes::{ActionFactory,ActionOperation,Parameter};
use std::io::{Read,Write};
struct Input{data:Vec<u8>,at:usize}
impl Input{
    fn word(&mut self)->u32{let value=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;value}
    fn float(&mut self)->f32{f32::from_bits(self.word())}
    fn string(&mut self)->String{let n=self.word()as usize;let value=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;value}
    fn optional(&mut self)->Option<f32>{if self.word()!=0{Some(self.float())}else{None}}
    fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}
    fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}
    fn attributes(&mut self)->Vec<GraphAttribute>{(0..self.word()).map(|_|GraphAttribute{name:self.string(),text:self.string(),float_bits:self.word(),boolean_byte:self.word()as u8}).collect()}
}
struct Output(Vec<u8>);
impl Output{
    fn word(&mut self,v:u32){self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32){self.word(v.to_bits());}
    fn optional(&mut self,v:Option<f32>){self.word(u32::from(v.is_some()));if let Some(v)=v{self.float(v);}}
    fn string(&mut self,v:&str){self.word(v.len()as u32);self.0.extend(v.as_bytes());}
    fn text(&mut self,v:&Option<String>){self.word(u32::from(v.is_some()));if let Some(v)=v{self.string(v);}}
    fn bits(&mut self,v:Option<u32>){self.word(u32::from(v.is_some()));if let Some(v)=v{self.word(v);}}
    fn param(&mut self,p:&Parameter){for v in [&p.name,&p.mg_intent,&p.mg_intent_mag,&p.mg_intent_angle,&p.ag_intent,&p.text]{self.text(v);}self.bits(p.float_bits);self.bits(p.boolean_byte.map(u32::from));
        self.optional(p.default_value);self.optional(p.scale);self.word(u32::from(p.on_update));for f in p.filters{self.word(f);}self.word(p.angle_filter);self.word(u32::from(p.negate_on_mirror));}
    fn mutation(&mut self,m:IntentMutation){match m{IntentMutation::None=>self.word(0),IntentMutation::Remove=>self.word(1),IntentMutation::Set(v)=>{self.word(2);self.float(v);}}}
    fn snapshot(&mut self,map:&IntentMap,names:&[String]){self.word(map.len()as u32);for name in names{self.optional(map.get(name).copied());}}
}
fn main(){
    let args:Vec<_>=std::env::args().collect();let mut out=Output(Vec::new());
    if args[1]=="config"{
        let source=StateGraph::load(std::path::Path::new(&args[2])).unwrap();let binding=Binding::from_graph(&source).unwrap();let operations=binding.instantiate_operations(&source,&mut ActionFactory).unwrap().operations;
        out.word(operations.len()as u32);for op in operations{out.param(&op.config);out.word(op.parameters.len()as u32);for p in op.parameters{out.param(&p);}}
    }else{
        let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let commands=r.word();let collections=Collections::load(std::path::Path::new(&args[3])).unwrap();let sliding=original_sliding::Settings::load(&collections).unwrap();
        for _ in 0..commands{let op=r.word();out.word(op);match op{
            0=>{let attributes=r.attributes();let numeric=graph_host::parse_numeric_condition(&Attributes::new(&attributes));out.word(numeric.comparison as u32);out.float(numeric.threshold);out.word(u32::from(numeric.absolute));for _ in 0..r.word(){out.word(u32::from(numeric.matches(r.float())));}},
            1=>{let attributes=r.attributes();let a=Attributes::new(&attributes);let op=ActionFactory.create(OperationKind::Behavior,Node::State(0),&a).unwrap().unwrap();out.param(&op.config);
                let f=graph_host::motion_intent_filter::Operation::parse(&a);out.string(&f.intent);out.string(&f.filtered_intent);let s=f.settings;out.float(s.starting_value);out.float(s.default_value);out.float(s.scale);for f in s.filters{out.word(f);}
                out.optional(s.ramp_time);out.float(s.blend_rising);out.float(s.blend_falling);out.optional(s.blend_out);out.optional(s.clamp_velocity);out.optional(s.clamp_acceleration);},
            2=>{let mut constant=ConstMgIntent::new(r.float(),r.word()!=0);let mut time=TimeMgIntent{elapsed:r.float()};let mut board=original_board_adjust::State::default();
                for _ in 0..r.word(){let phase=r.word();let value=r.optional();let dt=r.float();out.mutation(match phase{0=>constant.begin(),1=>constant.update(),_=>constant.end()});
                    out.mutation(if phase==1{time.update(value,dt)}else{time.end()});out.float(time.elapsed);let magnitude=r.optional();let angle=r.optional();let filter=r.word();let negate=r.word()!=0;let mirrored=r.word()!=0;
                    if phase==0{board.begin();}let result=board.update(magnitude,angle,filter,negate,mirrored);out.word(u32::from(result.is_some()));if let Some((m,a))=result{out.float(m);out.float(a);}}},
            3=>{let attributes=r.attributes();let operation=graph_host::motion_intent_filter::Operation::parse(&Attributes::new(&attributes));let mut state=skate_core::animation::intent_filter::State::default();let mut input=IntentMap::new();let mut output=IntentMap::new();let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();
                for _ in 0..r.word(){let phase=r.word();let value=r.optional();let dt=r.float();let flags=if r.word()!=0{Some(r.word())}else{None};input.clear();if let Some(v)=value{input.insert(&operation.intent,v);}
                    let error=match phase{0=>{operation.begin(&mut state,&mut output);""},1=>{if let Some(flags)=flags{operation.update(&mut state,&input,&mut output,dt,(flags&0x20000000!=0,flags&0x40000000!=0));""}else{"FilterMotionGraphIntent requires live animation stance flags"}},_=>{operation.end(&mut output);""}};
                    out.word(u32::from(error.is_empty()));out.string(error);out.float(state.elapsed);out.float(state.previous_delta);out.float(state.value);out.snapshot(&output,&names);}},
            4=>{let attributes=r.attributes();let operation=ActionFactory.create(OperationKind::Condition,Node::State(0),&Attributes::new(&attributes)).unwrap().unwrap();let ActionOperation::Condition(mut condition)=operation.operation else{panic!("expected core condition")};
                let category=r.word();let grinding=r.word()!=0;let grind_name=r.string();let speed=r.float();let forward_speed=r.float();let speed_and_slope=r.float();let elapsed=r.float();let mirrored=r.word()!=0;let fakie=r.word()!=0;let ground_axis_y=r.float();let disabled=r.word()!=0;let maximum=r.float();let present=r.word();
                let inputs=ConditionInputs{speeds:(present&1!=0).then_some(SpeedInputs{speed,forward_speed,speed_and_slope}),physical_state:(present&2!=0).then_some(PhysicalStateInputs{category,grinding,grind_name}),time_since_last_input:(present&4!=0).then_some(elapsed),mirrored:(present&8!=0).then_some(mirrored),riding_fakie:(present&16!=0).then_some(fakie),push_brake:(present&32!=0).then_some(PushBrakeInputs{ground_axis_y,skeleton_disables_push_brake:disabled,maximum_ground_angle_degrees:maximum})};
                let mut action=IntentMap::new();for _ in 0..r.word(){let name=r.string();action.insert(&name,r.float());}let parents:Vec<_>=(0..r.word()).map(|_|match r.word(){0xffffffff=>None,n=>Some(n as usize)}).collect();let current=match r.word(){0xffffffff=>None,n=>Some(n as usize)};let target=match r.word(){0xffffffff=>None,n=>Some(n as usize)};
                if let ActionCondition::CurrentState{target:ref mut bound,..}=condition{*bound=target;}let value=condition.evaluate(&inputs,&action,current,&parents);match value{Ok(v)=>{out.word(1);out.word(u32::from(v));out.string("");},Err(error)=>{out.word(0);out.word(0);out.string(error);}}},
            5=>{let mut state=original_sliding::State::default();let mut latch:SlideLatch=unsafe{std::mem::transmute(r.words::<5>())};let mut deceleration=r.float();
                for _ in 0..r.word(){let category=r.word();let speed=r.float();let direction=r.float();let dt=r.float();let mut animation=motion_animation::MotionAnimation::default();
                    for name in ["RightSlide","LeftSlide","RightSlideStart","LeftSlideStart"]{if let Some(v)=r.optional(){animation.motion_intents.insert(name,v);}}
                    state.update(&animation,category,speed,direction,dt,&sliding,&mut latch);let words:[u32;5]=unsafe{std::mem::transmute(latch)};for word in words{out.word(word);}
                    for right in [false,true]{for v in original_sliding::create(&latch,right,animation.motion_intents.get("RightSlide").copied(),animation.motion_intents.get("LeftSlide").copied(),&sliding){out.float(v);}}
                    let velocity=r.floats();let z=r.floats();let flipped=r.word()!=0;out.float(original_sliding::direction(velocity,z,flipped));let ground=std::array::from_fn(|_|r.floats());out.float(original_sliding::deceleration(&mut deceleration,velocity,ground,&sliding));out.float(original_sliding::spin(direction,&sliding));}},
            6=>{let source=StateGraph::load(std::path::Path::new(&args[4])).unwrap();let binding=Binding::from_graph(&source).unwrap();let runtime=graph_runtime::CompiledGraph::from_binding(&binding).unwrap();let graph=graph_runtime::LoadedGraph{source,binding,runtime};
                let mut host=graph_host::action::ActionHost::from_graph(&graph,&collections).unwrap();let mut controller=Controller::new(graph.binding.states.len());let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();
                for _ in 0..r.word(){let ending=r.word()!=0;let dt=r.float();host.action_intents.clear();host.errors.clear();for _ in 0..r.word(){let name=r.string();host.action_intents.insert(&name,r.float());}
                    host.stance=match r.word(){0=>None,n=>Some(((n-1)&1!=0,(n-1)&2!=0))};host.condition_inputs.physical_state=Some(PhysicalStateInputs{category:r.word(),grinding:false,grind_name:String::new()});host.condition_inputs.time_since_last_input=r.optional();
                    if ending{controller.end_all_behaviors(&mut host);}else{controller.update(&graph.runtime.program,dt,&mut host);}
                    let frame=&controller.frame;out.float(frame.dt);out.word(frame.current.map_or(0xffffffff,|v|v as u32));out.word(frame.last.map_or(0xffffffff,|v|v as u32));out.word(frame.state_times.len()as u32);for &time in &frame.state_times{out.optional(time);}
                    out.word(controller.active.len()as u32);for a in &controller.active{out.word(a.behavior as u32);out.word(a.instance);}out.snapshot(&host.motion_intents,&names);out.string(&host.errors.join("|"));}},
            7=>{use skate_core::{animation::{output::attributes::{AnimationAttribute,AttributePayload},skeleton_input::name::encode},graph::activation::ConditionHost};
                let attributes=r.attributes();let operation=ActionFactory.create(OperationKind::Condition,Node::State(0),&Attributes::new(&attributes)).unwrap().unwrap();
                let instances=graph_host::action_nodes::ActionInstances::new(vec![operation]);let remap=graph_runtime::OperationRemap{behaviors:vec![],conditions:vec![0],hooks:vec![]};
                let mut host=graph_host::action::ActionHost::new(instances,remap);for _ in 0..r.word(){let name=encode(r.string().as_bytes());let sequence_id=r.word()as i32;let kind=r.word()as u8;let payload=AttributePayload(std::array::from_fn(|_|if r.word()!=0{Some(r.word())}else{None}));
                    host.animation_attributes.push(AnimationAttribute{name,sequence_id,kind,payload,begin_time:0.,end_time:0.,status:0});}
                if r.word()!=0{host.physical_conditions=Some(graph_host::action::PhysicalConditions{requests_dismount:r.word()!=0,state:r.word()});}
                let frame=Frame{dt:0.,current:None,last:None,state_times:vec![]};out.word(host.condition_activation(0,&frame));out.string(&host.errors.join("|"));},
            8=>{use skate_core::graph::activation::ConditionHost;
                let source=StateGraph::load(std::path::Path::new(&args[4])).unwrap();let binding=Binding::from_graph(&source).unwrap();let runtime=graph_runtime::CompiledGraph::from_binding(&binding).unwrap();let graph=graph_runtime::LoadedGraph{source,binding,runtime};
                let mut host=graph_host::action::ActionHost::from_graph(&graph,&collections).unwrap();for _ in 0..r.word(){let current=match r.word(){0xffffffff=>None,n=>Some(n as usize)};let state_times=(0..r.word()).map(|_|r.optional()).collect();let frame=Frame{dt:0.,current,last:None,state_times};host.errors.clear();
                    out.word(graph.runtime.operations.conditions.len()as u32);for id in 0..graph.runtime.operations.conditions.len(){out.word(host.condition_activation(id,&frame));}out.string(&host.errors.join("|"));}},
            _=>panic!("invalid operation"),
        }}assert_eq!(r.at,r.data.len());
    }
    std::io::stdout().write_all(&out.0).unwrap();
}
