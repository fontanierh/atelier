mod biped_world {
// GENERATED_WORLD
pub(super)fn read(input:&mut crate::Input)->Result<BoardWorld,String>{
 let mut r=Reader{bytes:input.data.clone(),at:input.at};let count=r.word();let triangles=(0..count).map(|_|cached(triangle(&mut r))).collect();let enabled=r.word()!=0;let data=metadata(&mut r);input.at=r.at;
 if enabled{BoardWorld::with_query_metadata(triangles,data).map_err(str::to_owned)}else{Ok(BoardWorld::new(triangles))}
}
}
fn read_biped_world(i:&mut Input)->Result<BoardWorld,String>{biped_world::read(i)}
