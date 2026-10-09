// GENERATED_WHOLE_HOST_MODULE_DECLARATIONS
use std::io::{Read,Write};
use skate_core::{animation::{output::attributes::AttributeName,landing_quality as landing},physics::filtered_state as filtered,point_graph};
// GENERATED_VERIFIED_FILTERED_WIRE
// GENERATED_DECLARATION_PROTOCOL
fn main()->Result<(),String>{
    let args:Vec<_>=std::env::args().collect();
    let stock=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;
    let fixture=skate_data::collections::Collections::load(std::path::Path::new(&args[2]))?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;
    let mut i=Input{bytes,at:0};let mut o=Output::default();
    physics::migration_player_state_run(&stock,&fixture,&mut i,&mut o)?;
    if i.at!=i.bytes.len(){return Err("unconsumed input".into());}
    std::io::stdout().write_all(&o.0).map_err(|e|e.to_string())
}
