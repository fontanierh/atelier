// Appended to an exact hashed prefix of the existing facade probe, followed by
// its explicit caller-publication helper. Every production host stays intact.
use graph_host::{motion::MotionHost,motion_gameplay_conditions::GameplayConditions};
use skate_core::animation::skeleton_input::name::encode;
impl Input { fn vector3(&mut self)->[f32;3] {std::array::from_fn(|_|self.float())} }
fn complete_snapshot(out:&mut Output,actor:&SkaterAnimation,reset:&AdditionalResetFields,names:&[String]) {
    out.snapshot(actor,reset,names);
    let h=&actor.motion;
    let (registered,instances)=h.migration_complete_registration();out.word(registered.len() as u32);for v in registered {out.word(u32::from(v));}out.word(instances as u32);
    out.word(u32::from(h.wipeout_controls.seed_from_air_tweak));out.word(u32::from(h.wipeout_controls.gestures_enabled));for v in h.wipeout_controls.gesture {out.float(v);}
    let mut mask=0u32;
    for (bit,present) in [h.animation.skater_animation_flags.is_some(),h.playback_context.is_mirrored.is_some(),h.playback_context.board_available.is_some(),h.gameplay_conditions.is_some(),h.condition_inputs.physical_state.is_some(),h.bump_acceleration.is_some(),h.offboard_cadence_phase.is_some(),h.runout_physical.is_some(),h.air_leg_physical.is_some(),h.prelanding_physical.is_some(),h.native_physical.is_some(),h.landing_physical.is_some(),h.grind_physical.is_some(),h.toggle_board_physical.is_some(),h.wipeout_physical.is_some()].into_iter().enumerate() {if present {mask|=1<<bit;}}
    out.word(mask);
    let pending=h.animation.migration_complete_pending();out.word(pending.len() as u32);for v in pending {for word in v.name.0 {out.word(word);}out.float(v.value);out.word(u32::from(v.normalized));out.word(v.sequence_id as u32);}
    for name in ["fakie","AirBodyTweak","RetrieveBoard","IA_BODYSPIN_OLLIE_FS_0_N","IA_BODYSPIN_OLLIE_BS_0_N"] {out.word(u32::from(h.animation.channels.has(name)));out.float(h.animation.channels.elapsed(name));out.float(h.animation.channels.remaining(name));out.word(u32::from(h.animation.channels.in_transition(name)));}
}
fn reset_fields()->AdditionalResetFields {
    AdditionalResetFields{compression:0.137,foot_ik_influence:[0.317,0.731],next_step_position_valid:true,actor_flag_1904_bit23:true,actor_flag_1908_bit2:true,external_impulse_active:true,external_physics_input_active:true,externally_controlled:true,prevent_manual_respawn:true,ignore_respawn_reset_button:255,force_braking:true,truck_tightness:0.113,wheel_hardness:0.719,auxiliary_vectors:[[0.137,0.317,0.731,0.113];6],requested_physics_mode:0xdeadbeef}
}
fn complete_run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=Path::new(&args[1]);let fixtures=Path::new(&args[2]);let data=Collections::load(assets)?;let source=AnimationSource::load(assets)?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;if bytes.get(..8)!=Some(b"ATASKTR4") {return Err("Invalid complete facade protocol".into());}let mut input=Input{data:bytes,at:8};let mut out=Output(Vec::new(),true,true);
    for _ in 0..input.word() {let _=input.string();}let names:Vec<_>=(0..input.word()).map(|_|input.string()).collect();let count=input.word();out.word(count);
    let graphs=|id:u32|->Result<graph_runtime::StockGraphs,String> {Ok(graph_runtime::StockGraphs{action:load_graph(&fixtures.join(format!("actor-{id}.action.reference")))?,motion:load_graph(&fixtures.join(format!("actor-{id}.motion.reference")))?})};
    for _ in 0..count {
        let id=input.word();let pro=input.string();let mut graph=graphs(id)?;
        let mut actor=match SkaterAnimation::from_source(&data,&graph,pro.as_bytes(),source.clone()) {Ok(v)=>{out.status(Ok(()));v},Err(e)=>{out.status(Err(e.clone()));return Err(e)}};
        let mut reset=reset_fields();let steps=input.word();out.word(steps);complete_snapshot(&mut out,&actor,&reset,&names);
        for _ in 0..steps {
            match input.word() {
                0=>{let dt=input.float();let action=input.map();let p=input.physical();out.status(actor.advance(&graph,dt,&action,p,&mut reset));},
                1=>{let natural=input.word();let style=input.word();actor.set_customisation(natural,style);out.status(Ok(()));},
                2=>{actor.request_checkpoint_stance(input.word());out.status(Ok(()));},
                3=>{let name=input.string();let animation=input.string();let settings=input.channel();match actor.motion.animation.new_channel(&name,&animation,settings) {Ok(created)=>{out.word(1);out.word(u32::from(created));},Err(e)=>out.status(Err(e))}},
                4=>{let name=input.string();let time=input.float();let last=input.boolean();actor.motion.animation.channels.end_with(&name,time,last);out.status(Ok(()));},
                5=>{match actor.evaluate_initial_pose() {Ok(h)=>{out.word(1);out.matrices(&h);},Err(e)=>out.status(Err(e))}},
                6=>{actor.motion.animation.posture.set_profile(input.word());out.status(Ok(()));},
                7=>{actor.action_controller.end_all_behaviors(&mut actor.action);actor.motion_controller.end_all_behaviors(&mut actor.motion);out.status(Ok(()));},
                8=>{input.extra_physical(&mut actor.motion);out.status(Ok(()));},
                9=>{input.interaction_physical(&mut actor.motion);out.status(Ok(()));},
                10=>{physical(&mut input,&mut actor.motion);out.status(Ok(()));},
                11=>{
                    let id=input.word();let settings_id=input.word();let replacement=graphs(id)?;
                    let alternate=if settings_id==u32::MAX {None}else{Some(Collections::load(&fixtures.join(format!("settings-{settings_id}/assets")))?)};
                    match SkaterAnimation::from_source(alternate.as_ref().unwrap_or(&data),&replacement,pro.as_bytes(),source.clone()) {Ok(v)=>{actor=v;graph=replacement;out.status(Ok(()));},Err(e)=>out.status(Err(e))}
                },
                _=>return Err("Invalid complete facade opcode".into()),
            }
            complete_snapshot(&mut out,&actor,&reset,&names);
        }
    }
    if input.at!=input.data.len() {return Err("Complete facade input trailing bytes".into());}std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=complete_run() {eprintln!("{e}");std::process::exit(2);}}
