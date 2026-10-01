//! Local pipe adapter. The original session owns physics, input, graphs and poses.
use serde::Deserialize;
use serde_json::{Value, json};
use skate_host::bridge::{Controls, Session};
use std::{io::{self, BufRead, Write}, path::Path};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct World {
    triangles: Vec<[[f32; 3]; 3]>,
    rails: Vec<Vec<[f32; 3]>>,
    spawn: [f32; 3],
    heading: f32,
}
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    Step { dt: f32, buttons: u16, left: [i16; 2], right: [i16; 2], triggers: [u8; 2] },
    Activate { spawn: [f32; 3], heading: f32, goofy: bool, difficulty: String, trucks: f32,
        #[serde(default)] generation: u32, #[serde(default)] velocity: [f32; 3],
        #[serde(default = "one")] pop: f32, #[serde(default = "one")] spin: f32,
        #[serde(default = "one")] push_speed: f32, #[serde(default = "one")] push_power: f32,
        #[serde(default)] vert_assist: f32 },
    Configure { goofy: bool, difficulty: String, trucks: f32,
        #[serde(default = "one")] pop: f32, #[serde(default = "one")] spin: f32,
        #[serde(default = "one")] push_speed: f32, #[serde(default = "one")] push_power: f32,
        #[serde(default)] vert_assist: f32 },
    World { path: String, #[serde(default)] background: bool },
    Launch { velocity: [f32; 3] },
    Suspend {},
    Quit {},
}
fn one() -> f32 { 1. }
fn world(path: &Path) -> Result<World, String> {
    let w: World = serde_json::from_slice(&std::fs::read(path).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    if w.triangles.is_empty() || w.triangles.len() > 500_000 || !w.heading.is_finite()
        || w.spawn.iter().any(|v| !v.is_finite())
        || w.triangles.iter().flatten().flatten().any(|v| !v.is_finite())
        || w.rails.iter().any(|r| r.len() < 2 || r.iter().flatten().any(|v| !v.is_finite())) {
        return Err("Invalid collision snapshot".into());
    }
    Ok(w)
}
fn emit(v: Value) -> Result<(), String> {
    let mut output = io::stdout().lock();
    serde_json::to_writer(&mut output, &v).map_err(|e| e.to_string())?;
    writeln!(output).and_then(|_| output.flush()).map_err(|e| e.to_string())
}
fn publish(s: &Session, ready: bool, generation: u32) -> Result<(), String> {
    let p = s.pose();
    if !p.root.is_finite() || !p.velocity.is_finite() || p.bones.iter().any(|b| !b.is_finite()) {
        return Err("The skating session produced a nonfinite pose".into());
    }
    let (score, reward, trick) = s.score();
    let mut value = json!({"type": if ready {"ready"} else {"pose"}, "tick": p.tick, "generation": generation,
        "root": p.root.to_cols_array(), "bones": p.bones.iter().map(|b| b.to_cols_array()).collect::<Vec<_>>(),
        "velocity": p.velocity.to_array(), "state": p.state, "score": score, "reward": reward, "trick": trick,
        "manual": s.manual_balance(),
        "camera": p.camera.map(|(position,basis,fov)| json!({"position":position.to_array(),"basis":basis.to_cols_array(),"fov":fov}))});
    if ready {
        value["names"] = json!(p.names);
        value["reference"] = json!(s.reference_pose()?.iter().map(|b| b.to_cols_array()).collect::<Vec<_>>());
    }
    emit(value)
}
fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 { return Err("Usage: atelier-skate-runtime ASSETS COLLISION_JSON".into()); }
    let w = world(Path::new(&args[2]))?;
    let mut session = Session::new(Path::new(&args[1]), w.triangles, w.rails, w.spawn, w.heading)?;
    session.activate(w.spawn, w.heading)?;
    let mut generation = 0;
    publish(&session, true, generation)?;
    let mut elapsed = 0.;
    // Collision built on another thread while riding; installed at the next step.
    let (built_tx, built) = std::sync::mpsc::channel();
    for line in io::stdin().lock().lines() {
        let line = line.map_err(|e| e.to_string())?;
        if line.len() > 16_384 { return Err("Input packet is too large".into()); }
        match serde_json::from_str::<Command>(&line).map_err(|e| e.to_string())? {
            Command::Step {dt,buttons,left,right,triggers} => {
                if !dt.is_finite() || dt < 0. { return Err("Invalid frame interval".into()); }
                while let Ok(prepared) = built.try_recv() { session.install_collision(prepared?)?; }
                elapsed = (elapsed + dt).min(0.1);
                while elapsed + 1e-7 >= session.period() {
                    elapsed -= session.period();
                    session.tick(Controls {buttons,left,right,triggers})?;
                }
                // Also acknowledge sub-tick frames so the host can bound outstanding pipe traffic.
                publish(&session, false, generation)?;
            }
            Command::Activate {spawn,heading,goofy,difficulty,trucks,generation: ride,velocity,pop,spin,push_speed,push_power,vert_assist} => {
                if spawn.iter().any(|v| !v.is_finite()) || !heading.is_finite() || !trucks.is_finite() || velocity.iter().any(|v| !v.is_finite()) {
                    return Err("Invalid spawn or equipment".into());
                }
                session.configure(&difficulty, goofy, trucks)?;
                session.tune(pop, spin, push_speed, push_power, vert_assist)?;
                session.activate(spawn, heading)?;
                session.launch(velocity);
                generation = ride;
                elapsed = 0.;
                publish(&session, false, generation)?;
            }
            Command::World {path, background: false} => {
                let w = world(Path::new(&path))?;
                session.install_collision(session.collision_builder().build(w.triangles,w.rails)?)?;
            }
            // The rider keeps the current collision (it still covers him) until this one is parsed and built.
            Command::World {path, background: true} => {
                let (builder, sender) = (session.collision_builder(), built_tx.clone());
                std::thread::Builder::new().name("atelier-skate-world".into()).stack_size(32*1024*1024)
                    .spawn(move || { let _ = sender.send(world(Path::new(&path)).and_then(|w| builder.build(w.triangles,w.rails))); })
                    .map_err(|e| e.to_string())?;
            }
            Command::Configure {goofy,difficulty,trucks,pop,spin,push_speed,push_power,vert_assist} => {
                if !trucks.is_finite() { return Err("Invalid equipment".into()); }
                session.configure(&difficulty, goofy, trucks)?;
                session.tune(pop, spin, push_speed, push_power, vert_assist)?;
            }
            Command::Launch {velocity} => {
                if velocity.iter().any(|v| !v.is_finite()) { return Err("Invalid launch velocity".into()); }
                session.launch(velocity);
            }
            Command::Suspend {} => { session.suspend_input(); elapsed = 0.; }
            Command::Quit {} => break,
        }
    }
    Ok(())
}
fn main() {
    // The reference host also uses a dedicated 32 MiB simulation stack.
    let result = std::thread::Builder::new().name("atelier-skate".into()).stack_size(32*1024*1024)
        .spawn(run).expect("skate worker thread").join();
    let error = match result { Ok(Ok(())) => return, Ok(Err(e)) => e, Err(_) => "Skate worker panicked; see its diagnostic log".into() };
    let _ = emit(json!({"type":"error","message":error}));
    std::process::exit(1);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_out_of_range_controller_packets() {
        assert!(serde_json::from_str::<Command>(r#"{"op":"step","dt":0.02,"buttons":0,"left":[40000,0],"right":[0,0],"triggers":[0,0]}"#).is_err());
        assert!(serde_json::from_str::<Command>(r#"{"op":"quit","unexpected":true}"#).is_err());
    }
    #[test]
    fn hosts_without_the_vert_assist_keep_the_original() {
        let Ok(Command::Configure { vert_assist, .. }) = serde_json::from_str(r#"{"op":"configure","goofy":false,"difficulty":"normal","trucks":0.5}"#)
            else { panic!("configure") };
        assert_eq!(vert_assist, 0.);
    }
}
