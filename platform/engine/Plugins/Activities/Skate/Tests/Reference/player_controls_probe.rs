//! Whole unchanged controls.rs and gesture_input.rs, with declaration-only
//! borrowed call-site records. This proves controls, not upstream physics/camera.
use bevy::prelude::*;
use skate_core::{input::{controller::{ActionMap,DerivedControllerInput},gameplay_map::GameplayActions,tick::TickInput},player::input_phase::PhysicalPlayerInput};
use std::io::{Read,Write};
mod input {
    use bevy::prelude::*;
    #[derive(Resource)] pub(crate) struct PublishedTickInput(pub skate_core::input::tick::TickInput);
    #[path="gesture_input.rs"] pub(crate) mod gesture_input;
}
mod camera {
    #[derive(bevy::prelude::Resource)] pub(crate) struct CameraRuntime {pub frame:Option<skate_core::camera::CameraFrame>}
}
mod physics {
    use bevy::prelude::*;
    pub(crate) struct Simulation {pub time_step:f32}
    pub(crate) struct Step {pub simulation:Simulation}
    pub(crate) struct Settings {pub step:Step,pub input_magnitude_threshold:f32}
    pub(crate) struct AnimationProfile {pub physics_mode:u32}
    #[derive(Resource)] pub(crate) struct GamePhysics {pub settings:Settings,pub animation_profile:AnimationProfile}
    pub(crate) mod skater {
        pub(crate) struct PlayerInput {pub physical:skate_core::player::input_phase::PhysicalPlayerInput}
        #[derive(bevy::prelude::Resource)] pub(crate) struct SkaterRuntime {pub player_input:PlayerInput}
    }
    #[path="controls.rs"] pub(crate) mod controls;
    // Declaration-only visibility bridge. The original pub(super) sample()
    // runs unchanged with its real Bevy resource parameters.
    pub(crate) fn run_sample(world:&mut World) {
        let mut state=bevy::ecs::system::SystemState::<(
            Res<crate::input::PublishedTickInput>,Res<GamePhysics>,
            Res<skater::SkaterRuntime>,Res<crate::camera::CameraRuntime>,
            ResMut<controls::PlayerControls>)>::new(world);
        let(i,p,s,c,m)=state.get_mut(world).unwrap();controls::sample(i,p,s,c,m);
    }
}
struct Input {data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32{let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32{f32::from_bits(self.word())}
    fn string(&mut self)->String{let n=self.word()as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
    fn u64(&mut self)->u64{let low=self.word()as u64;low|((self.word()as u64)<<32)}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32){self.0.extend(v.to_le_bytes());}
    fn string(&mut self,s:&str){self.word(s.len()as u32);self.0.extend(s.as_bytes());}
    fn snapshot(&mut self,p:&physics::controls::PlayerControls,names:&[String]){
        for &v in p.controller.words(){self.word(v);}
        self.word(u32::from(p.offboard_direction.is_some()));if let Some(v)=p.offboard_direction{for f in v{self.word(f.to_bits());}}
        self.word(p.ticks as u32);self.word((p.ticks>>32)as u32);
        for v in [p.actor_flags,u32::from(p.bumper_state_502),u32::from(p.bumper_state_104),u32::from(p.preferences.automatic_push_enabled),u32::from(p.preferences.automatic_push_right)]{self.word(v);}
        self.word(p.intents.len()as u32);for v in &p.intents{self.string(v.name);self.word(v.value.to_bits());}
        self.word(p.action_intents.len()as u32);for n in names{let v=p.action_intents.get(n);self.word(u32::from(v.is_some()));if let Some(v)=v{self.word(v.to_bits());}}
    }
}
struct Map {values:[f32;18],states:[u8;18],trace:Vec<(u32,u32)>}
impl Map {fn read(r:&mut Input)->Self{Self{values:std::array::from_fn(|_|r.float()),states:std::array::from_fn(|_|r.word()as u8),trace:Vec::new()}}}
impl ActionMap for Map {
    fn value(&mut self,a:u32)->f32{self.trace.push((0,a));self.values[(a-64)as usize]}
    fn state(&mut self,a:u32)->u8{self.trace.push((1,a));self.states[(a-64)as usize]}
}
fn frame(r:&mut Input)->(PhysicalPlayerInput,physics::GamePhysics,camera::CameraRuntime){
    let mut p=PhysicalPlayerInput::default();p.state.category_12=r.word();p.state.state_16=r.word();p.off_board.flag_304=r.word()as u8;p.scoring.capabilities_204=r.word();
    let f=physics::GamePhysics{settings:physics::Settings{step:physics::Step{simulation:physics::Simulation{time_step:r.float()}},input_magnitude_threshold:r.float()},animation_profile:physics::AnimationProfile{physics_mode:r.word()}};
    let present=r.word()!=0;let basis=skate_core::math::Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|r.float()))};
    let camera=camera::CameraRuntime{frame:present.then_some(skate_core::camera::CameraFrame{basis,position:[0.;4],previous_basis:basis,previous_position:[0.;4],linear_velocity:[0.;4],angular_velocity:[0.;4],shake_translation:[0.;4],discontinuity:false,field_of_view_degrees:0.,opacity:1.,blur:1.})};(p,f,camera)
}
fn main(){
    std::panic::set_hook(Box::new(|_|{}));let args:Vec<_>=std::env::args().collect();let root=std::path::Path::new(&args[1]);
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();let count=r.word();let mut out=Output(Vec::new());
    let mut world=World::new();world.insert_resource(physics::controls::PlayerControls::default());world.insert_resource(input::PublishedTickInput(TickInput::new(0,GameplayActions::from_values([0.;18]),false)));
    world.insert_resource(physics::GamePhysics{settings:physics::Settings{step:physics::Step{simulation:physics::Simulation{time_step:0.}},input_magnitude_threshold:0.},animation_profile:physics::AnimationProfile{physics_mode:0}});
    world.insert_resource(physics::skater::SkaterRuntime{player_input:physics::skater::PlayerInput{physical:PhysicalPlayerInput::default()}});world.insert_resource(camera::CameraRuntime{frame:None});
    for _ in 0..count {
        let op=r.word();out.word(op);let mut ok=true;let mut error=String::new();let mut trace=Vec::new();let mut extra=Vec::new();
        match op {
            0=>{let loaded=r.word()!=0;world.insert_resource(if loaded{physics::controls::PlayerControls::load(root).unwrap()}else{physics::controls::PlayerControls::default()});},
            1=>{let mut p=world.resource_mut::<physics::controls::PlayerControls>();p.actor_flags=r.word();p.bumper_state_502=r.word()!=0;p.bumper_state_104=r.word()!=0;p.preferences.automatic_push_enabled=r.word()!=0;p.preferences.automatic_push_right=r.word()!=0;p.ticks=r.u64();p.controller=DerivedControllerInput::from_words(std::array::from_fn(|_|r.word()));},
            2=>{let dt=r.float();let threshold=r.float();let caps=r.word();let mut map=Map::read(&mut r);world.resource_mut::<physics::controls::PlayerControls>().update(&mut map,dt,threshold,caps);trace=map.trace;},
            3=>{let(p,f,c)=frame(&mut r);let mut map=Map::read(&mut r);world.insert_resource(f);world.insert_resource(c);world.resource_mut::<physics::skater::SkaterRuntime>().player_input.physical=p;
                let mut controls=world.remove_resource::<physics::controls::PlayerControls>().unwrap();let result=controls.update_for_physics(&mut map,world.resource(),world.resource(),world.resource());world.insert_resource(controls);if let Err(e)=result{ok=false;error=e;}trace=map.trace;},
            4=>{let mut map=Map::read(&mut r);{let p=world.resource::<physics::controls::PlayerControls>();let mut actions=p.simulation_actions(&mut map);for _ in 0..r.word(){let kind=r.word();let a=r.word();extra.push(if kind==0{actions.value(a).to_bits()}else{actions.state(a)as u32});}}trace=map.trace;},
            5=>{let difficulty=r.word();let state=r.word();world.resource_mut::<physics::controls::PlayerControls>().publish_gestures(difficulty,state);},
            6=>{let n=r.string();let v=r.float();world.resource_mut::<physics::controls::PlayerControls>().action_intents.insert(&n,v);},
            7=>{let(p,f,c)=frame(&mut r);let tick=r.u64();let available=r.word()!=0;let values=std::array::from_fn(|_|r.float());world.insert_resource(f);world.insert_resource(c);world.resource_mut::<physics::skater::SkaterRuntime>().player_input.physical=p;world.insert_resource(input::PublishedTickInput(TickInput::new(tick,GameplayActions::from_values(values),available)));
                let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||physics::run_sample(&mut world)));if let Err(e)=result{ok=false;error=if let Some(v)=e.downcast_ref::<String>(){v.clone()}else{e.downcast_ref::<&str>().unwrap().to_string()};}},
            _=>panic!("unknown operation"),
        }
        out.word(u32::from(ok));out.string(&error);out.word(extra.len()as u32);for v in extra{out.word(v);}out.word(trace.len()as u32);for(k,a)in trace{out.word(k);out.word(a);}out.snapshot(world.resource(),&names);
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).unwrap();
}
