// Appended in the unchanged landing_on_deck Runtime's privacy scope.
pub(crate)fn migration_landing_observe(o:&mut crate::Output,owner:&Runtime){
 let s=&owner.state;o.word(s.output.is_some()as u32);if let Some(v)=s.output{crate::landing_update_out(o,v)}o.float(s.time_to_land);for b in [s.dangerous,s.near_deck,s.turning,s.hippy]{o.word(b as u32)}o.word(s.takeoff_frames as u32);o.floats([s.spin_rate,s.applied_spin,s.transition_angle,s.accumulated_spin]);o.word(s.half_turns as u32);o.word(s.next_half_turns as u32);o.word(s.landing_half_turns()as u32);o.word(s.requests_board_flip()as u32);
 let a=&owner.settings;let r=&owner.root_settings;o.floats([a.minimum_auto_angle,a.automatic_speed,a.input_speed,a.input_delta,a.automatic_delta,a.maximum_landing_speed,r.root_y_offset,r.capsule_radius,r.capsule_length]);
}
