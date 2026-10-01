//! Temporary migration oracle. All skate-core implementation comes unchanged
//! from the pinned Git revision; this target only publishes subsystem state.
use skate_core::{animation::{skeleton_input::name::encode, playback_parameters::intent_key, intent_filter},
    graph::intents::IntentMap, input::{pad::Pad, history::{PadHistory, HistoryRecord}, xbox::{self,XboxState},
    controller::{self,ActionMap,DerivedControllerInput}, gameplay_map::GameplayActions, riding_intentions,
    anticipation_intentions,manual_intentions,trick_intentions,grind_intentions,wipeout_intentions,offboard_intentions,
    graph_intents,turn_conditioner,turn_remap,set_turning,power_sliding,body_flip_signal,animation_packet}, point_graph::PointGraph};
use std::io::{Read,Write};
struct Input { bytes:Vec<u8>, at:usize }
impl Input {
    fn word(&mut self)->u32 { let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap()); self.at+=4; v }
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn words<const N:usize>(&mut self)->[u32;N] { std::array::from_fn(|_|self.word()) }
    fn floats<const N:usize>(&mut self)->[f32;N] { std::array::from_fn(|_|self.float()) }
    fn raw(&mut self)->Vec<u8> {let n=self.word() as usize;let v=self.bytes[self.at..self.at+n].to_vec();self.at+=n;v}
    fn string(&mut self)->String {String::from_utf8(self.raw()).unwrap()}
    fn optional(&mut self)->Option<f32> {if self.word()!=0 {Some(self.float())}else{None}}
    fn stance(&mut self)->Option<(bool,bool)> {match self.word(){0=>None,n=>Some(((n-1)&1!=0,(n-1)&2!=0))}}
    fn graph<const N:usize>(&mut self)->PointGraph<N> {PointGraph{x:self.floats(),y:self.floats()}}
    fn remap(&mut self)->turn_remap::TurnRemap {turn_remap::TurnRemap{magnitude:self.graph(),angle:self.graph(),angle_offset:self.float()}}
    fn filter(&mut self)->intent_filter::Settings {intent_filter::Settings{starting_value:self.float(),default_value:self.float(),scale:self.float(),filters:self.words(),
        ramp_time:self.optional(),blend_rising:self.float(),blend_falling:self.float(),blend_out:self.optional(),clamp_velocity:self.optional(),clamp_acceleration:self.optional()}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32){self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32){self.word(v.to_bits());}
    fn words<const N:usize>(&mut self,v:[u32;N]){for w in v{self.word(w);}}
    fn floats<const N:usize>(&mut self,v:[f32;N]){for w in v{self.float(w);}}
    fn optional(&mut self,v:Option<f32>){self.word(u32::from(v.is_some()));if let Some(v)=v{self.float(v);}}
    fn string(&mut self,v:&str){self.word(v.len() as u32);self.0.extend(v.as_bytes());}
    fn intents<'a>(&mut self,v:impl IntoIterator<Item=(&'a str,f32)>){let v:Vec<_>=v.into_iter().collect();self.word(v.len() as u32);for(n,v)in v{self.string(n);self.float(v);}}
    fn pad(&mut self,p:&Pad){self.word(p.count()as u32);self.word(p.records().len()as u32);for r in p.records(){self.words(*r);}}
    fn mutation(&mut self,m:graph_intents::IntentMutation){match m{graph_intents::IntentMutation::None=>self.word(0),graph_intents::IntentMutation::Remove=>self.word(1),graph_intents::IntentMutation::Set(v)=>{self.word(2);self.float(v);}}}
}
struct ScriptMap {values:[f32;18],later:[f32;18],states:[u32;18],calls:[u32;18],log:Vec<u32>}
impl ActionMap for ScriptMap {
    fn value(&mut self,action:u32)->f32 {self.log.push(action);let i=(action-64)as usize;let value=if self.calls[i]==0{self.values[i]}else{self.later[i]};self.calls[i]+=1;value}
    fn state(&mut self,action:u32)->u8 {self.log.push(action|0x80000000);self.states[(action-64)as usize]as u8}
}
fn main(){
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut r=Input{bytes,at:0};let mut out=Output(Vec::new());
    let commands=r.word();let mut intents=IntentMap::new();
    for command in 0..commands {let op=r.word();out.word(op);match op {
        0=>{let name=r.raw();out.words(encode(&name).0);},
        1=>{let action=r.word();let name=r.string();out.words(intent_key(&name));match action {
            0=>out.optional(intents.insert(&name,r.float())),1=>out.optional(intents.get(&name).copied()),2=>out.optional(intents.remove(&name)),3=>out.word(u32::from(intents.contains_key(&name))),_=>intents.clear(),}
            out.word(intents.len()as u32);out.word(u32::from(intents.is_empty()));
            let key=intent_key(&name);let kind=["negate","abs","oneMinus","clamp","angleFlip","angleRot90","angleRotN90"].iter().position(|v|intent_key(v)==key).map_or(0,|i|i as u32+1);out.word(kind);},
        2=>{let stored=r.word()as usize;let count=r.word()as usize;let records=(0..stored).map(|_|r.words()).collect();let mut pad=Pad::from_storage(records,count);
            for _ in 0..r.word(){let n=r.word();let values:Vec<_>=(0..n).map(|_|r.float()).collect();pad.update(&values);out.pad(&pad);}},
        3=>{let state=XboxState{buttons:r.word()as u16,triggers:[r.word()as u8,r.word()as u8],left:[r.word()as i16,r.word()as i16],right:[r.word()as i16,r.word()as i16]};
            let device=r.word()as u8;let values=xbox::convert(&state,device);out.floats(values);let mut pad=Pad::new();pad.update(&values);out.floats(*GameplayActions::from_pad(&pad).values());},
        4=>{let mut c=DerivedControllerInput::from_words(r.words());if r.word()!=0{c.initialize();}out.words(*c.words());
            for _ in 0..r.word(){let dt=r.float();let s502=r.word()!=0;let s104=r.word()!=0;let s=controller::MagnitudeHeldSettings{attribute:r.optional(),missing_attribute_value:r.float()};
                let mut map=ScriptMap{values:r.floats(),later:r.floats(),states:r.words(),calls:[0;18],log:Vec::new()};c.update(&mut map,dt,s502,s104,&s);out.words(*c.words());out.word(map.log.len()as u32);for v in map.log{out.word(v);}}},
        5=>{let c=DerivedControllerInput::from_words(r.words());let actor=r.word();let physical=r.word();let prefs=riding_intentions::PushPreferences{automatic_push_enabled:r.word()!=0,automatic_push_right:r.word()!=0};let air=r.word()!=0;
            let observation=offboard_intentions::AnalogObservation{effective_skeleton_z:r.floats(),biped_correction:if r.word()!=0{Some(r.floats())}else{None}};
            out.intents(riding_intentions::produce(&c,actor,prefs).iter().map(|v|(v.name,v.value)));
            out.intents(anticipation_intentions::produce(&c).iter().map(|v|(v.name,v.value)));out.intents(manual_intentions::produce(&c,actor).iter().map(|v|(v.name,v.value)));
            out.intents(trick_intentions::produce(&c).iter().map(|v|(v.name,v.value)));out.intents(grind_intentions::produce(&c).iter().map(|v|(v.name,v.value)));
            out.intents(wipeout_intentions::produce(&c,actor,physical).iter().map(|v|(v.name,v.value)));out.intents(offboard_intentions::produce_discrete(&c,actor,air).iter().map(|v|(v.name,v.value)));
            out.intents(offboard_intentions::produce_analog(&c,observation).iter().map(|v|(v.name,v.value)));let st=skate_core::input::steering_intentions::produce(r.floats(),actor);
            out.optional(st.turn);out.optional(st.hard_turn);out.optional(st.hard_turn_crouch);},
        6=>{let value=r.float();let kinds=r.words();let stance=r.stance();for kind in 0..11{out.float(graph_intents::apply_filter(value,kind));}out.float(graph_intents::filter_chain(value,kinds,stance));
            let attached=std::cell::RefCell::new(Vec::new());
            graph_intents::attach_intent(if command%3==0{None}else{Some(value)},command%2!=0,
                |v|attached.borrow_mut().push((0,v)),|v|attached.borrow_mut().push((1,v)));
            let attached=attached.into_inner();out.word(attached.len()as u32);for(n,v)in attached{out.word(n);out.float(v);}
            let create=graph_intents::CreateMgIntent{on_update:r.word()!=0,default_value:r.optional(),scale:r.float(),filters:kinds};let mut created=r.word()!=0;
            for _ in 0..r.word(){let phase=r.word();let action=r.optional();let st=r.stance();out.mutation(match phase{0=>create.enter(&mut created,action,st),1=>create.update(&mut created,action,st),_=>create.exit()});out.word(u32::from(created));}
            let settings=r.filter();let mut state=intent_filter::State{elapsed:r.float(),previous_delta:r.float(),value:r.float()};if r.word()!=0{out.float(state.begin(&settings));}
            for _ in 0..r.word(){let value=r.optional();let dt=r.float();let st=r.stance().unwrap_or((false,false));out.float(state.update(&settings,value,dt,st));out.float(state.elapsed);out.float(state.previous_delta);out.float(state.value);}},
        7=>{let mut h=PadHistory::new();let mut pads=std::array::from_fn(|_|Pad::new());for _ in 0..r.word(){let phase=r.word();if phase==0{
                let mut records=Vec::new();for _ in 0..r.word(){let values:Vec<_>=(0..r.word()).map(|_|r.float()).collect();let mut record=HistoryRecord::new(&values);if r.word()!=0{record.clear_count();}records.push(record);}h.publish(&records);
            }else{out.word(u32::from(h.drain_to_latest(&mut pads)));}out.word(h.read_index()as u32);out.word(h.write_index()as u32);for pad in &pads{out.pad(pad);}}},
        8=>{let mut state=turn_conditioner::State{history:r.floats(),filters:std::array::from_fn(|_|r.floats())};let settings=turn_conditioner::Settings{filter_coefficients:std::array::from_fn(|_|r.floats()),
            input_curve:r.graph(),quickness_curve:r.graph(),speed_curve:r.graph(),smoothing_curve:r.graph(),parameters:r.floats()};
            for _ in 0..r.word(){if r.word()!=0{state.reset_history();}let input=turn_conditioner::Input{body_160:r.float(),body_176:r.float(),bundle_36_field_160:r.float(),bundle_32_field_264:r.float(),animation_152:r.word()as u8,animation_156:r.word()as u8};
                out.floats(turn_conditioner::update(&mut state,input,&settings));out.floats(state.history);for f in state.filters{out.floats(f);}}},
        9=>{let settings=set_turning::Settings{remaps:[r.remap(),r.remap()],speed_tuck:r.graph(),blend:r.graph(),speed_threshold:r.float(),maximum_delta:r.float(),override_turn:r.float()};
            let mut state=set_turning::State{elapsed:r.float(),smoothed:r.float(),mode:r.word()};
            // The recovered owner is one [u32;5] field with no invalid bit patterns.
            // Capture/load its complete storage in the probe, without changing source.
            let mut latch: set_turning::SlideLatch=unsafe{std::mem::transmute(r.words::<5>())};
            for _ in 0..r.word(){let phase=r.word();let side=r.word()!=0;let extra=r.word()!=0;let dt=r.float();match phase {
                0=>state.enter(),1=>latch.reset(),2=>latch.begin_slide(side),3=>latch.grab(side),4=>latch.set_candidate_enabled(side),5=>latch.set_start(side,extra),6=>latch.set_end(side,extra),7=>latch.advance_elapsed(side,dt),_=>{
                    let physical=set_turning::Physical{field_32:r.float(),field_36:r.float(),field_52:r.float(),field_56:r.float(),field_60:r.float(),body_168:r.float()};let stance=r.stance().unwrap_or((false,false));
                    let intents=set_turning::Intents{fakie_turn:r.optional(),mode_0_slide:r.optional(),mode_1_slide:r.optional()};let mut emitted=Vec::new();
                    set_turning::update(&mut state,&mut latch,physical,stance,dt,&settings,intents,|n,v|emitted.push((n,v)));out.word(emitted.len()as u32);for(n,v)in emitted{out.word(n as u32);out.float(v);}
                    out.floats(settings.remaps[0].apply([physical.field_32,physical.field_56]));out.floats(settings.remaps[1].apply([physical.field_36,physical.field_56]));}}
                out.float(state.elapsed);out.float(state.smoothed);out.word(state.mode);let words:[u32;5]=unsafe{std::mem::transmute(latch)};out.words(words);
                out.word(u32::from(latch.captured_fakie()));out.word(u32::from(latch.candidate_enabled()));for side in [false,true]{out.float(latch.elapsed(side));out.word(u32::from(latch.start(side)));out.word(u32::from(latch.end(side)));out.word(u32::from(latch.should_leave(side)));}}},
        10=>{let mut state=body_flip_signal::State::default();for _ in 0..r.word(){let settings=body_flip_signal::Settings{gesture_window:r.float(),takeoff_window:r.float()};if r.word()!=0{state.begin(settings);}
            let present=[r.word()!=0,r.word()!=0];let category=r.word();let dt=r.float();let result=state.update(present,category,dt,settings);out.word(result.map_or(0xffffffff,|i|i as u32));}},
        11=>{let mut state=power_sliding::State{elapsed:r.float(),previous_right:r.float(),previous_left:r.float(),flags:r.word()};let mut latch=r.words();
            let settings=power_sliding::Settings{minimum_speed:r.float(),minimum_slide_time:r.float(),stop_time:r.graph(),speed_response:r.graph(),angle_response:r.graph()};
            for _ in 0..r.word(){let input=power_sliding::Input{category:r.word(),speed:r.float(),right_slide:r.optional(),left_slide:r.optional(),right_query:r.word()!=0,left_query:r.word()!=0,graph_scalar:r.float()};
                let clocks:[f32;3]=r.floats();let mut calls=0;power_sliding::update(&mut state,&mut latch,input,&settings,||{let value=clocks[calls];calls+=1;value});
                out.float(state.elapsed);out.float(state.previous_right);out.float(state.previous_left);out.word(state.flags);out.words(latch);out.word(calls as u32);
                let align=if r.word()!=0{Some((r.floats(),r.floats(),r.word()as u8))}else{None};out.float(power_sliding::alignment(align));}},
        12=>{let s=animation_packet::AnimationPacketFields{stance_byte:r.word()as u8,timestep:r.float(),scalar_10388:r.float(),flags_10375_10496_10784:std::array::from_fn(|_|r.word()as u8),
            vector_10480:r.words(),matrix_10704:std::array::from_fn(|_|r.words()),byte_10768:r.word()as u8,truck_tightness:r.float(),scalar_10792:r.float(),flag_10371:r.word()as u8};
            let mut d=animation_packet::ProcessedPacketFields{flags_2468:r.word(),flags_2476:r.word(),timestep:0.,scalar_2668:0.,vector_1520:[0;4],matrix_1536:[[0;4];4],byte_1600:0,truck_tightness:0.,scalar_2764:0.};
            animation_packet::publish(&s,&mut d);out.word(d.flags_2468);out.word(d.flags_2476);out.float(d.timestep);out.float(d.scalar_2668);out.words(d.vector_1520);for row in d.matrix_1536{out.words(row);}out.word(d.byte_1600 as u32);out.float(d.truck_tightness);out.float(d.scalar_2764);},
        13=>{let mut current=controller::RawControllerInput::from_words(r.words());let previous=controller::RawControllerInput::from_words(r.words());let s502=r.word()!=0;let s104=r.word()!=0;
            let mut map=ScriptMap{values:r.floats(),later:r.floats(),states:r.words(),calls:[0;18],log:Vec::new()};current.update(&previous,&mut map,s502,s104);out.words(*current.words());out.word(map.log.len()as u32);for v in map.log{out.word(v);}},
        _=>panic!("invalid command"),
    }}
    assert_eq!(r.at,r.bytes.len());std::io::stdout().write_all(&out.0).unwrap();
}
