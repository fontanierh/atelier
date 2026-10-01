//! Original graph controller oracle with a deterministic, stateful test host.
#![allow(dead_code)]
mod graph;
use graph::{activation::{ActivationProgram,Expression,Child,Condition,ConditionHost},
    controller::{Behavior,Program,Frame,Host,Controller}, selection::{Topology,State,Transition}};
use std::io::{Read,Write};
struct Reader { bytes: Vec<u8>, at: usize }
impl Reader {
    fn word(&mut self)->u32 { let value=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap()); self.at+=4; value }
    fn id(&mut self)->usize { self.word() as usize }
    fn optional(&mut self)->Option<usize> { let value=self.word(); (value!=u32::MAX).then_some(value as usize) }
    fn indices(&mut self)->Vec<usize> { (0..self.id()).map(|_|self.id()).collect() }
}
fn word(out: &mut impl Write, value: u32) { out.write_all(&value.to_le_bytes()).unwrap(); }
fn optional(out: &mut impl Write, value: Option<usize>) { word(out,value.map_or(u32::MAX,|v|v as u32)); }
fn snapshot(out: &mut impl Write, frame: &Frame) {
    word(out,frame.dt.to_bits()); optional(out,frame.current); optional(out,frame.last); word(out,frame.state_times.len() as u32);
    for &value in &frame.state_times { word(out,u32::from(value.is_some())); word(out,value.unwrap_or(0.).to_bits()); }
}
fn program(input: &mut Reader)->Program {
    let (ns,nt,ne,nc,nb)=(input.id(),input.id(),input.id(),input.id(),input.id());
    let root=input.id();
    let mut states=Vec::new(); let mut transitions=Vec::new(); let mut expressions=Vec::new();
    let mut state_expressions=Vec::new(); let mut transition_expressions=Vec::new();
    let mut state_behaviors=Vec::new(); let mut transition_hooks=Vec::new();
    for _ in 0..ns {
        states.push(State {parent:input.optional(),enabled:input.word()!=0,active:input.word()!=0,
            interruptibility:input.word(),interrupt_ancestor:input.optional(),children:input.indices(),transitions:input.indices()});
        state_expressions.push(input.optional()); state_behaviors.push(input.indices());
    }
    for _ in 0..nt {
        transitions.push(Transition {enabled:input.word()!=0,target:input.id(),priority:input.word()});
        transition_expressions.push(input.optional()); transition_hooks.push(input.indices());
    }
    for _ in 0..ne {
        let operator=input.word();
        let children=(0..input.id()).map(|_|{ let kind=input.word();let id=input.id();if kind==0 {Child::Expression(id)} else {Child::Condition(id)} }).collect();
        expressions.push(Expression{operator,children});
    }
    let conditions=(0..nc).map(|_|Condition{enabled:input.word()!=0,mask:input.word()}).collect();
    let behaviors=(0..nb).map(|_|Behavior{owner:input.id(),enabled:input.word()!=0}).collect();
    Program {topology:Topology{states,transitions},root,activation:ActivationProgram{state_expressions,transition_expressions,expressions,conditions},
             behaviors,state_behaviors,transition_hooks}
}
struct TraceHost<W: Write> {out:W,memory:u32,next:u32,tick:u32,values:Vec<u32>}
impl<W:Write> TraceHost<W> {
    fn event(&mut self,kind:u32,id:usize,aux:u32,frame:Option<&Frame>,context:[u32;6]) {
        word(&mut self.out,kind); word(&mut self.out,id as u32); word(&mut self.out,aux); word(&mut self.out,self.memory);
        for value in context { word(&mut self.out,value); }
        word(&mut self.out,u32::from(frame.is_some())); if let Some(frame)=frame {snapshot(&mut self.out,frame);}
        self.memory=self.memory.wrapping_mul(1664525).wrapping_add(1013904223).wrapping_add(id as u32).wrapping_add(kind);
    }
}
impl<W:Write> ConditionHost for TraceHost<W> {
    fn condition_activation(&mut self,id:usize,frame:&Frame)->u32 {
        let mut result=self.values[id]; if result&0x80000000!=0 {result^=self.memory&1;}
        self.event(0,id,result,Some(frame),[0;6]); result
    }
}
impl<W:Write> Host for TraceHost<W> {
    fn context(&self)->[u32;6] {[self.memory,2,0,4,self.tick,6]}
    fn allocate(&mut self,id:usize,frame:&Frame)->u32 {
        self.next+=1; let instance=if self.next%7==0 {0} else {self.next}; self.event(1,id,instance,Some(frame),[0;6]); instance
    }
    fn begin(&mut self,id:usize,context:[u32;6],frame:&Frame) {self.event(2,id,0,Some(frame),context);}
    fn update(&mut self,id:usize,context:[u32;6],frame:&Frame) {self.event(3,id,0,Some(frame),context);}
    fn end(&mut self,id:usize,context:[u32;6],frame:&Frame) {self.event(4,id,0,Some(frame),context);}
    fn hook(&mut self,id:usize,frame:&Frame) {self.event(5,id,0,Some(frame),[0;6]);}
    fn release(&mut self,id:u32) {self.event(6,id as usize,0,None,[0;6]);}
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Reader{bytes,at:0};
    let mut out=std::io::BufWriter::new(std::io::stdout().lock());
    for case in 0..input.word() {
        let program=program(&mut input);let mut controller=Controller::new(program.topology.states.len());
        let mut host=TraceHost{out:&mut out,memory:0x12345678,next:0,tick:0,values:Vec::new()};
        for tick in 0..input.word() {
            let command=input.word();let dt=f32::from_bits(input.word());host.values=input.indices().into_iter().map(|v|v as u32).collect();host.tick=tick;
            word(&mut host.out,0xfffffffe);word(&mut host.out,case);word(&mut host.out,tick);
            if command==0 {controller.update(&program,dt,&mut host);} else {controller.end_all_behaviors(&mut host);}
            word(&mut host.out,0xfffffffd);snapshot(&mut host.out,&controller.frame);word(&mut host.out,controller.active.len() as u32);
            for active in &controller.active {word(&mut host.out,active.behavior as u32);word(&mut host.out,active.instance);}
            word(&mut host.out,host.memory);word(&mut host.out,host.next);
        }
    }
    assert_eq!(input.at,input.bytes.len());
}
