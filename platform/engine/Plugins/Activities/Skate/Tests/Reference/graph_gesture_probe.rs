//! Oracle imports the unchanged original catalog, insertion rows and lifecycle.
#[path="../../crates/skate-host/src/input/gesture_catalog.rs"] mod gesture_catalog;
#[path="../../crates/skate-host/src/input/gesture_mapping_data.rs"] mod gesture_mapping_data;
#[path="../../crates/skate-host/src/input/gesture_mapping.rs"] mod gesture_mapping;
use skate_core::graph::intents::IntentMap;
use gesture_catalog::Group;
use std::io::{Read,Write};
struct Input{data:Vec<u8>,at:usize}
impl Input{
    fn word(&mut self)->u32{let value=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;value}
    fn string(&mut self)->String{let size=self.word()as usize;let value=String::from_utf8(self.data[self.at..self.at+size].to_vec()).unwrap();self.at+=size;value}
    fn map(&mut self,map:&mut IntentMap){for _ in 0..self.word(){let name=self.string();map.insert(&name,f32::from_bits(self.word()));}}
}
struct Output(Vec<u8>);
impl Output{
    fn word(&mut self,value:u32){self.0.extend(value.to_le_bytes());}
    fn text(&mut self,value:&str){self.word(value.len()as u32);self.0.extend(value.as_bytes());}
    fn optional(&mut self,value:Option<&str>){self.word(u32::from(value.is_some()));if let Some(value)=value{self.text(value);}}
    fn snapshot(&mut self,map:&IntentMap,names:&[String]){self.word(map.len()as u32);for name in names{let value=map.get(name);self.word(u32::from(value.is_some()));if let Some(value)=value{self.word(value.to_bits());}}}
}
fn group(value:u32)->Group{match value{0=>Group::Square,1=>Group::Nose,2=>Group::Tail,3=>Group::Nose90,4=>Group::Tail90,5=>Group::NoseN90,6=>Group::TailN90,_=>panic!("invalid group")}}
fn main(){
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let mut out=Output(Vec::new());for _ in 0..r.word(){let op=r.word();out.word(op);match op{
        0=>{match Group::parse(&r.string()){Ok(group)=>{out.word(1);out.word(group as u32);out.text("");},Err(error)=>{out.word(0);out.text(&error);}}},
        1=>{let rows=gesture_mapping_data::TABLES[r.word()as usize];out.word(rows.len()as u32);for &(key,normal,mirrored,dark) in rows{out.text(key);out.text(normal);out.text(mirrored);out.word(dark);}},
        2=>{let group=group(r.word());let mirrored=r.word()!=0;let mut action=IntentMap::new();r.map(&mut action);out.word(u32::from(group.has_intent(|name|action.contains_key(name))));out.optional(gesture_mapping::select(group,&action,mirrored));},
        3=>{let mut state=gesture_mapping::State::default();let mut motion=IntentMap::new();r.map(&mut motion);let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();for _ in 0..r.word(){let phase=r.word();for _ in 0..r.word(){let insert=r.word()!=0;let name=r.string();if insert{motion.insert(&name,f32::from_bits(r.word()));}else{motion.remove(&name);}}
            if phase==0{let group=group(r.word());let mirrored=r.word()!=0;let override_name=if r.word()!=0{Some(r.string())}else{None};let mut action=IntentMap::new();r.map(&mut action);state.begin(group,override_name.as_deref(),&action,&mut motion,mirrored);}else if phase==1{state.update(&mut motion);}else if phase==2{state.end(&mut motion);}else{state=gesture_mapping::State::default();}out.snapshot(&motion,&names);}},
        _=>panic!("unknown operation"),
    }}assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).unwrap();
}
