// Data-only observers inside the unchanged original private host owners.
impl AirTrajectoryRuntime {
    pub(crate) fn migration_observe(&self,o:&mut crate::Output){
        o.words.extend(skate_core::air::trajectory::migration_probe::runtime_selector_words(&self.selector));
        skate_core::air::trajectory::migration_probe::settings(&mut o.words,&self.settings);
        o.word(self.pending_results.is_some()as u32);if let Some(results)=&self.pending_results{o.word(results.len()as u32);for &r in results{o.words.extend(skate_core::air::trajectory::migration_probe::runtime_result_words(r));}}
        self.grind_settings.migration_observe(o);
        o.word(self.grind_world.is_some()as u32);if let Some(p)=&self.grind_world{crate::observe_provider(o,p);}
        o.word(self.nearby_grinds.len()as u32);for &i in &self.nearby_grinds{o.word(i as u32);}
    }
}
pub(crate)fn migration_departure(n:[f32;4],v:[f32;4],d:f32)->[f32;4]{vert_departure_normal(n,v,d)}
