use std::io::{Read,Write};
struct Input{data:Vec<u8>,at:usize}
impl Input {
 fn word(&mut self)->u32{let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->[f32;3]{std::array::from_fn(|_|self.float())}
 fn frame(&mut self)->original_runtime::Frame {
    let tick=self.word();let dt=self.float();let category=match self.word(){0=>0,1=>1,2=>2,3=>3,4=>4,5=>5,6=>6,7=>7,_=>panic!("invalid category")};
    let state=self.word();let present=self.word()!=0;let name=skate_core::animation::output::attributes::AttributeName(std::array::from_fn(|_|self.word()));
    let grind_id=self.word() as i32;let flags=self.word();let position=self.vector();let velocity=self.vector();let forward=self.vector();
    let switch=self.word()!=0;let fakie=self.word()!=0;let nollie=self.word()!=0;let body_flip=self.word()!=0;let suspend_air=self.word()!=0;let teleported=self.word()!=0;let reverting=self.word()!=0;
    let landing=skate_core::animation::landing_quality::Output{landing_data_167:self.word()!=0,landing_type_96:self.word(),sideways_speed_84:self.float(),spin_92:self.float(),..Default::default()};
    use skate_core::physics::filtered_state::FilteredCategory as C;
    let category=match category{0=>C::Invalid,1=>C::Ground,2=>C::Air,3=>C::Grind,4=>C::Wipeout,5=>C::Teleport,6=>C::Offboard,7=>C::OffboardAir,_=>unreachable!()};
    original_runtime::Frame{tick,dt,category,state,descriptor:present.then_some(name),grind_id,flags,position,velocity,forward,switch,fakie,nollie,body_flip,suspend_air,landing,teleported,reverting}
 }
}
struct Output(Vec<u32>);
impl Output {
 fn word(&mut self,w:u32){self.0.push(w)}fn float(&mut self,f:f32){self.word(f.to_bits())}
 fn floats<const N:usize>(&mut self,v:[f32;N]){for x in v{self.float(x)}}
 fn string(&mut self,s:&str){self.word(s.len() as u32);for v in s.bytes(){self.word(u32::from(v))}}
 fn status(&mut self,r:Result<(),String>){match r{Ok(())=>self.word(1),Err(e)=>{self.word(0);self.string(&e)}}}
 fn carrier(&mut self,c:&skate_core::scoring::carrier::Carrier){self.word(c.scorable.id as u32);self.word(c.scorable.class);self.word(c.scorable.score_type as u32);self.word(c.points as u32);self.float(c.factor);self.float(c.reward);self.float(c.announcement_threshold);self.word(c.start_tick);self.word(c.delay_ticks);self.word(c.announced as u32);self.word(c.completed as u32);self.word(c.unannounced as u32);self.word(c.switch as u32);self.word(c.fakie as u32)}
}
mod original_runtime {
// ORIGINAL_SCORING_RUNTIME
 pub(super) fn observe(r:&Runtime,o:&mut super::Output){
    let start=o.0.len();o.word(0);o.word(match r.collector{Collector::None=>0,Collector::Ground=>1,Collector::Air=>2,Collector::Grind=>3,Collector::Offboard=>4,Collector::Special=>5});
    for c in &r.carriers{o.word(c.is_some() as u32);if let Some(c)=c{o.carrier(c)}}
    for a in [r.held,r.distance,r.metric_rewards]{o.floats(a)}for v in r.metric_started{o.word(v as u32)}o.floats(r.start);o.floats(r.previous);
    for v in [r.previous_heading,r.spin,r.peak,r.air_factor,r.air_repetition]{o.float(v)}o.word(r.air_repetition_set as u32);o.word(r.grab_chain);o.floats(r.air_metrics);
    for v in [r.landing_countdown,r.idle_ticks,r.collector_ticks,r.manual_revert_ticks]{o.word(v)}o.word(r.revert_id.is_some() as u32);if let Some(v)=r.revert_id{o.word(v as u32)}
    o.word(r.sequence_active as u32);o.float(r.sequence_score);o.string(&r.trick_name);for v in r.stance{o.word(v as u32)}for v in [r.clean,r.sketchy,r.new_trick,r.modified_trick,r.close_tricks]{o.word(v as u32)}
    o.0.extend(r.session.holder.migration_runtime_words());o.float(r.session.combo.timer.points);o.word(r.session.combo.timer.expired as u32);o.float(r.session.combo.multiplier);o.float(r.session.line.points);o.word(r.session.line.expired as u32);
    o.0[start]=(o.0.len()-start-1) as u32;
 }
}
fn main()->Result<(),String>{
 let args=std::env::args().collect::<Vec<_>>();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{data:bytes,at:0};let mut o=Output(Vec::new());let cases=i.word();o.word(cases);
 for _ in 0..cases{let mut r=original_runtime::Runtime::load(&data)?;let count=i.word();o.word(count);original_runtime::observe(&r,&mut o);
    for _ in 0..count{let op=i.word();o.word(op);let result=match op{0=>r.advance(i.frame()),1=>original_runtime::Runtime::load(&data).map(|new|r=new),2=>{r.session.holder.set_suppressed(i.word()!=0);Ok(())},_=>panic!("invalid command")};o.status(result);original_runtime::observe(&r,&mut o)}
 }
 assert_eq!(i.at,i.data.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in o.0{stdout.write_all(&w.to_le_bytes()).map_err(|e|e.to_string())?}Ok(())
}
