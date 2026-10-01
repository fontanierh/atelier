pub(crate)fn migration_biped_observe(o:&mut crate::Output,s:&BipedAir){
 crate::observe_BipedAirState(o,&s.state);for c in [s.checks.skeleton_air,s.checks.offboard_air]{for f in [c.squash,c.displacement,c.body_contact,c.arm_contact]{o.float(f)}}o.float(s.checks.offboard_min_speed);
}
