//! Actual core phase contracts, full host exchange and COM filter.
#![allow(dead_code,unused_imports)]
use skate_core::{math::Vector3,physics::phase::*,player::state::PhysicalStateId};
use std::io::{Read,Write};
mod native_arithmetic {
// @COMPLETE_ARITHMETIC_SOURCE@
}
mod original_com {
// @COMPLETE_COM_SOURCE@
    pub fn migration_observe(&self_not_used: &()) {} // @COM_OBSERVER@
}
mod original_exchange {
// @COMPLETE_EXCHANGE_SOURCE@
    pub(super) fn observe(exchange:&SimulationExchange,out:&mut super::Output) {
        use super::*;
        out.u64(exchange.commands.tick());out.commands(exchange.commands.commands());
        out.events(exchange.events());out.word(exchange.output().is_some() as u32);
        if let Some(value)=exchange.output(){out.snapshot(value);}
    }
    pub(super) fn run(exchange:&mut SimulationExchange,input:&mut super::Input,kind:u32)->Result<(),String> {
        match kind {
            3=>exchange.emit_event(input.u64(),input.event()),
            4=>{exchange.publish_output(input.snapshot());Ok(())},
            5=>exchange.request_state(input.state()),
            _=>unreachable!(),
        }
    }
    pub(super) fn new(tick:u64)->SimulationExchange {SimulationExchange::new(tick)}
}
struct Input {data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let value=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;value}
    fn u64(&mut self)->u64 {u64::from(self.word())|(u64::from(self.word())<<32)}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn vec3(&mut self)->Vector3 {Vector3::new(self.float(),self.float(),self.float())}
    fn vector(&mut self)->[f32;4] {core::array::from_fn(|_|self.float())}
    fn state(&mut self)->PhysicalStateId {self.word().try_into().unwrap()}
    fn body(&mut self)->PhysicsBody {match self.word(){0=>PhysicsBody::Board,1=>PhysicsBody::Rider,_=>unreachable!()}}
    fn command(&mut self)->PhysicsCommand {match self.word(){
        0=>PhysicsCommand::SetVelocity{body:self.body(),linear:self.vec3(),angular:self.vec3()},
        1=>PhysicsCommand::ApplyImpulse{body:self.body(),impulse:self.vec3(),point:self.vec3()},
        2=>PhysicsCommand::RequestState(self.state()),
        3=>PhysicsCommand::SetContactMode{body:self.body(),enabled:self.word()!=0},_=>unreachable!()}}
    fn event(&mut self)->PhysicsEvent {match self.word(){
        0=>PhysicsEvent::StateChanged{from:self.state(),to:self.state()},1=>PhysicsEvent::Landing,
        2=>PhysicsEvent::Wipeout,3=>PhysicsEvent::Contact{body:self.body()},_=>unreachable!()}}
    fn snapshot(&mut self)->PhysicalOutputSnapshot {PhysicalOutputSnapshot{
        tick:self.u64(),state:self.state(),board_position:self.vec3(),board_linear_velocity:self.vec3(),
        rider_root_position:self.vec3(),rider_linear_velocity:self.vec3(),ground_normal:self.vec3(),
        contact_count:self.word(),predicted_position:self.vec3(),grounded:self.word()!=0,wiping_out:self.word()!=0,
        landed:self.word()!=0,events:(0..self.word()).map(|_|self.event()).collect()}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32){self.0.extend(v.to_le_bytes());}
    fn u64(&mut self,v:u64){self.word(v as u32);self.word((v>>32) as u32);}
    fn float(&mut self,v:f32){self.word(v.to_bits());}
    fn string(&mut self,v:&str){self.word(v.len() as u32);self.0.extend(v.as_bytes());}
    fn vector(&mut self,v:[f32;4]){for value in v{self.float(value);}}
    fn vec3(&mut self,v:Vector3){for value in [v.x,v.y,v.z]{self.float(value);}}
    fn status(&mut self,v:Result<(),String>){match v{Ok(())=>self.word(1),Err(error)=>{self.word(0);self.string(&error);}}}
    fn body(&mut self,v:PhysicsBody){self.word(match v{PhysicsBody::Board=>0,PhysicsBody::Rider=>1});}
    fn command(&mut self,v:&PhysicsCommand){match v{
        PhysicsCommand::SetVelocity{body,linear,angular}=>{self.word(0);self.body(*body);self.vec3(*linear);self.vec3(*angular);},
        PhysicsCommand::ApplyImpulse{body,impulse,point}=>{self.word(1);self.body(*body);self.vec3(*impulse);self.vec3(*point);},
        PhysicsCommand::RequestState(v)=>{self.word(2);self.word(*v as u32);},
        PhysicsCommand::SetContactMode{body,enabled}=>{self.word(3);self.body(*body);self.word(*enabled as u32);}}}
    fn commands(&mut self,v:&[PhysicsCommand]){self.word(v.len() as u32);for value in v{self.command(value);}}
    fn event(&mut self,v:&PhysicsEvent){match v{
        PhysicsEvent::StateChanged{from,to}=>{self.word(0);self.word(*from as u32);self.word(*to as u32);},
        PhysicsEvent::Landing=>self.word(1),PhysicsEvent::Wipeout=>self.word(2),
        PhysicsEvent::Contact{body}=>{self.word(3);self.body(*body);}}}
    fn events(&mut self,v:&[PhysicsEvent]){self.word(v.len() as u32);for value in v{self.event(value);}}
    fn snapshot(&mut self,v:&PhysicalOutputSnapshot){self.u64(v.tick);self.word(v.state as u32);
        for x in [v.board_position,v.board_linear_velocity,v.rider_root_position,v.rider_linear_velocity,v.ground_normal]{self.vec3(x);}
        self.word(v.contact_count);self.vec3(v.predicted_position);self.word(v.grounded as u32);self.word(v.wiping_out as u32);self.word(v.landed as u32);self.events(&v.events);}
}
fn observe(commands:&PhysicsCommandBuffer,events:&PhysicsEventBuffer,exchange:&original_exchange::SimulationExchange,
    com:&original_com::CentreOfMassFilter,last:&Option<original_com::CentreOfMassOutput>,out:&mut Output){
    out.u64(commands.tick());out.word(commands.is_empty() as u32);out.commands(commands.commands());
    out.u64(events.tick());out.events(events.events());original_exchange::observe(exchange,out);
    original_com::observe(com,out);out.word(last.is_some() as u32);
    if let Some(last)=last{out.vector(last.velocity);out.vector(last.acceleration);out.vector(last.position);}
}
fn main(){let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut input=Input{data,at:0};let mut output=Output(Vec::new());
    let count=input.word();output.word(count);
    for _ in 0..count {let tick=input.u64();let rows=input.word();output.u64(tick);output.word(rows);
        let mut commands=PhysicsCommandBuffer::new(tick);let mut events=PhysicsEventBuffer::new(tick);
        let mut exchange=original_exchange::new(tick);let mut com=original_com::CentreOfMassFilter::default();let mut last=None;
        observe(&commands,&events,&exchange,&com,&last,&mut output);
        for _ in 0..rows{let kind=input.word();output.word(kind);
            let result=match kind{
                0=>commands.push(input.u64(),input.command()),1=>commands.clear(input.u64()),
                2=>events.emit(input.u64(),input.event()),3|4|5=>original_exchange::run(&mut exchange,&mut input,kind),
                6=>{let position=input.vector();let velocity=input.vector();last=Some(com.update(position,velocity));Ok(())},
                7=>{com.reset();Ok(())},8=>{
                    let raw=input.word();let parsed=PhysicalStateId::try_from(raw);output.status(Ok(()));
                    match parsed {Ok(state)=>{output.word(1);output.word(state as u32);output.word(state.native_owner_offset());output.word(state.category());output.word(state.is_grind() as u32);output.string(&format!("{state:?}"));},Err(error)=>{output.word(0);output.word(error.0);}}
                    observe(&commands,&events,&exchange,&com,&last,&mut output);continue;
                },_=>unreachable!()};
            output.status(result);observe(&commands,&events,&exchange,&com,&last,&mut output);
        }
    }assert_eq!(input.at,input.data.len());std::io::stdout().write_all(&output.0).unwrap();}
