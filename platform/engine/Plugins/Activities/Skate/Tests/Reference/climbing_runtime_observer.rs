// Appended to complete original climbing/mod.rs. Only fixture state writes and
// private read-only observations are added; every numerical body stays original.
fn migration_transform(o:&mut crate::Output,t:&Transform){o.floats(t.scale.to_array());o.floats(t.rotation.to_array());o.floats(t.translation.to_array());}
fn migration_pose(o:&mut crate::Output,p:&[NativeMatrix]){o.word(p.len()as u32);for m in p{o.matrix(*m)}}
fn migration_ledge(o:&mut crate::Output,l:ledge::Ledge){for v in[l.anchor,l.landing,l.forward,l.palms[0],l.palms[1],l.normals[0],l.normals[1]]{o.floats(v.to_array())}}
pub(crate)fn migration_climber_observe(o:&mut crate::Output,r:&Runtime){
 o.word(r.clips.is_some()as u32);o.word(r.indices.len()as u32);for &i in &r.indices{o.word(i as u32)}o.float(r.cooldown);o.word(r.active.is_some()as u32);
 if let Some(a)=&r.active{o.word(match a.phase{Phase::Catch=>0,Phase::Hang=>1,Phase::Mantle=>2,Phase::Settle=>3});o.float(a.time);migration_ledge(o,a.ledge);migration_transform(o,&a.start_root);o.word(a.entry.len()as u32);for t in &a.entry{migration_transform(o,t)}migration_pose(o,&a.fallback);o.matrix(a.board_world.to_cols_array_2d());o.matrix(a.physical_board_world.to_cols_array_2d());o.word(a.carry_board as u32)}
 o.word(r.approach.is_some()as u32);if let Some(a)=&r.approach{approach::migration_climber_observe(o,a)}o.word(r.ground_entry.len()as u32);for t in &r.ground_entry{migration_transform(o,t)}
}
pub(crate)fn migration_climber_seed(p:&GamePhysics,s:&mut SkaterRuntime,i:&mut crate::Input)->Result<(),String>{
 let phase=match i.word(){0=>Phase::Catch,1=>Phase::Hang,2=>Phase::Mantle,3=>Phase::Settle,_=>panic!("Climbing phase")};let carry_board=i.word()!=0;let time=i.float();let feet=Vec3::from_array(i.floats());let facing=Vec3::from_array(i.floats());
 let ledge=ledge::find_air(&p.world,feet,facing).ok_or("Fixture has no real climbing ledge")?;let r=&mut s.climbing;let c=&r.clips.as_ref().unwrap().reach;let entry=c.sample(0.);let root=matrix(s.animated_skeleton.roots.animation_to_world);
 r.active=Some(Attached{phase,time,ledge,start_root:Transform::from_matrix(root),board_world:root*c.globals(&entry)[c.index("SKATEBOARD_ROOT")],entry,fallback:s.render_pose.clone(),physical_board_world:matrix(super::solve::deck_frame(&p.board)),carry_board});Ok(())
}
pub(crate)fn migration_climber_publish(p:&GamePhysics,s:&mut SkaterRuntime,i:&mut crate::Input)->Result<(),String>{let root=Mat4::from_cols_array_2d(&i.matrix());let n=i.word()as usize;let mut pose=s.render_pose.clone();pose.truncate(n);publish_pose(p,s,root,pose)}
pub(crate)fn migration_climber_clear(r:&mut Runtime,cooldown:f32){r.active=None;r.approach=None;r.cooldown=cooldown;}
pub(crate)fn migration_climber_empty_ground(r:&mut Runtime){r.active=None;r.ground_entry.clear();}

pub(crate)fn migration_climber_hang_pose(p:&GamePhysics,s:&mut SkaterRuntime,i:&mut crate::Input)->Result<(),String>{let feet=Vec3::from_array(i.floats());let facing=Vec3::from_array(i.floats());let l=ledge::find_air(&p.world,feet,facing).ok_or("Fixture has no real climbing ledge")?;let r=&s.climbing;let c=&r.clips.as_ref().unwrap().reach;let globals=c.globals(&c.sample(c.duration()));let yaw=Quat::from_rotation_y(l.forward.x.atan2(l.forward.z));let position=l.anchor-yaw*c.hands(&globals)+yaw*contacts::clearance(c,&globals);let root=Transform::from_translation(position).with_rotation(yaw).to_matrix();let mut pose=s.render_pose.clone();for(&j,&g)in r.indices.iter().zip(&globals){pose[j]=native(g)}publish_pose(p,s,root,pose)}
