// Append-only private access and observations after the full original module.
fn migration_boneless_owner(o:&mut crate::Output,b:&Boneless){
 o.word(b.toe as u32);o.floats(b.anchor);o.word(b.right as u32);
 for g in b.curves{o.floats(g.x);o.floats(g.y)}
}
pub(super)fn migration_boneless_observe(o:&mut crate::Output,s:&super::SkaterRuntime){
 migration_boneless_owner(o,&s.boneless);
}
pub(super)fn migration_boneless_launch(p:&mut super::GamePhysics,s:&mut super::SkaterRuntime)->Result<(),String>{launch(p,s)}
pub(super)fn migration_boneless_load(stock:&std::path::Path,invalid:&std::path::Path,o:&mut crate::Output)->Result<(),String>{
 let data=Collections::load(stock.join("private/stock/skater-collections.json")).map_err(|e|e.to_string())?;
 let mut b=Boneless::load(&data)?;
 let data=Collections::load(invalid.join("private/stock/skater-collections.json")).map_err(|e|e.to_string())?;
 match Boneless::load(&data){Ok(next)=>{b=next;o.status(Ok(()))},Err(e)=>o.status(Err(e))}
 migration_boneless_owner(o,&b);Ok(())
}
