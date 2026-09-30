//! Original data binding and host-to-controller compilation, with no rewritten compiler.
#![allow(dead_code)]
#[path = "../../crates/skate-host/src/graph_runtime.rs"]
mod original;
use skate_data::state_graph::{StateGraph,binding::Binding};
use skate_core::graph::{controller::Program,activation::Child};
use std::io::Write;
fn word(out:&mut impl Write,value:usize) {out.write_all(&(value as u32).to_le_bytes()).unwrap();}
fn optional(out:&mut impl Write,value:Option<usize>) {word(out,value.unwrap_or(0xffffffff));}
fn indices(out:&mut impl Write,values:&[usize]) {word(out,values.len());for &value in values {word(out,value);}}
fn program(out:&mut impl Write,p:&Program) {
    for value in [p.topology.states.len(),p.topology.transitions.len(),p.activation.expressions.len(),p.activation.conditions.len(),p.behaviors.len(),p.root] {word(out,value);}
    for (i,s) in p.topology.states.iter().enumerate() {
        optional(out,s.parent);word(out,s.enabled as usize);word(out,s.active as usize);word(out,s.interruptibility as usize);optional(out,s.interrupt_ancestor);
        indices(out,&s.children);indices(out,&s.transitions);optional(out,p.activation.state_expressions[i]);indices(out,&p.state_behaviors[i]);
    }
    for (i,t) in p.topology.transitions.iter().enumerate() {
        word(out,t.enabled as usize);word(out,t.target);word(out,t.priority as usize);optional(out,p.activation.transition_expressions[i]);indices(out,&p.transition_hooks[i]);
    }
    for e in &p.activation.expressions {
        word(out,e.operator as usize);word(out,e.children.len());
        for &child in &e.children {
            let (kind,id)=match child {Child::Expression(id)=>(0,id),Child::Condition(id)=>(1,id)};
            word(out,kind);word(out,id);
        }
    }
    for c in &p.activation.conditions {word(out,c.enabled as usize);word(out,c.mask as usize);}
    for b in &p.behaviors {word(out,b.owner);word(out,b.enabled as usize);}
}
fn main() {
    let args:Vec<_>=std::env::args().collect();
    let graph=StateGraph::load(std::path::Path::new(&args[1])).unwrap();
    let binding=Binding::from_graph(&graph).unwrap();
    let compiled=match original::CompiledGraph::from_binding(&binding) {
        Ok(value)=>value,Err(error)=>{eprintln!("{error}");std::process::exit(3);}
    };
    let mut out=std::io::BufWriter::new(std::io::stdout().lock());
    if args[2]=="program" {program(&mut out,&compiled.program);}
    else {indices(&mut out,&compiled.operations.behaviors);indices(&mut out,&compiled.operations.conditions);indices(&mut out,&compiled.operations.hooks);}
}
