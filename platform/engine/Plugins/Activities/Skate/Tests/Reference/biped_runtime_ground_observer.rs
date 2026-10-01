// Read-only complete Owner observation in its original privacy scope.
pub(crate)fn migration_biped_observe(o:&mut crate::Output,s:&Owner){
 crate::observe_BipedControllerState(o,&s.controller.state);
 o.word(s.result.is_some()as u32);if let Some(r)=s.result{crate::observe_BipedGroundResult(o,&r)}
 crate::observe_BipedGroundState(o,&s.ground);crate::biped_contact::prefix_out(o,s.contact);
 let i=&s.controller.settings.movement_intent;for g in [i.sprint_blend,i.slide_steering]{o.floats(g.x);o.floats(g.y)}o.floats(i.sprint_speed.x);o.floats(i.sprint_speed.y);o.floats(i.normal_speed.x);o.floats(i.normal_speed.y);o.float(i.sprint_time_cap);
 let v=&s.controller.settings.movement_velocity;for g in [v.slope_speed_scalar,v.slope_mode_speed,v.turn_vs_speed,v.turn_delta_vs_speed,s.controller.settings.slide_vs_slope,s.controller.settings.slide_vs_speed]{o.floats(g.x);o.floats(g.y)}
 o.word(s.geometry_adjustment.is_some()as u32);if let Some(a)=s.geometry_adjustment{crate::biped_geometry::adjustment_out(o,a)}
 super::offboard::skeleton_ground::migration_biped_observe(o,&s.skeleton_state);
 super::offboard::ground_geometry::migration_biped_observe(o,&s.geometry);
 for g in [s.movement_vs_stick_angle,s.turn_vs_stick_angle]{o.floats(g.x);o.floats(g.y)}
 o.float(s.air_launch.jump_speed_scalar);o.float(s.air_launch.jump_height);
 let c=&s.collision_settings;for f in [c.vehicle_scalar,c.vehicle_contact,c.maximum_displacement,c.maximum_arm_contact,c.maximum_body_contact,c.minimum_speed,c.maximum_squash,c.special_scalar]{o.float(f)}
 let b=&s.grab_settings;o.floats(b.extent_0);o.floats(b.extent_16);o.floats(b.offset_32);for f in [b.angle_436,b.angle_440,b.margin_444,b.angle_452,b.angle_456]{o.float(f)}
}
