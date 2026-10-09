use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn scorable(&mut self)->original_score::Scorable{let id=self.word()as usize;let class=self.word();let score_type=self.word()as usize;original_score::Scorable{id,class,score_type}}
 fn rules(&mut self)->original_score::session::Rules{let combo_capacity=self.float();let combo_levels=std::array::from_fn(|_|(self.float(),self.float()));let combo_refresh_threshold=self.float();let line_capacity=self.float();let bail_factor=self.float();original_score::session::Rules{combo_capacity,combo_levels,combo_refresh_threshold,line_capacity,bail_factor}}
}
struct Output(Vec<u32>);
impl Output{
 fn word(&mut self,w:u32){self.0.push(w)}
 fn float(&mut self,f:f32){self.word(f.to_bits())}
 fn carrier(&mut self,c:&original_score::carrier::Carrier){self.word(c.scorable.id as u32);self.word(c.scorable.class);self.word(c.scorable.score_type as u32);self.word(c.points as u32);self.float(c.factor);self.float(c.reward);self.float(c.announcement_threshold);self.word(c.start_tick);self.word(c.delay_ticks);self.word(c.announced as u32);self.word(c.completed as u32);self.word(c.unannounced as u32);self.word(c.switch as u32);self.word(c.fakie as u32);}
 fn snapshot(&mut self,s:&original_score::session::Session,c:&[original_score::carrier::Carrier;2]){original_score::migration_holder(self,&s.holder);self.float(s.combo.timer.points);self.word(s.combo.timer.expired as u32);self.float(s.combo.multiplier);self.float(s.line.points);self.word(s.line.expired as u32);for carrier in c{self.carrier(carrier)}}
}
mod original_score{
// ORIGINAL_SCORING_OWNER
pub(super) fn migration_holder(o:&mut super::Output,s:&ScoreHolder){let p=&s.snapshot;for v in[p.completed_lines,p.line,p.accumulated,p.last_reward,p.general_pending,p.fingerflip_pending,p.grind_reward]{o.float(v)}for v in s.repetitions{o.word(v as i32 as u32)}for v in s.sequence_history{o.word(v as i32 as u32)}for v in s.type_history{o.word(v as i32 as u32)}o.word(s.pending_sequence as u32);o.word(s.suppressed as u32);}
}
fn main(){
 let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut o=Output(vec![]);let count=i.word();o.word(count);
 for case in 0..count{
  let mut s=original_score::session::Session::default();let mut carriers=std::array::from_fn(|_|original_score::carrier::Carrier::new(original_score::Scorable{id:0,class:0,score_type:0},0,0.,0.,0,0,false,false));let commands=i.word();o.word(case);o.word(commands);o.snapshot(&s,&carriers);
  for _ in 0..commands{let op=i.word();o.word(op);let mut result=0;
   match op{
    0=>{let d=i.scorable();let reward=i.float();s.holder.end_trick(d,reward)},1=>{let d=i.scorable();let reward=i.float();s.holder.credit_trick(d,reward)},2=>s.holder.finish_collector(),3=>s.holder.cancel_pending(),4=>s.holder.reward_sequence(i.float()),5=>{let reward=i.float();let line=i.word()!=0;s.holder.publish(reward,line)},6=>s.holder.clear_sequence_history(),7=>s.holder.bank_line(i.word()!=0),8=>s.holder.reset(),9=>s.holder.set_suppressed(i.word()!=0),10=>result=s.holder.repetition_count(i.scorable()).map(|v|v as i32 as u32).unwrap_or(u32::MAX),
    11=>{let dt=i.float();let drain=i.float();let scale=i.float();result=s.line.advance(dt,drain,scale,i.word()!=0)as u32},12=>{let reward=i.float();let r=i.rules();s.combo.credit(reward,r.combo_capacity,r.combo_levels,r.combo_refresh_threshold)},13=>{let reward=i.float();let capacity=i.float();s.line.credit(reward,capacity)},14=>{let r=i.rules();let landing=i.float();let penalized=i.word()!=0;let enabled=i.word()!=0;result=s.publish_sequence(&r,landing,penalized,enabled).to_bits()},15=>{let reset=i.word()!=0;let active=i.word()!=0;s.settle_line(reset,active)},
    16=>{let slot=i.word()as usize;let d=i.scorable();let points=i.word()as i32;let factor=i.float();let threshold=i.float();let start=i.word();let delay=i.word();let stance=i.word()!=0;let fakie=i.word()!=0;carriers[slot]=original_score::carrier::Carrier::new(d,points,factor,threshold,start,delay,stance,fakie)},17=>{let slot=i.word()as usize;let tick=i.word();result=carriers[slot].announce(tick,i.float())as u32},18=>{let slot=i.word()as usize;result=carriers[slot].complete(i.float())as u32},19=>{let slot=i.word()as usize;let replacement=i.word()as usize;let factor=i.float();assert_ne!(slot,replacement);let(mut a,mut b)=(carriers[slot].clone(),carriers[replacement].clone());a.convert_to(&mut b,factor);carriers[slot]=a;carriers[replacement]=b},20=>{let authored=i.float();let extra=i.float();result=original_score::carrier::delay_ticks(authored,extra)},21=>result=s.line.seconds(i.float()).to_bits(),22=>{let d=i.scorable();result=d.valid()as u32|((d.repetition_applies()as u32)<<1)},_=>panic!("unknown scoring command")
   }o.word(result);o.snapshot(&s,&carriers);
  }
 }assert_eq!(i.at,i.words.len());let mut out=std::io::BufWriter::new(std::io::stdout().lock());for w in o.0{out.write_all(&w.to_le_bytes()).unwrap()}
}
