// GENERATED_COMPLETE_OWNER_OBSERVATIONS
fn boneless_snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,last:&skate_core::air::known::KnownAirOutput){
 block(o,|o|boneless::migration_boneless_observe(o,s));
 block(o,|o|{o.floats(s.skeleton.record.pose[15][3]);o.floats(s.skeleton.record.pose[19][3]);});
 snapshot(o,p,s,last);
}
pub(super)fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
// GENERATED_COMPLETE_OWNER_CONSTRUCTION
 boneless_snapshot(o,&p,&s,&last);
 for _ in 0..n{let op=i.word();o.word(op);let r=match op{
// GENERATED_ORIGINAL_CALLER_CASES
 30=>boneless::enter(&mut p,&mut s),31=>boneless::update(&mut p,&mut s),
 32=>boneless::migration_boneless_launch(&mut p,&mut s),
 33=>{let x=&mut s.player_input.processed;x.vectors_544_560_592_608[0]=i.floats::<4>().map(f32::to_bits);x.vectors_544_560_592_608[3]=i.floats::<4>().map(f32::to_bits);x.prepared_jump_704=i.floats::<4>().map(f32::to_bits);x.vectors_544_560_592_608[2]=i.floats::<4>().map(f32::to_bits);x.effective_anim_transform_192[2]=i.floats::<4>().map(f32::to_bits);Ok(())},
 35=>{s.player_input.processed.flags_2468=i.word();s.player_input.processed.flags_2480=i.word();Ok(())},
 _=>panic!("Boneless wire operation")};o.status(r);boneless_snapshot(o,&p,&s,&last);
 }
 }Ok(())
}
}
pub(crate)fn migration_boneless_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_boneless::run(a,f,i,o)}
pub(crate)fn migration_boneless_load(a:&std::path::Path,f:&std::path::Path,o:&mut crate::Output)->Result<(),String>{boneless::migration_boneless_load(a,f,o)}
