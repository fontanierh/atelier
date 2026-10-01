//! Verbatim original GameInputManager/listener publication, with PAT/JSON data.
#[path="../../crates/skate-host/src/input/gesture_input.rs"] mod gesture_input;
use skate_core::graph::intents::IntentMap;
use std::io::{Read,Write};
struct Input{data:Vec<u8>,at:usize}
impl Input{
    fn word(&mut self)->u32{let value=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;value}
    fn float(&mut self)->f32{f32::from_bits(self.word())}
    fn string(&mut self)->String{let size=self.word()as usize;let value=String::from_utf8(self.data[self.at..self.at+size].to_vec()).unwrap();self.at+=size;value}
}
struct Output(Vec<u8>);
impl Output{
    fn word(&mut self,value:u32){self.0.extend(value.to_le_bytes());}
    fn snapshot(&mut self,map:&IntentMap,names:&[String]){self.word(map.len()as u32);for name in names{let value=map.get(name);self.word(u32::from(value.is_some()));if let Some(value)=value{self.word(value.to_bits());}}}
}
fn main(){
    let args:Vec<_>=std::env::args().collect();let root=std::path::Path::new(&args[1]);let mut publication=gesture_input::GestureInput::load(root).unwrap();
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let mut out=Output(Vec::new());let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();
    for _ in 0..r.word(){let operation=r.word();out.word(operation);match operation{
        0=>publication=gesture_input::GestureInput::load(root).unwrap(),
        1=>{let axes=std::array::from_fn(|_|std::array::from_fn(|_|r.float()));let difficulty=r.word();let flags=r.word();let state=r.word();let mut action=IntentMap::new();for _ in 0..r.word(){let name=r.string();action.insert(&name,r.float());}
            publication.publish(axes,difficulty,flags,state,&mut action);out.snapshot(&action,&names);},
        _=>panic!("unknown operation"),
    }}assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).unwrap();
}
