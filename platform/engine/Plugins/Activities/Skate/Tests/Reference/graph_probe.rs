//! Temporary independent oracle: original graph decoding, binding and hashing.
#![allow(dead_code)]
mod state_graph;
use state_graph as reference;
#[derive(Debug)]
pub struct AssetError(pub String);
impl std::fmt::Display for AssetError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(&self.0) }
}
impl std::error::Error for AssetError {}
use reference::{StateGraph, GraphAttribute, attributes::Attributes, binding::{Binding, Node, OperationKind}};
use std::io::{BufRead, Write};
fn word(out: &mut impl Write, value: usize) { out.write_all(&(value as u32).to_le_bytes()).unwrap(); }
fn string(out: &mut impl Write, value: &str) { word(out,value.len()); out.write_all(value.as_bytes()).unwrap(); }
fn optional(out: &mut impl Write, value: Option<usize>) { word(out,value.unwrap_or(0xffffffff)); }
fn indices(out: &mut impl Write, values: &[usize]) { word(out,values.len()); for &value in values { word(out,value); } }
fn node(out: &mut impl Write, value: Node) {
    let (kind,index) = match value { Node::State(i)=>(0,i), Node::Transition(i)=>(1,i), Node::Expression(i)=>(2,i), Node::Operation(i)=>(3,i) };
    word(out,kind); word(out,index);
}
fn attribute(out: &mut impl Write, value: &GraphAttribute) {
    string(out,&value.name); string(out,&value.text); word(out,value.float_bits as usize); word(out,value.boolean_byte as usize);
}
fn dump(out: &mut impl Write, graph: &StateGraph) {
    word(out,graph.elements.len());
    for element in &graph.elements {
        word(out,element.source_offset); string(out,&element.tag); word(out,element.attributes.len());
        for value in &element.attributes { attribute(out,value); }
        indices(out,&element.children);
        let attrs = Attributes::new(&element.attributes);
        for value in &element.attributes { attribute(out,attrs.get(&value.name).unwrap()); }
        word(out,attrs.boolean_byte("absent-parity-probe",231) as usize);
        word(out,attrs.float_bits("absent-parity-probe",0x80000001) as usize);
    }
}
fn binding(out: &mut impl Write, graph: &StateGraph, binding: &Binding) {
    word(out,binding.root); word(out,binding.states.len());
    for state in &binding.states {
        word(out,state.element); string(out,&state.name); optional(out,state.parent);
        indices(out,&state.children); indices(out,&state.behaviors); indices(out,&state.transitions); optional(out,state.expression);
        word(out,state.enabled as usize); word(out,state.active as usize); word(out,state.interruptibility as usize); optional(out,state.interrupt_ancestor);
    }
    word(out,binding.transitions.len());
    for transition in &binding.transitions {
        word(out,transition.element); word(out,transition.owner); optional(out,transition.target); word(out,transition.enabled as usize);
        word(out,transition.priority as usize); optional(out,transition.expression); indices(out,&transition.hooks);
    }
    word(out,binding.expressions.len());
    for expression in &binding.expressions {
        word(out,expression.element); word(out,expression.enabled as usize); word(out,expression.operator as usize); word(out,expression.children.len());
        for &child in &expression.children { node(out,child); }
    }
    word(out,binding.operations.len());
    for operation in &binding.operations {
        word(out,operation.element); node(out,operation.parent);
        word(out,match operation.kind { OperationKind::Behavior=>0,OperationKind::Condition=>1,OperationKind::Hook=>2 });
        string(out,&operation.name); word(out,operation.enabled as usize); optional(out,operation.condition_mask.map(|v|v as usize));
        indices(out,&operation.parameters);
    }
    for (i,state) in binding.states.iter().enumerate() {
        let mut names = vec![state.name.as_str(),"","missing.parity.state",&binding.states[0].name];
        if let Some(parent)=state.parent { names.push(&binding.states[parent].name); }
        for &child in &state.children { names.push(&binding.states[child].name); }
        let attrs = Attributes::new(&graph.elements[state.element].attributes);
        if let Some(interrupt)=attrs.text("interruptable") { names.push(interrupt); }
        for &transition in &state.transitions {
            // Attribute values outlive the temporary index, whose getters return graph borrows.
            let values = Attributes::new(&graph.elements[binding.transitions[transition].element].attributes);
            if let Some(target)=values.text("target") { names.push(target); }
        }
        word(out,names.len());
        for name in names { for ascend in [false,true] { optional(out,binding.find_state(i,name,ascend)); } }
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    if args.len()==2 && args[1]=="hash" {
        for line in std::io::stdin().lock().lines() {
            let name=line.unwrap();
            writeln!(out,"{:08x} {:08x} {:08x} {:x}",reference::attributes::byte_hash(name.as_bytes()),reference::attributes::key_hash(&name),
                     reference::binding::name_hash(&name),reference::binding::parse_condition_mask(Some(&name))).unwrap();
        }
        return;
    }
    let graph = match StateGraph::load(std::path::Path::new(&args[1])) {
        Ok(value)=>value, Err(error)=>{ eprintln!("{error}"); std::process::exit(2); }
    };
    if args[2]=="dump" { dump(&mut out,&graph); }
    else {
        let bound=match Binding::from_graph(&graph) { Ok(value)=>value,Err(error)=>{ eprintln!("{error}"); std::process::exit(3); } };
        binding(&mut out,&graph,&bound);
    }
}
