//! Optional current-runtime differential replay of externally supplied raw Session fixtures.
//! Set HAKUBA_SKATE_PARITY_DIR to an oracle directory under the system temporary folder.
//! This is a diagnostic comparison, not a historical golden or a tolerance-based acceptance claim.
use super::*;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    io::{BufRead, BufReader, BufWriter, Write},
    path::Path,
};

#[derive(Deserialize)]
struct World {
    triangles: Vec<[[f32; 3]; 3]>,
    surfaces: Vec<u16>,
    rails: Vec<Vec<[f32; 3]>>,
    spawn: [f32; 3],
    heading: f32,
}
fn scalar(value: &Value, key: &str, default: f32) -> Result<f32, String> {
    value.get(key).map(|v| serde_json::from_value(v.clone()).map_err(|e| e.to_string())).unwrap_or(Ok(default))
}
fn field<T: serde::de::DeserializeOwned>(value: &Value, key: &str) -> Result<T, String> {
    serde_json::from_value(value.get(key).ok_or_else(|| format!("Missing {key}"))?.clone()).map_err(|e| e.to_string())
}
fn feel(value: Option<&Value>) -> Result<crate::FeelTuning, String> {
    let mut feel = crate::FeelTuning::default();
    if let Some(value) = value {
        for (key, value) in value.as_object().ok_or("Expected feel object")? {
            let f = || serde_json::from_value::<f32>(value.clone()).map_err(|e| e.to_string());
            macro_rules! floats { ($($name:ident),* $(,)?) => { match key.as_str() {
                $(stringify!($name) => feel.$name = f()?,)*
                "tight_flicks" => feel.tight_flicks = f()? != 0.,
                "flick_120hz" => return Err("Legacy flick_120hz fixture option is unsupported; recognizer always uses 120 Hz".into()),
                "drift_powerslide" => feel.drift_powerslide = f()? != 0.,
                "auto_push" | "assisted_air" => {
                    let choice = match f()? { -1. => None, 0. => Some(false), 1. => Some(true), _ => return Err("Invalid feel choice".into()) };
                    if key == "auto_push" { feel.auto_push = choice; } else { feel.assisted_air = choice; }
                }
                _ => return Err(format!("Unknown feel field {key}")),
            } }; }
            floats!(
                flick_radius,
                flick_window,
                flick_pace,
                gravity,
                boneless,
                hippy,
                rail_magnetism,
                grind_pop,
                grind_friction,
                grind_tolerance,
                camera_follow,
                camera_pullback,
                wall_follow,
                braking,
                steering,
                carve,
                grip,
                powerslide,
                rolling_friction,
                hill_speed,
                pump,
                wobble,
                wobble_onset,
                manual_drift,
                landing,
                impact,
                powerslide_turn,
                drift_grip,
                drift_full_grip,
                bowl_boost
            );
        }
    }
    feel.validate()?;
    Ok(feel)
}
fn observation(session: &Session, ready: bool, generation: u32) -> Result<Value, String> {
    let pose = session.pose();
    if !pose.root.is_finite() || !pose.velocity.is_finite() || pose.bones.iter().any(|m| !m.is_finite()) {
        return Err("The skating session produced a nonfinite pose".into());
    }
    let (score, reward, trick) = session.score();
    let pumping = &session.skater.ground.pumping;
    let deck = session.physics.board.part_transforms()[crate::core::physics::board::BodyId::Deck.index()];
    let mut row = json!({"type":if ready {"ready"} else {"pose"}, "tick":pose.tick, "generation":generation,
        "root":pose.root.to_cols_array(), "bones":pose.bones.iter().map(|m|m.to_cols_array()).collect::<Vec<_>>(),
        "velocity":pose.velocity.to_array(), "state":pose.state, "score":score, "reward":reward,
        "trick":trick, "manual":session.manual_balance(),
        "surface":[pose.surface.physics,pose.surface.sound,pose.surface.wheels],
        "boost":{"total":session.boost.total, "pump":pumping.pump_acceleration,
            "intentional":u8::from(pumping.intentional_pumping), "up":deck.basis.columns[1][1]},
        "camera":pose.camera.map(|(position,basis,fov)|json!({"position":position.to_array(),"basis":basis.to_cols_array(),"fov":fov}))});
    if ready {
        row["names"] = json!(pose.names);
        row["reference"] = json!(session.reference_pose()?.iter().map(|m| m.to_cols_array()).collect::<Vec<_>>());
    }
    Ok(row)
}
#[derive(Default)]
struct NumericDelta {
    compared: usize,
    different_f32_words: usize,
    max_absolute: f64,
    first_difference: Option<Value>,
    first_over_1e6: Option<Value>,
    first_over_1e4: Option<Value>,
    first_over_1e2: Option<Value>,
}
impl NumericDelta {
    fn record(&mut self, row: usize, path: &str, rust: f64, cpp: f64) {
        self.compared += 1;
        if (rust as f32).to_bits() == (cpp as f32).to_bits() {
            return;
        }
        self.different_f32_words += 1;
        let absolute = (rust - cpp).abs();
        self.max_absolute = self.max_absolute.max(absolute);
        let witness = json!({"row":row,"field":path,"rust":rust,"cpp":cpp,"absolute":absolute});
        self.first_difference.get_or_insert_with(|| witness.clone());
        if absolute > 1e-6 {
            self.first_over_1e6.get_or_insert_with(|| witness.clone());
        }
        if absolute > 1e-4 {
            self.first_over_1e4.get_or_insert_with(|| witness.clone());
        }
        if absolute > 1e-2 {
            self.first_over_1e2.get_or_insert(witness);
        }
    }
    fn report(&self) -> Value {
        json!({"compared":self.compared,"different_f32_words":self.different_f32_words,"max_absolute":self.max_absolute,
            "first_difference":self.first_difference,"first_over_1e-6":self.first_over_1e6,
            "first_over_1e-4":self.first_over_1e4,"first_over_1e-2":self.first_over_1e2})
    }
}
fn numeric(row: usize, path: &str, rust: &Value, cpp: &Value, delta: &mut NumericDelta) {
    match (rust, cpp) {
        (Value::Number(a), Value::Number(b)) => {
            if let (Some(a), Some(b)) = (a.as_f64(), b.as_f64()) {
                delta.record(row, path, a, b);
            }
        }
        (Value::Array(a), Value::Array(b)) => {
            for (i, (a, b)) in a.iter().zip(b).enumerate() {
                numeric(row, &format!("{path}[{i}]"), a, b, delta);
            }
        }
        (Value::Object(a), Value::Object(b)) => {
            for (key, a) in a {
                if let Some(b) = b.get(key) {
                    numeric(row, &format!("{path}.{key}"), a, b, delta);
                }
            }
        }
        _ => {}
    }
}
fn replay(root: &Path, folder: &Path, prepared: &crate::PreparedResources) -> Result<Value, String> {
    let world: World = serde_json::from_slice(&fs::read(folder.join("world.json")).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let rails = world
        .rails
        .into_iter()
        .enumerate()
        .map(|(i, points)| CollisionRail { id: format!("world_edge_{i}"), points, closed: false })
        .collect();
    let mut session =
        Session::from_resources(prepared, world.triangles, world.surfaces, rails, world.spawn, world.heading)?;
    session.activate(world.spawn, world.heading)?;
    let mut generation = 0;
    let mut elapsed = 0.0f32;
    let mut output = BufWriter::new(fs::File::create(folder.join("rust-output.jsonl")).map_err(|e| e.to_string())?);
    let cpp_file = fs::File::open(folder.join("output.jsonl")).map_err(|e| e.to_string())?;
    let mut cpp = BufReader::new(cpp_file).lines();
    let mut rows = 0;
    let mut states = BTreeMap::<String, usize>::new();
    let mut state_mismatches = 0;
    let mut first_state_mismatch = None;
    let mut categories = BTreeMap::<String, NumericDelta>::new();
    let mut shape_mismatches = Vec::new();
    let mut publish = |session: &Session, ready, generation| -> Result<(), String> {
        let rust = observation(session, ready, generation)?;
        let reference: Value = serde_json::from_str(&cpp.next().ok_or("Missing C++ row")?.map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        serde_json::to_writer(&mut output, &rust).map_err(|e| e.to_string())?;
        writeln!(output).map_err(|e| e.to_string())?;
        if let Some(state) = rust["state"].as_str() {
            *states.entry(state.into()).or_default() += 1;
        }
        if rust["state"] != reference["state"] {
            state_mismatches += 1;
            first_state_mismatch
                .get_or_insert_with(|| json!({"row":rows,"rust":rust["state"],"cpp":reference["state"]}));
        }
        for key in ["root", "velocity", "bones", "camera", "surface", "score", "reward", "manual", "boost", "reference"]
        {
            numeric(rows, key, &rust[key], &reference[key], categories.entry(key.into()).or_default());
        }
        for key in ["type", "tick", "generation", "trick", "names"] {
            if rust[key] != reference[key] && shape_mismatches.len() < 20 {
                shape_mismatches.push(json!({"row":rows,"field":key,"rust":rust[key],"cpp":reference[key]}));
            }
        }
        rows += 1;
        Ok(())
    };
    publish(&session, true, generation)?;
    let input = BufReader::new(fs::File::open(folder.join("input.jsonl")).map_err(|e| e.to_string())?);
    let mut execution_error = None;
    for (index, line) in input.lines().enumerate() {
        let command: Value = serde_json::from_str(&line.map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        let mut apply = || -> Result<bool, String> {
            match command["op"].as_str().ok_or("Missing command op")? {
                "activate" | "configure" => {
                    session.configure(
                        &field::<String>(&command, "difficulty")?,
                        field(&command, "goofy")?,
                        field(&command, "trucks")?,
                    )?;
                    session.tune(
                        scalar(&command, "pop", 1.)?,
                        scalar(&command, "spin", 1.)?,
                        scalar(&command, "push_speed", 1.)?,
                        scalar(&command, "push_power", 1.)?,
                        scalar(&command, "vert_assist", 0.)?,
                    )?;
                    session.set_feel(feel(command.get("feel"))?)?;
                    if command["op"] == "activate" {
                        session.activate(field(&command, "spawn")?, field(&command, "heading")?)?;
                        session.launch(
                            command
                                .get("velocity")
                                .map(|v| serde_json::from_value(v.clone()).map_err(|e| e.to_string()))
                                .unwrap_or(Ok([0.; 3]))?,
                        );
                        generation = command
                            .get("generation")
                            .map(|v| serde_json::from_value(v.clone()).map_err(|e| e.to_string()))
                            .unwrap_or(Ok(0))?;
                        elapsed = 0.;
                        publish(&session, false, generation)?;
                    }
                }
                "step" => {
                    let dt: f32 = field(&command, "dt")?;
                    if !dt.is_finite() || dt < 0. {
                        return Err("Invalid frame interval".into());
                    }
                    if command.get("readings").is_some() {
                        return Err("Device subreadings are not implemented by this fixture replay".into());
                    }
                    let input = Controls {
                        buttons: field(&command, "buttons")?,
                        left: field(&command, "left")?,
                        right: field(&command, "right")?,
                        triggers: field(&command, "triggers")?,
                    };
                    elapsed = (elapsed + dt).min(0.1);
                    while elapsed + 1e-7 >= session.period() {
                        elapsed -= session.period();
                        session.tick(input)?;
                    }
                    publish(&session, false, generation)?;
                }
                "quit" => return Ok(false),
                other => return Err(format!("Unsupported fixture command {other}")),
            }
            Ok(true)
        };
        match apply() {
            Ok(true) => {}
            Ok(false) => break,
            Err(error) => {
                execution_error = Some(json!({"input_line":index+1,"error":error}));
                break;
            }
        }
    }
    drop(publish);
    output.flush().map_err(|e| e.to_string())?;
    let unread_cpp_rows = cpp.count();
    Ok(json!({"fixture":folder.strip_prefix(root).unwrap_or(folder),"rows":rows,"rust_states":states,
        "recognizer":"Rust uses 120 Hz; matching oracle recognizer settings are not established.",
        "state_mismatches":state_mismatches,"first_state_mismatch":first_state_mismatch,
        "numeric":categories.iter().map(|(key,value)|(key.clone(),value.report())).collect::<BTreeMap<_,_>>(),
        "structural_or_label_mismatches_first20":shape_mismatches,"unread_cpp_rows":unread_cpp_rows,
        "execution_error":execution_error}))
}

#[test]
fn removed_flick_rate_fixture_is_rejected() {
    for value in [0, 1] {
        let error = feel(Some(&json!({"flick_120hz": value}))).unwrap_err();
        assert!(error.contains("unsupported"));
    }
}

#[test]
fn current_cpp_raw_fixtures_report_session_deltas() {
    let Some(root) = std::env::var_os("HAKUBA_SKATE_PARITY_DIR") else {
        return;
    };
    let root = fs::canonicalize(root).expect("parity fixture directory");
    let temporary = fs::canonicalize(std::env::temp_dir()).expect("system temporary directory");
    let explicit_tmp = fs::canonicalize("/tmp").expect("temporary fixture directory");
    assert!(
        root.starts_with(temporary) || root.starts_with(explicit_tmp),
        "parity outputs must stay under a temporary directory"
    );
    std::thread::Builder::new().name("raw-session-parity".into()).stack_size(32*1024*1024).spawn(move|| {
        let bytes=fs::read(concat!(env!("CARGO_MANIFEST_DIR"),"/../../assets/simulations/skate-simulation/skate-simulation.skatepack")).expect("exported simulation package");
        let prepared=crate::PreparedResources::from_bytes(bytes).expect("valid current package");
        let mut fixtures:Vec<_>=fs::read_dir(root.join("fixtures")).unwrap().map(|e|e.unwrap().path()).filter(|p|p.is_dir()).collect();
        fixtures.sort();
        let mut reports=BTreeMap::new();
        for folder in fixtures {
            let name=folder.file_name().unwrap().to_string_lossy().into_owned();
            eprintln!("Current C++ comparison fixture: {name}");
            let report=match replay(&root,&folder,&prepared) {Ok(report)=>report,Err(error)=>json!({"fixture":name,"setup_error":error})};
            fs::write(folder.join("rust-comparison.json"),serde_json::to_vec_pretty(&report).unwrap()).unwrap();
            reports.insert(name,report);
            fs::write(root.join("rust-comparison.json"),serde_json::to_vec_pretty(&json!({
                "scope":"Current C++ production versus current Rust port over identical external raw fixtures; no historical or exact-parity claim. Rust always uses 120 Hz flick recognition; an omitted oracle option does not establish matching recognizer settings.",
                "thresholds":"1e-6, 1e-4, and 1e-2 report witnesses only, never acceptance tolerances.",
                "floating_point_environment":"Rust test process environment; C++ oracle explicitly flushes denormals. Any arithmetic difference needs investigation, not a relaxed pass.",
                "fixtures":reports})).unwrap()).unwrap();
        }
    }).unwrap().join().unwrap();
}
