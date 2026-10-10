use std::io::Write;
use skate_core::player::state::PhysicalStateId;
mod original_host {
// ORIGINAL_HOST
}
fn main(){
    let registry=original_host::StateRegistry::new();
    let ids=[100,101,102,103,104,105,200,201,202,300,400,401,402,403,404,405,500,501,502,503,600,601,602,700,701,702];
    let states:Vec<PhysicalStateId>=ids.into_iter().map(|id|id.try_into().unwrap()).collect();
    let mut output=Vec::<u32>::new();
    for &id in &states {let capability=registry.capability(id);output.extend([capability.id as u32,capability.supported as u32,capability.has_enter as u32,capability.has_exit as u32]);}
    for &current in &states {for &requested in &states {output.extend([current as u32,requested as u32,registry.can_transition(current,requested) as u32]);}}
    let mut stream=std::io::BufWriter::new(std::io::stdout().lock());for word in output {stream.write_all(&word.to_le_bytes()).unwrap();}
}
