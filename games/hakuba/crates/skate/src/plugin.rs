//! The in-process skating host: exclusive movement, fixed simulation ticks and one-frame-behind presentation.
#[path = "frame.rs"]
mod frame;
#[path = "lost.rs"]
mod lost;
#[path = "places.rs"]
mod places;
#[path = "preferences.rs"]
mod preferences;
#[path = "retarget.rs"]
mod retarget;
#[path = "ride_input.rs"]
mod ride_input;

use crate::{Controls, Pose, Session};
use bevy::app::AnimationSystems;
use bevy::asset::{AssetLoader, LoadContext, io::Reader};
use bevy::gltf::{Gltf, GltfExtras};
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use hakuba_characters::{Play, PoseOverride, PoseSystems, Rig, SolvedPose};
use hakuba_player::{MovementOwner, Player, PlayerSystems};
use hakuba_screens::{DevMode, Pause, Screen};
use hakuba_world::{CollisionFocus, Ground, Unready, WorldCollision};
use ride_input::RideInput;
pub use ride_input::StickReading;

const PACKAGE: &str = "simulations/skate-simulation/skate-simulation.skatepack";
const BOARD: &str = "equipment/skateboard/skateboard.glb";
const PARTS: [&str; 7] = [
    "SKATEBOARD_ROOT",
    "TRUCK_FRONT",
    "TRUCK_BACK",
    "RIGHT_WHEELFRONT",
    "LEFT_WHEELFRONT",
    "RIGHT_WHEELBACK",
    "LEFT_WHEELBACK",
];

#[derive(SystemSet, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SkateSystems {
    Simulation,
}

pub struct SkatePlugin;
impl Plugin for SkatePlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<StickReading>()
            .add_message::<crate::AudioEvent>()
            .init_asset::<Package>()
            .init_asset_loader::<PackageLoader>()
            .init_resource::<Ride>()
            .init_resource::<RideInput>()
            .init_resource::<SkateStatus>()
            .init_resource::<BoardGrip>()
            .init_resource::<places::Places>()
            .add_systems(Startup, load)
            .add_systems(OnEnter(Screen::World), (spawn, places::spawn))
            .add_systems(OnExit(Screen::World), clear)
            .add_systems(
                PreUpdate,
                places::capture_close
                    .after(bevy::input::InputSystems)
                    .run_if(in_state(Screen::World))
                    .run_if(in_state(Pause::Playing))
                    .run_if(in_state(DevMode::Off)),
            )
            .add_systems(OnEnter(DevMode::On), release)
            .init_resource::<Spare>()
            .init_resource::<Carry>()
            // From the title on: the first build reads the scoring tables, best done before the world is shown.
            .add_systems(Update, build_spare)
            .add_systems(Update, (prepare, read_holder).run_if(in_state(Screen::World)))
            .add_systems(
                Update,
                (
                    ride_input::read,
                    places::read,
                    keep_collision,
                    transition,
                    apply_preferences,
                    simulate.in_set(SkateSystems::Simulation),
                )
                    .chain()
                    .after(PlayerSystems::Input)
                    .before(PlayerSystems::Movement)
                    .run_if(in_state(Screen::World))
                    .run_if(in_state(Pause::Playing))
                    .run_if(in_state(DevMode::Off)),
            )
            .add_systems(
                PostUpdate,
                (present, carry)
                    .chain()
                    .after(AnimationSystems)
                    .before(PoseSystems::Apply)
                    .before(TransformSystems::Propagate)
                    .run_if(in_state(Screen::World))
                    .run_if(in_state(DevMode::Off)),
            )
            .add_systems(Update, (hud, places::hud).run_if(in_state(Screen::World)));
    }
}

/// Public, read-only presentation and replay telemetry; all values come from the solved session.
#[derive(Resource, Debug)]
pub struct SkateStatus {
    pub active: bool,
    pub bailed: bool,
    pub recovering: bool,
    pub on_foot: bool,
    pub on_board: bool,
    pub stowed: bool,
    pub waiting_for_collision: bool,
    pub tick: u64,
    pub state: String,
    pub speed_mps: f32,
    pub score: f32,
    pub reward: f32,
    pub trick: String,
    pub telemetry: crate::SkateTelemetry,
    pub audio: crate::AudioFrame,
    pub balance: f32,
    pub surface: u16,
    pub wheels: u32,
    pub failure: Option<String>,
}

impl Default for SkateStatus {
    fn default() -> Self {
        Self {
            active: false,
            bailed: false,
            recovering: false,
            on_foot: false,
            on_board: false,
            stowed: true,
            waiting_for_collision: false,
            tick: 0,
            state: String::new(),
            speed_mps: 0.,
            score: 0.,
            reward: 0.,
            trick: String::new(),
            telemetry: Default::default(),
            audio: Default::default(),
            balance: 0.,
            surface: 0,
            wheels: 0,
            failure: None,
        }
    }
}

#[derive(Asset, TypePath)]
struct Package(crate::PreparedResources);
#[derive(Default, TypePath)]
struct PackageLoader;
impl AssetLoader for PackageLoader {
    type Asset = Package;
    type Settings = ();
    type Error = BevyError;
    async fn load(&self, reader: &mut dyn Reader, _: &(), _: &mut LoadContext<'_>) -> Result<Package, BevyError> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        Ok(Package(crate::PreparedResources::from_bytes(bytes).map_err(std::io::Error::other)?))
    }
    fn extensions(&self) -> &[&str] {
        &["skatepack"]
    }
}
#[derive(Resource)]
struct AssetsToLoad {
    package: Handle<Package>,
    board: Handle<Gltf>,
}
fn load(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(AssetsToLoad { package: assets.load(PACKAGE), board: assets.load(BOARD) });
}

#[derive(Resource, Default)]
struct BoardGrip(Option<retarget::DeckProfile>);
#[derive(Component)]
struct BoardPart(&'static str);
#[derive(Component)]
struct Preparing;
#[derive(Component)]
struct RideHud;
fn spawn(mut commands: Commands) {
    commands.spawn((Name::new("Skating assets"), Preparing, Unready, DespawnOnExit(Screen::World)));
    commands.spawn((
        RideHud,
        DespawnOnExit(Screen::World),
        Node { position_type: PositionType::Absolute, left: px(22), bottom: px(20), ..default() },
        Text::new("Triangle / V | skateboard"),
        TextFont { font_size: FontSize::Px(18.), ..default() },
        TextColor(Color::WHITE),
    ));
}
fn prepare(
    mut commands: Commands,
    assets: Res<AssetServer>,
    handles: Res<AssetsToLoad>,
    packages: Res<Assets<Package>>,
    models: Res<Assets<Gltf>>,
    waiting: Query<Entity, With<Preparing>>,
    mut status: ResMut<SkateStatus>,
) {
    if waiting.is_empty() {
        return;
    }
    for (failed, path) in [
        (assets.load_state(&handles.package).is_failed(), PACKAGE),
        (assets.load_state(&handles.board).is_failed(), BOARD),
    ] {
        if failed {
            if status.failure.as_deref() != Some(path) {
                error!("Skating asset failed: {path}");
                status.failure = Some(path.into());
            }
            for entity in &waiting {
                commands.entity(entity).despawn();
            }
            return;
        }
    }
    let (Some(_), Some(model)) = (packages.get(&handles.package), models.get(&handles.board)) else { return };
    if PARTS.iter().any(|name| !model.named_scenes.contains_key(*name)) {
        let error = format!("{BOARD}: missing articulated board scene");
        if status.failure.as_ref() != Some(&error) {
            error!("{error}");
            status.failure = Some(error);
        }
        for entity in &waiting {
            commands.entity(entity).despawn();
        }
        return;
    }
    for name in PARTS {
        commands.spawn((
            Name::new(name),
            BoardPart(name),
            DespawnOnExit(Screen::World),
            WorldAssetRoot(model.named_scenes[name].clone()),
            Transform::from_scale(Vec3::splat(0.001)),
            Visibility::default(),
        ));
    }
    for entity in &waiting {
        commands.entity(entity).despawn();
    }
}

/// A session built on another thread while the player walks, so mounting the board only swaps in the collision
/// around them instead of freezing the game for the seconds a fresh session takes to build.
#[derive(Resource, Default)]
struct Spare {
    session: std::sync::Arc<std::sync::Mutex<Option<Result<Session, String>>>>,
    /// A session is being built, waits in `session`, or rides: never build a second.
    started: bool,
    builder: Option<crate::CollisionBuilder>,
    /// The collision around the walking player, kept current on another thread so a mount only installs it.
    built: BuiltCollision,
    building: Option<u64>,
    prepared: Option<(u64, crate::PreparedCollision)>,
}

/// While the player walks, keeps the collision around them built for the spare session, so the board can be mounted
/// on the frame it is asked for.
fn keep_collision(
    mut spare: ResMut<Spare>,
    mut focus: ResMut<CollisionFocus>,
    collision: Res<WorldCollision>,
    players: Query<(&Player, &Transform)>,
) {
    let Ok((player, at)) = players.single() else { return };
    if player.owner == MovementOwner::Skating {
        return;
    }
    // Only the ground under the walker: the ride widens it once mounted. A wide focus would pin far tiles at full
    // detail and republish collision as the player walks.
    focus.radius_m = WALK_FOCUS_M;
    focus.request(at.translation, Vec3::ZERO);
    if spare.builder.is_none() {
        let builder =
            spare.session.lock().unwrap().as_ref().and_then(|s| s.as_ref().ok()).map(|s| s.collision_builder());
        spare.builder = builder;
    }
    let Some(builder) = spare.builder else { return };
    let landed = spare.built.lock().unwrap().take();
    if let Some((generation, prepared)) = landed {
        spare.building = None;
        match prepared {
            Ok(prepared) => spare.prepared = Some((generation, prepared)),
            Err(error) => warn!("the spare ride collision failed: {error}"),
        }
    }
    if spare.building.is_none()
        && !collision.snapshot.triangles.is_empty()
        && spare.prepared.as_ref().map(|p| p.0) != Some(collision.generation)
    {
        let (snapshot, generation, slot) = (collision.snapshot.clone(), collision.generation, spare.built.clone());
        spare.building = Some(generation);
        std::thread::spawn(move || {
            hakuba_screens::run_this_thread_as(hakuba_screens::ThreadClass::Utility);
            let (triangles, surfaces, rails) = simulation_collision(&snapshot);
            *slot.lock().unwrap() = Some((generation, builder.build(triangles, surfaces, rails)));
        });
    }
}

/// How far around the walker collision is kept for a mount, and around the rider once mounted.
const WALK_FOCUS_M: f32 = 16.;
const RIDE_FOCUS_M: f32 = 48.;

fn build_spare(
    mut spare: ResMut<Spare>,
    handles: Res<AssetsToLoad>,
    packages: Res<Assets<Package>>,
    players: Query<&Player>,
) {
    // Never while skating: building takes seconds of a core the ride needs.
    if spare.started || players.iter().any(|player| player.owner == MovementOwner::Skating) {
        return;
    }
    let Some(package) = packages.get(&handles.package) else { return };
    let (slot, resources) = (spare.session.clone(), package.0.clone());
    spare.started = true;
    std::thread::spawn(move || {
        hakuba_screens::run_this_thread_as(hakuba_screens::ThreadClass::Utility);
        // A small floor stands in for the world until the real collision is installed at mount.
        let floor = vec![[[-8., 0., -8.], [8., 0., -8.], [8., 0., 8.]], [[-8., 0., -8.], [8., 0., 8.], [-8., 0., 8.]]];
        let t = std::time::Instant::now();
        let session = Session::from_resources(&resources, floor, vec![1 << 7; 2], Vec::new(), [0.; 3], 0.);
        match &session {
            Ok(_) => info!("spare skate session built in {:?}", t.elapsed()),
            Err(error) => warn!("spare skate session failed: {error}"),
        }
        *slot.lock().unwrap() = Some(session);
    });
}

/// The world collision as the simulation takes it: its triangles turned into the simulation's frame and winding.
fn simulation_collision(
    snapshot: &hakuba_world::CollisionSnapshot,
) -> (Vec<[[f32; 3]; 3]>, Vec<u16>, Vec<crate::CollisionRail>) {
    let triangles = snapshot
        .triangles
        .iter()
        .map(|t| [t.points[0], t.points[2], t.points[1]].map(|p| frame::simulation_point(p).to_array()))
        .collect();
    let rails = snapshot
        .rails
        .iter()
        .map(|r| crate::CollisionRail {
            id: r.id.clone(),
            closed: r.closed,
            points: r.points.iter().map(|p| frame::simulation_point(Vec3::from(*p)).to_array()).collect(),
        })
        .collect();
    (triangles, snapshot.triangles.iter().map(|t| t.surface).collect(), rails)
}

type BuiltCollision = std::sync::Arc<std::sync::Mutex<Option<(u64, Result<crate::PreparedCollision, String>)>>>;

#[derive(Resource, Default)]
struct Ride {
    session: Option<Session>,
    /// The generation of world collision being built on another thread, and where it lands.
    building: Option<u64>,
    built: BuiltCollision,
    previous: Option<Pose>,
    current: Option<Pose>,
    retarget: Option<retarget::Retarget>,
    accumulator: f32,
    generation: u64,
    mounting: bool,
    bail_time: f32,
    stowing: bool,
    mounting_transition: bool,
    offboard_time: f32,
    toggle_ticks: u8,
    desired_on_foot: Option<bool>,
    toggle_cooldown: u8,
    floor: lost::HeldFloor,
    last_shown: Option<Pose>,
    marker_returns: u64,
    marker_relocating: bool,
    marker_teleport_seen: bool,
    recovery_owned: bool,
}

#[allow(clippy::too_many_arguments)]
fn transition(
    mut commands: Commands,
    mut ride: ResMut<Ride>,
    mut input: ResMut<RideInput>,
    mut status: ResMut<SkateStatus>,
    mut focus: ResMut<CollisionFocus>,
    collision: Res<WorldCollision>,
    handles: Res<AssetsToLoad>,
    packages: Res<Assets<Package>>,
    models: Res<Assets<Gltf>>,
    mut players: Query<(&mut Player, &mut Transform)>,
    rigs: Query<&Rig>,
    mut ground: Ground,
    settings: Res<hakuba_settings::Settings>,
    grip: Res<BoardGrip>,
    mut spare: ResMut<Spare>,
    mut carry: ResMut<Carry>,
) {
    let Ok((mut player, mut at)) = players.single_mut() else { return };
    if player.owner == MovementOwner::Skating && status.failure.is_some() {
        let failure = status.failure.clone();
        hand_back(
            &mut commands,
            &mut ride,
            &mut player,
            &mut at,
            &mut focus,
            &mut status,
            &mut ground,
            &mut spare,
            None,
        );
        status.failure = failure;
        return;
    }
    if input.stow && player.owner == MovementOwner::Skating {
        ride.stowing = true;
        ride.mounting_transition = false;
        ride.toggle_ticks = 0;
        ride.desired_on_foot = if status.on_foot { None } else { Some(true) };
        ride.toggle_cooldown = 0;
    }
    if input.toggle {
        if status.failure.is_some() {
            return;
        }
        if player.owner == MovementOwner::Skating {
            // Off the board at once, where the rider is, carrying it, with every move of walking back.
            input.toggle = false;
            let held = Some(&mut *carry);
            hand_back(
                &mut commands,
                &mut ride,
                &mut player,
                &mut at,
                &mut focus,
                &mut status,
                &mut ground,
                &mut spare,
                held,
            );
            return;
        }
        ride.mounting = !ride.mounting;
        if !ride.mounting {
            status.waiting_for_collision = false;
        }
    }
    if ride.mounting_transition && ride.current.as_ref().is_some_and(|pose| pose.state == "BipedGround") {
        ride.desired_on_foot = Some(false);
        ride.toggle_cooldown = 0;
        ride.mounting_transition = false;
    }
    if should_hand_back(ride.stowing, ride.offboard_time) {
        hand_back(
            &mut commands,
            &mut ride,
            &mut player,
            &mut at,
            &mut focus,
            &mut status,
            &mut ground,
            &mut spare,
            None,
        );
        return;
    }
    if input.recover && player.owner == MovementOwner::Skating {
        // Recovery stays in the native graph so the physical rider gets up where it fell.
        input.packet.buttons |= 0x1000;
    }
    if !ride.mounting || grip.0.is_none() {
        return;
    }
    focus.request(at.translation, player.motion.velocity);
    status.waiting_for_collision = true;
    if !collision.snapshot.covers(at.translation) {
        return;
    }
    let (Some(package), Some(_), Ok(rig)) =
        (packages.get(&handles.package), models.get(&handles.board), rigs.get(player.body))
    else {
        return;
    };
    let heading = frame::simulation_point(at.rotation * Vec3::Z);
    let spawn = frame::simulation_point(at.translation).to_array();
    let mut generation = collision.generation;
    let result = (|| {
        let t = std::time::Instant::now();
        let ready = spare.session.lock().unwrap().take();
        let mut session = match ready {
            Some(Ok(mut session)) => {
                // The collision kept around the walking player is installed as it is: the ride replaces it on
                // another thread if the world has moved on since.
                match spare.prepared.take() {
                    Some((built, prepared)) => {
                        generation = built;
                        session.install_collision(prepared)?;
                    }
                    None => {
                        let (triangles, surfaces, rails) = simulation_collision(&collision.snapshot);
                        warn!("MOUNT_TIMING no prepared collision: building it now");
                        session.install_collision(session.collision_builder().build(triangles, surfaces, rails)?)?;
                    }
                }
                debug!("MOUNT_TIMING spare install {:?}", t.elapsed());
                session
            }
            other => {
                if other.is_some() {
                    spare.started = false;
                }
                warn!("MOUNT_TIMING no spare session: building one now");
                let (triangles, surfaces, rails) = simulation_collision(&collision.snapshot);
                Session::from_resources(&package.0, triangles, surfaces, rails, spawn, heading.x.atan2(heading.z))?
            }
        };
        debug!("MOUNT_TIMING from_resources {:?}", t.elapsed());
        preferences::apply(&mut session, &settings.skate)?;
        debug!("MOUNT_TIMING preferences {:?}", t.elapsed());
        let pose = session.activate(spawn, heading.x.atan2(heading.z))?;
        debug!("MOUNT_TIMING activate {:?}", t.elapsed());
        places::restore(&mut session, &settings)?;
        session.launch(frame::simulation_point(player.motion.velocity).to_array());
        info!(
            "MOUNT_AT walker {:.2} yaw {:.0} rider {:.2}",
            at.translation,
            heading.x.atan2(heading.z).to_degrees(),
            frame::world_point(pose.root.w_axis.truncate())
        );
        let retarget = retarget::Retarget::bind(rig, &pose.names, &session.reference_pose()?)?;
        debug!("MOUNT_TIMING retarget {:?}", t.elapsed());
        Ok::<_, String>((session, pose, retarget))
    })();
    match result {
        Ok((session, pose, retarget)) => {
            ride.previous = None;
            ride.current = Some(pose);
            ride.session = Some(session);
            ride.retarget = Some(retarget);
            ride.accumulator = 0.;
            ride.generation = generation;
            ride.mounting = false;
            ride.bail_time = 0.;
            ride.toggle_ticks = 0;
            ride.offboard_time = 0.;
            ride.mounting_transition = false;
            carry.held = false;
            player.owner = MovementOwner::Skating;
            commands.entity(player.body).insert((PoseOverride, SolvedPose::default()));
            status.active = true;
            status.stowed = false;
            status.waiting_for_collision = false;
            status.failure = None;
        }
        Err(error) => {
            error!("Cannot start skating: {error}");
            status.failure = Some(error);
            ride.mounting = false;
            focus.clear();
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn simulate(
    time: Res<Time>,
    real_time: Res<Time<Real>>,
    mut ride: ResMut<Ride>,
    mut input: ResMut<RideInput>,
    mut status: ResMut<SkateStatus>,
    mut focus: ResMut<CollisionFocus>,
    collision: Res<WorldCollision>,
    players: Query<&Player>,
    windows: Query<&Window, With<bevy::window::PrimaryWindow>>,
    mut ground: Ground,
    mut audio_events: MessageWriter<crate::AudioEvent>,
    mut places: ResMut<places::Places>,
    mut settings: ResMut<hakuba_settings::Settings>,
) {
    let Ok(player) = players.single() else { return };
    if player.owner != MovementOwner::Skating || status.failure.is_some() {
        return;
    }
    let Some(current) = ride.current.as_ref() else { return };
    let position = frame::world_point(current.root.w_axis.truncate());
    let velocity = if status.on_foot {
        ride.previous.as_ref().map_or(Vec3::ZERO, |previous| {
            let ticks = current.tick.saturating_sub(previous.tick).max(1) as f32;
            frame::world_point(current.root.w_axis.truncate() - previous.root.w_axis.truncate())
                / (ride.session.as_ref().unwrap().period() * ticks)
        })
    } else {
        frame::world_point(current.velocity)
    };
    let target = places::target(&places, &settings);
    focus.radius_m = RIDE_FOCUS_M;
    focus.request(position, velocity);
    focus.destination = target;
    let was_waiting = status.waiting_for_collision;
    // Only the ground the rider is about to reach matters: a tile still loading at the far edge of the focus must not
    // stop the ride.
    status.waiting_for_collision = !collision.snapshot.covers(position + velocity * 0.1)
        || target.is_some_and(|target| !collision.snapshot.covers(target));
    if status.waiting_for_collision {
        if !was_waiting {
            warn!("RIDE_WAIT the ride stops for collision at {position:.1} moving {velocity:.1}");
        }
        ride.accumulator = 0.;
        return;
    }
    // The ride keeps the collision it has while the next is built on another thread: building it here would stall
    // the frame for tens of milliseconds each time the area around the rider moves.
    if ride.generation != collision.generation && ride.building != Some(collision.generation) {
        let builder = ride.session.as_ref().unwrap().collision_builder();
        let (snapshot, generation, slot) = (collision.snapshot.clone(), collision.generation, ride.built.clone());
        ride.building = Some(generation);
        std::thread::spawn(move || {
            hakuba_screens::run_this_thread_as(hakuba_screens::ThreadClass::Utility);
            let started = std::time::Instant::now();
            let (triangles, surfaces, rails) = simulation_collision(&snapshot);
            let prepared = builder.build(triangles, surfaces, rails);
            info!("RIDE_COLLISION built in {:.1?}", started.elapsed());
            *slot.lock().unwrap() = Some((generation, prepared));
        });
    }
    let built = ride.built.lock().unwrap().take();
    if let Some((generation, prepared)) = built {
        if ride.building == Some(generation) {
            ride.building = None;
        }
        let started = std::time::Instant::now();
        let installed = prepared.and_then(|prepared| ride.session.as_mut().unwrap().install_collision(prepared));
        info!("RIDE_COLLISION installed in {:.1?}", started.elapsed());
        if let Err(error) = installed {
            status.failure = Some(error);
            return;
        }
        ride.generation = generation;
    }
    if let Ok(window) = windows.single() {
        ride.session.as_mut().unwrap().set_aspect_ratio(window.width() / window.height().max(1.));
    }
    let period = ride.session.as_ref().unwrap().period();
    // Keep a full fixed-step accumulator. A long host hitch pauses instead of inventing a huge solver step.
    ride.accumulator += time.delta_secs().min(0.25);
    let ticking = std::time::Instant::now();
    let mut ticks = 0;
    while ride.accumulator >= period {
        ticks += 1;
        let position = frame::world_point(ride.current.as_ref().unwrap().root.w_axis.truncate());
        let mut assist = 1.0_f32;
        let mut boost = 0.0_f32;
        for zone in &collision.snapshot.assist_zones {
            if inside_zone(position, zone.center, zone.half_extent, zone.yaw) {
                assist = assist.min(zone.value);
            }
        }
        for zone in &collision.snapshot.boost_zones {
            if inside_zone(position, zone.center, zone.half_extent, zone.yaw) {
                boost = boost.max(zone.value);
            }
        }
        if let Some(session) = ride.session.as_mut() {
            if let Err(error) = session.limit_vert_assist(assist).and_then(|_| session.set_boost_zone(boost)) {
                status.failure = Some(error);
                return;
            }
        }
        let mut packet = input.packet;
        if let Some(wants_on_foot) = ride.desired_on_foot {
            let state = ride.current.as_ref().unwrap().physical_state;
            let on_foot = (500..=502).contains(&state);
            if on_foot == wants_on_foot {
                ride.desired_on_foot = None;
                ride.toggle_ticks = 0;
            } else if ride.toggle_cooldown == 0 && matches!(state,100|200..=202|500..=501) {
                ride.toggle_ticks = 2;
                ride.toggle_cooldown = 12;
            }
        }
        ride.toggle_cooldown = ride.toggle_cooldown.saturating_sub(1);
        if ride.toggle_ticks > 0 {
            packet.buttons |= 0x8000;
            ride.toggle_ticks -= 1;
        }
        packet = places::packet(&mut places, packet);
        let tick_end = real_time.elapsed_secs_f64() - f64::from(ride.accumulator - period);
        let fine = input.fine_for_tick(tick_end, period, packet);
        let result = if let Some((half, end)) = fine {
            ride.session.as_mut().unwrap().tick_with_sticks(packet, half, end)
        } else {
            ride.session.as_mut().unwrap().tick(packet)
        };
        input.ticked();
        if let Err(error) = result {
            error!("Skating simulation stopped: {error}");
            status.failure = Some(error);
            ride.accumulator = 0.;
            return;
        }
        for event in ride.session.as_ref().unwrap().audio_events() {
            audio_events.write(*event);
        }
        let saved_before = settings.skate_places.clone();
        places::publish(ride.session.as_ref().unwrap(), &mut places, settings.bypass_change_detection());
        if settings.skate_places != saved_before {
            settings.set_changed();
        }
        let solved = ride.session.as_ref().unwrap().pose();
        let marker_returns = ride.session.as_ref().unwrap().marker_status().returns;
        if marker_returns != ride.marker_returns {
            ride.marker_returns = marker_returns;
            ride.marker_relocating = true;
            ride.marker_teleport_seen = false;
        }
        if ride.marker_relocating && solved.physical_state == 702 {
            ride.marker_teleport_seen = true;
        }
        let last_shown = ride.last_shown.as_ref().or(ride.current.as_ref()).unwrap().clone();
        let recovering = ride.session.as_ref().unwrap().recovering();
        let recovery_boundary = ride.recovery_owned || recovering;
        if ride.recovery_owned && !recovering {
            ride.floor = lost::HeldFloor::default();
        }
        ride.recovery_owned = recovering;
        let verdict = if !finite_pose(&solved) {
            lost::Verdict::Jump
        } else {
            let step = lost::Step {
                state: solved.physical_state,
                tick: solved.tick,
                ticks: solved.tick.saturating_sub(last_shown.tick) + 1,
                from: frame::world_point(last_shown.ground_point),
                to: frame::world_point(solved.ground_point),
                velocity: frame::world_point(solved.velocity),
                speed: last_shown.velocity.length().max(solved.velocity.length()),
            };
            lost::observe(&step, &mut ride.floor, |from, to| {
                let delta = to - from;
                let distance = delta.length();
                let direction = Dir3::new(delta).ok()?;
                ground.cast(from, direction, distance).map(|hit| (hit.point, hit.normal))
            })
        };
        let recovery_rebase = recovery_boundary && matches!(verdict, lost::Verdict::Jump | lost::Verdict::Teleport);
        if !finite_pose(&solved) || (verdict != lost::Verdict::Kept && !ride.marker_relocating && !recovery_rebase) {
            warn!("Skating local bail: {verdict:?}");
            if let Err(error) = ride.session.as_mut().unwrap().bail_in_place(&last_shown) {
                status.failure = Some(error);
                return;
            }
            ride.current = Some(ride.session.as_ref().unwrap().pose());
            ride.previous = ride.current.clone();
            ride.accumulator = 0.;
            break;
        }
        if ride.marker_relocating && ride.marker_teleport_seen && solved.physical_state != 702 {
            ride.marker_relocating = false;
            ride.marker_teleport_seen = false;
            ride.floor = lost::HeldFloor::default();
        }
        ride.offboard_time = if solved.physical_state == 500 { ride.offboard_time + period } else { 0. };
        ride.bail_time = if solved.bailed { ride.bail_time + period } else { 0. };
        ride.previous = ride.current.take();
        ride.current = Some(solved);
        ride.accumulator -= period;
    }
    if ticking.elapsed().as_secs_f32() > 0.004 {
        info!("RIDE_TICKS {ticks} in {:.1?}", ticking.elapsed());
    }
    let current = ride.current.as_ref().unwrap();
    status.tick = current.tick;
    status.state = current.state.clone();
    status.speed_mps = current.velocity.length();
    status.surface = current.surface.sound as u16;
    status.wheels = current.surface.wheels;
    status.bailed = current.bailed;
    status.on_board = !(500..=502).contains(&current.physical_state) && !current.bailed;
    status.stowed = false;
    status.on_foot = (500..=502).contains(&current.physical_state);

    let session = ride.session.as_ref().unwrap();
    status.audio = session.audio();
    status.recovering = session.recovering();
    let (score, reward, _) = session.score();
    status.score = score;
    status.reward = reward;
    status.telemetry = session.telemetry();
    status.trick = status.telemetry.display_trick.clone();
    status.balance = session.manual_balance();
}

#[allow(clippy::too_many_arguments)]
fn present(
    mut commands: Commands,
    mut ride: ResMut<Ride>,
    status: Res<SkateStatus>,
    grip: Res<BoardGrip>,
    settings: Res<hakuba_settings::Settings>,
    mut players: Query<(&Player, &mut Transform)>,
    rigs: Query<&Rig>,
    mut parts: Query<(&BoardPart, &mut Transform), Without<Player>>,
    mut camera: Query<(&mut Transform, &mut Projection), (With<Camera3d>, Without<Player>, Without<BoardPart>)>,
    mut walking_fov: Local<Option<f32>>,
    mut riding: ResMut<hakuba_world::Riding>,
) {
    riding.set_if_neq(hakuba_world::Riding(status.active));
    if !status.active {
        for (_, mut at) in &mut parts {
            at.scale = Vec3::splat(0.001);
        }
        // The ride's wider view ends with the ride: the walker sees as before the mount.
        if let (Some(fov), Ok((_, mut projection))) = (walking_fov.take(), camera.single_mut())
            && let Projection::Perspective(p) = &mut *projection
        {
            p.fov = fov;
        }
        return;
    }
    let Ok((player, mut root)) = players.single_mut() else { return };
    if player.owner != MovementOwner::Skating {
        return;
    }
    let (Some(current), Some(retarget), Ok(rig)) =
        (ride.current.as_ref(), ride.retarget.as_ref(), rigs.get(player.body))
    else {
        return;
    };
    let previous = ride.previous.as_ref().unwrap_or(current);
    let alpha = (ride.accumulator / ride.session.as_ref().unwrap().period()).clamp(0., 1.);
    *root = frame::interpolate(&frame::world_transform(previous.root), &frame::world_transform(current.root), alpha);
    let bones = interpolate_hierarchy(&previous.bones, &current.bones, &current.parents, alpha);
    commands.entity(player.body).insert(retarget.solve(
        rig,
        &bones,
        grip.0.as_ref(),
        std::array::from_fn(|i| {
            previous.contacts[i].board_blend
                + (current.contacts[i].board_blend - previous.contacts[i].board_blend) * alpha
        }),
    ));
    for (part, mut at) in &mut parts {
        if let Some(index) = current.names.iter().position(|n| n == part.0) {
            *at = Transform::from_matrix(root.to_matrix() * frame::world_transform(bones[index]).to_matrix());
            at.scale *=
                (previous.board_visibility + (current.board_visibility - previous.board_visibility) * alpha).max(0.001);
        }
    }
    if let (Some(a), Some(b), Ok((mut at, mut projection))) = (previous.camera, current.camera, camera.single_mut()) {
        let native_position = frame::world_point(a.0.lerp(b.0, alpha));
        let pivot = current
            .names
            .iter()
            .position(|n| n == "HIPS")
            .map_or(root.translation, |hip| root.transform_point(frame::world_point(bones[hip].w_axis.truncate())));
        let position = pivot + (native_position - pivot) * settings.skate.camera_distance;
        // The simulation publishes [right, up, at]. Reflect vectors, not camera-local axes.
        let forward = frame::world_point((a.1 * Vec3::Z).lerp(b.1 * Vec3::Z, alpha)).normalize();
        let up = frame::world_point((a.1 * Vec3::Y).lerp(b.1 * Vec3::Y, alpha)).normalize();
        *at = Transform::from_translation(position).looking_to(forward, up);
        if let Projection::Perspective(p) = &mut *projection {
            walking_fov.get_or_insert(p.fov);
            p.fov = (a.2 + (b.2 - a.2) * alpha + settings.skate.camera_fov).clamp(25., 110.).to_radians();
        }
    }
    let mut shown = current.clone();
    shown.root =
        frame::interpolate(&Transform::from_matrix(previous.root), &Transform::from_matrix(current.root), alpha)
            .to_matrix();
    shown.bones = bones;
    shown.velocity = previous.velocity.lerp(current.velocity, alpha);
    shown.ground_point = previous.ground_point.lerp(current.ground_point, alpha);
    ride.last_shown = Some(shown);
}

fn hand_back(
    commands: &mut Commands,
    ride: &mut Ride,
    player: &mut Player,
    at: &mut Transform,
    focus: &mut CollisionFocus,
    status: &mut SkateStatus,
    ground: &mut Ground,
    spare: &mut Spare,
    carry: Option<&mut Carry>,
) {
    if let Some(carry) = carry {
        if let Some((parts, deck_up)) = ride.current.as_ref().and_then(carried) {
            carry.parts = parts;
            carry.deck_up = deck_up;
            carry.held = true;
        }
    }
    // The session goes back to wait for the next mount: building another takes seconds.
    match ride.session.take() {
        Some(session) if status.failure.is_none() => {
            session_suspended(&mut *spare.session.lock().unwrap(), session);
            spare.started = true;
        }
        _ => spare.started = false,
    }
    let velocity = match (ride.previous.as_ref(), ride.current.as_ref(), ride.session.as_ref()) {
        (Some(previous), Some(current), Some(session)) if (500..=502).contains(&current.physical_state) => {
            let ticks = current.tick.saturating_sub(previous.tick).max(1) as f32;
            frame::world_point(current.root.w_axis.truncate() - previous.root.w_axis.truncate())
                / (session.period() * ticks)
        }
        (_, Some(pose), _) => frame::world_point(pose.velocity),
        _ => Vec3::ZERO,
    };
    let ahead = at.rotation * Vec3::X;
    let yaw = ahead.x.atan2(ahead.z);
    let hit = ground.below(at.translation, 0.5, 1.5);
    let grounded = hit.as_ref().is_some_and(|h| at.translation.y - h.point.y < 0.35);
    if grounded && let Some(hit) = hit {
        at.translation.y = hit.point.y;
    }
    at.rotation = Quat::from_rotation_y(yaw);
    player.resume_walking(at.translation, yaw, velocity, grounded);
    commands.entity(player.body).remove::<(PoseOverride, SolvedPose)>();
    commands.trigger(Play::looping(player.body, if grounded { "idle" } else { "fall" }).fading(0.15));
    *ride = Ride::default();
    *status = SkateStatus::default();
    // The walker keeps the focus where it is: clearing it would drop the collision just built and build it again.
    focus.destination = None;
}

fn session_suspended(slot: &mut Option<Result<Session, String>>, mut session: Session) {
    session.suspend_input();
    *slot = Some(Ok(session));
}

/// The board held at the walking player's side after they step off it, until a move that needs both hands puts it
/// away.
#[derive(Resource, Default)]
struct Carry {
    held: bool,
    /// Each part's place in the deck's frame, as the ride last had them.
    parts: [Mat4; PARTS.len()],
    /// The deck's turn into the player's frame when held on their right, and the same on their left.
    deck_up: [Quat; 2],
}

/// The board parts' places in the deck's frame, from a ride's pose, and the deck's turn into the player's frame when
/// held by its upper edge at their side: nose ahead, grip tape against the leg, wheels out.
fn carried(pose: &Pose) -> Option<([Mat4; PARTS.len()], [Quat; 2])> {
    let bone = |name: &str| {
        pose.names.iter().position(|n| n == name).map(|i| frame::world_transform(pose.bones[i]).to_matrix())
    };
    let inverse = bone(PARTS[0])?.inverse();
    let mut parts = [Mat4::IDENTITY; PARTS.len()];
    for (part, name) in parts.iter_mut().zip(PARTS) {
        *part = inverse * bone(name)?;
    }
    let (front, back) = (parts[1].w_axis.truncate(), parts[2].w_axis.truncate());
    let along = (front - back).try_normalize()?;
    let middle = (front + back) / 2.;
    let top = -(middle - along * middle.dot(along)).try_normalize()?;
    let deck = Mat3::from_cols(along, top, along.cross(top));
    // The player faces +Z with +Y up, so their right is -X.
    let turn =
        |inward: Vec3| Quat::from_mat3(&(Mat3::from_cols(Vec3::Z, inward, Vec3::Z.cross(inward)) * deck.transpose()));
    Some((parts, [turn(Vec3::X), turn(Vec3::NEG_X)]))
}

/// Shows the carried board in the walking player's hand, and puts it away at a sprint, a double jump, a dodge or the
/// paraglider.
#[allow(clippy::type_complexity)]
fn carry(
    mut carry: ResMut<Carry>,
    controls: Res<hakuba_player::Controls>,
    players: Query<(&Player, &Transform)>,
    hands: Query<&hakuba_characters::Hands>,
    nodes: Query<(&Transform, Option<&ChildOf>), Without<BoardPart>>,
    mut parts: Query<(&BoardPart, &mut Transform), (Without<Player>, Without<Camera3d>)>,
) {
    if !carry.held {
        return;
    }
    let Ok((player, at)) = players.single() else { return };
    if player.owner == MovementOwner::Skating {
        return;
    }
    let motion = &player.motion;
    if (controls.sprint && controls.stick.length() > 0.1)
        || motion.mode == hakuba_player::Mode::Glide
        || matches!(
            motion.action,
            hakuba_player::Action::Flip
                | hakuba_player::Action::Backflip
                | hakuba_player::Action::Hop(_)
                | hakuba_player::Action::GlideOpen
        )
    {
        carry.held = false;
        for (_, mut part) in &mut parts {
            part.scale = Vec3::splat(0.001);
        }
        return;
    }
    let Ok(hands) = hands.get(player.body) else { return };
    let world = |mut entity: Entity| {
        let mut place = bevy::math::Affine3A::IDENTITY;
        loop {
            let (local, parent) = nodes.get(entity).ok()?;
            place = local.compute_affine() * place;
            match parent {
                Some(parent) => entity = parent.parent(),
                None => return Some(Vec3::from(place.translation)),
            }
        }
    };
    let Some(right) = world(hands.arms[1].hand) else { return };
    let inverse = at.rotation.inverse();
    let local = inverse * (right - at.translation);
    let side = usize::from(local.x > 0.);
    let outward = Vec3::X * if side == 1 { 1. } else { -1. };
    let deck = Transform {
        translation: right + at.rotation * (Vec3::new(0., -CARRY_BELOW_WRIST_M, 0.) + outward * CARRY_OUT_M),
        rotation: at.rotation * carry.deck_up[side],
        scale: Vec3::ONE,
    }
    .to_matrix();
    for (part, mut place) in &mut parts {
        if let Some(index) = PARTS.iter().position(|name| *name == part.0) {
            *place = Transform::from_matrix(deck * carry.parts[index]);
        }
    }
}
/// How far below the wrist the carried deck's middle hangs, and how far out from the hand.
const CARRY_BELOW_WRIST_M: f32 = 0.17;
const CARRY_OUT_M: f32 = 0.04;
fn release(
    mut commands: Commands,
    mut ride: ResMut<Ride>,
    mut status: ResMut<SkateStatus>,
    mut focus: ResMut<CollisionFocus>,
    mut players: Query<(&mut Player, &mut Transform)>,
    mut ground: Ground,
    mut parts: Query<&mut Transform, (With<BoardPart>, Without<Player>)>,
    mut spare: ResMut<Spare>,
    mut carry: ResMut<Carry>,
) {
    carry.held = false;
    for mut at in &mut parts {
        at.scale = Vec3::splat(0.001);
    }
    if let Ok((mut player, mut at)) = players.single_mut() {
        if player.owner == MovementOwner::Skating {
            hand_back(
                &mut commands,
                &mut ride,
                &mut player,
                &mut at,
                &mut focus,
                &mut status,
                &mut ground,
                &mut spare,
                None,
            );
        }
    }
}
fn clear(
    mut ride: ResMut<Ride>,
    mut status: ResMut<SkateStatus>,
    mut focus: ResMut<CollisionFocus>,
    mut carry: ResMut<Carry>,
) {
    carry.held = false;
    *ride = Ride::default();
    *status = SkateStatus::default();
    focus.clear();
}
fn hud(status: Res<SkateStatus>, mut text: Query<&mut Text, With<RideHud>>) {
    for mut text in &mut text {
        let next = if let Some(error) = &status.failure {
            std::borrow::Cow::Owned(format!("Skating unavailable: {error}"))
        } else if status.waiting_for_collision {
            std::borrow::Cow::Borrowed("Preparing the ride collision...")
        } else if status.recovering {
            std::borrow::Cow::Borrowed("Recovering where the rider fell...")
        } else if status.active && status.on_foot {
            std::borrow::Cow::Borrowed(
                "Carrying skateboard | W/A/S/D move | Shift run | Space jump | Q/E drop/throw | V mount | F stow",
            )
        } else if status.active {
            std::borrow::Cow::Owned(format!(
                "{}  |  {:.0} km/h  |  {:.0} pts\n{}\nW push | S brake | A/D steer | Space pop | mouse/up/down flick/manual | Q/E grab | R transfer | Triangle / V off | F stow{}",
                status.state,
                status.speed_mps * 3.6,
                status.score,
                status.trick,
                if status.bailed { " | Cross / Enter recover" } else { "" }
            ))
        } else {
            std::borrow::Cow::Borrowed("Triangle / V | skateboard")
        };
        places::set_hud_text(&mut text, next);
    }
}

/// World-authored boxes are queried before the next fixed tick; no region coordinates enter this feature.
fn inside_zone(position: Vec3, center: [f32; 3], half: [f32; 3], yaw: f32) -> bool {
    let local = Quat::from_rotation_y(-yaw) * (position - Vec3::from(center));
    local.abs().cmple(Vec3::from(half)).all()
}

fn finite_pose(pose: &Pose) -> bool {
    pose.root.is_finite()
        && pose.velocity.is_finite()
        && pose.bones.iter().all(|m| m.is_finite())
        && pose.camera.is_none_or(|(p, b, f)| p.is_finite() && b.is_finite() && f.is_finite())
}

fn read_holder(
    parts: Query<(Entity, &BoardPart)>,
    children: Query<&Children>,
    extras: Query<(&Name, &GltfExtras)>,
    mut grip: ResMut<BoardGrip>,
    mut status: ResMut<SkateStatus>,
) {
    if grip.0.is_some() {
        return;
    }
    for (entity, part) in &parts {
        if part.0 != "SKATEBOARD_ROOT" {
            continue;
        }
        for child in children.iter_descendants(entity) {
            let Ok((name, extras)) = extras.get(child) else { continue };
            if name.as_str() != "holder" {
                continue;
            }
            let parsed = serde_json::from_str::<serde_json::Value>(&extras.value).ok().and_then(|v| {
                let expected = [
                    "LEFTHAND_REPARENTED",
                    "RIGHTHAND_REPARENTED",
                    "LEFTTOEBASE_REPARENTED",
                    "RIGHTTOEBASE_REPARENTED",
                ];
                let targets = v["attachment_targets"].as_array()?;
                if v["frame"].as_str() != Some("solved-bone-local")
                    || v["reference_pose"].as_str() != Some("RIG_TPOSE")
                    || v["reference_bank"].as_u64() != Some(0)
                    || targets.len() != expected.len()
                    || !expected.iter().all(|name| targets.iter().any(|target| target.as_str() == Some(name)))
                {
                    return None;
                }
                serde_json::from_value::<retarget::DeckProfile>(v["deck"].clone()).ok()
            });
            match parsed {
                Some(deck) => grip.0 = Some(deck),
                None => {
                    let failure = format!("{BOARD}: invalid source holder binding");
                    if status.failure.as_ref() != Some(&failure) {
                        error!("{failure}");
                        status.failure = Some(failure);
                    }
                }
            }
        }
    }
}

#[cfg(test)]
#[path = "lifecycle_tests.rs"]
mod lifecycle_tests;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn authored_zone_membership_is_oriented_and_has_no_render_clock() {
        assert!(inside_zone(Vec3::new(0., 0., 1.5), [0.; 3], [2., 1., 0.5], std::f32::consts::FRAC_PI_2));
        assert!(!inside_zone(Vec3::new(1.5, 0., 0.), [0.; 3], [2., 1., 0.5], std::f32::consts::FRAC_PI_2));
    }
    #[test]
    fn rigid_board_child_follows_arc_during_render_interpolation() {
        let a = [Mat4::IDENTITY, Mat4::IDENTITY, Mat4::from_translation(Vec3::X)];
        let parent = Mat4::from_rotation_y(1.2);
        let b = [Mat4::IDENTITY, parent, parent * Mat4::from_translation(Vec3::X)];
        let shown = interpolate_hierarchy(&a, &b, &[-1, 0, 1], 0.5);
        assert!((shown[2].w_axis.truncate().distance(shown[1].w_axis.truncate()) - 1.).abs() < 1e-5);
        assert!(shown[2].w_axis.z.abs() > 0.4);
    }
    #[test]
    fn normal_carry_keeps_native_authority_and_stow_waits_for_stable_ground() {
        assert!(!should_hand_back(false, 10.));
        assert!(!should_hand_back(true, 0.19));
        assert!(should_hand_back(true, 0.2));
    }
    /// Ground distance walked on foot over three seconds with the stick fully forward and `buttons` held.
    fn walked_on_foot(buttons: u16) -> f32 {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets");
        let bytes = std::fs::read(root.join(PACKAGE)).unwrap();
        let triangles = vec![
            [[-100., 0., -100.], [-100., 0., 100.], [100., 0., -100.]],
            [[100., 0., -100.], [-100., 0., 100.], [100., 0., 100.]],
        ];
        let resources = crate::PreparedResources::from_bytes(bytes).unwrap();
        let mut session =
            Session::from_resources(&resources, triangles, vec![129; 2], vec![], [0., 0.1, 0.], 0.).unwrap();
        session.activate_on_foot([0., 0.1, 0.], 0.).unwrap();
        for _ in 0..30 {
            session.tick(Controls::default()).unwrap();
        }
        assert_eq!(session.pose().physical_state, 500);
        let start = session.pose().ground_point;
        for _ in 0..180 {
            session.tick(Controls { buttons, left: [0, 32767], ..Controls::default() }).unwrap();
        }
        let end = session.pose().ground_point;
        assert_eq!(session.pose().physical_state, 500);
        Vec2::new(end.x - start.x, end.z - start.z).length()
    }
    #[test]
    fn south_alone_sprints_on_foot_and_east_cancels_it() {
        let walk = walked_on_foot(0);
        let sprint = walked_on_foot(0x1000);
        let both = walked_on_foot(0x3000);
        assert!(walk > 1.0, "walked {walk} m");
        assert!(sprint > walk * 1.2, "sprinted {sprint} m, walked {walk} m");
        assert!((both - walk).abs() < walk * 0.05, "South+East {both} m, walked {walk} m");
    }
    #[test]
    fn committed_session_mounts_pushes_and_dismounts_with_finite_interpolated_board() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets");
        let bytes = std::fs::read(root.join(PACKAGE)).unwrap();
        let triangles = vec![
            [[-100., 0., -100.], [-100., 0., 100.], [100., 0., -100.]],
            [[100., 0., -100.], [-100., 0., 100.], [100., 0., 100.]],
        ];
        let resources = crate::PreparedResources::from_bytes(bytes).unwrap();
        let mut session =
            Session::from_resources(&resources, triangles, vec![129; 2], vec![], [0., 0.1, 0.], 0.).unwrap();
        let initial = session.activate_on_foot([0., 0.1, 0.], 0.).unwrap();
        assert!(finite_pose(&initial));
        let mut states = std::collections::BTreeSet::new();
        let mut phase = 0;
        let mut phase_ticks = 0;
        let mut saw_carry = false;
        let mut remounted = false;
        let mut previous_state = String::new();
        for tick in 0..900 {
            let before = session.pose();
            if before.state != previous_state {
                eprintln!(
                    "tick={tick} phase={phase} state={} speed={} root={:?}",
                    before.state,
                    before.velocity.length(),
                    before.root.w_axis
                );
                previous_state = before.state.clone();
            }
            let mut packet = Controls::default();
            match phase {
                0 => {
                    if before.physical_state == 500 {
                        packet.buttons |= 0x8000;
                        phase = 1;
                        phase_ticks = 0;
                    }
                }
                1 => {
                    if before.physical_state == 500 && phase_ticks % 12 < 2 {
                        packet.buttons |= 0x8000;
                    }
                    if before.physical_state == 100 && phase_ticks > 60 {
                        phase = 2;
                        phase_ticks = 0;
                    }
                }
                2 => {
                    if phase_ticks < 90 {
                        packet.buttons |= 0x1000;
                    } else if before.physical_state == 100 {
                        phase = 3;
                        phase_ticks = 0;
                    }
                }
                3 => {
                    if (500..=502).contains(&before.physical_state) {
                        saw_carry = true;
                        phase = 4;
                        phase_ticks = 0;
                    } else if phase_ticks % 4 < 2 {
                        packet.buttons |= 0x8000;
                    }
                }
                4 => {
                    packet.left = [0, 16000];
                    if phase_ticks >= 60 && before.physical_state == 500 {
                        phase = 5;
                        phase_ticks = 0;
                    }
                }
                5 => {
                    if before.physical_state == 100 {
                        remounted = true;
                        phase = 6;
                        phase_ticks = 0;
                    } else if phase_ticks % 4 < 2 {
                        packet.buttons |= 0x8000;
                    }
                }
                _ => {
                    packet.buttons |= 0x1000;
                }
            }
            session.tick(packet).unwrap();
            phase_ticks += 1;
            if tick < 20 || tick % 60 == 0 {
                eprintln!("{}", session.transition_debug());
            }
            let pose = session.pose();
            assert!(finite_pose(&pose));
            states.insert(pose.state.clone());
            let deck = pose.names.iter().position(|name| name == "SKATEBOARD_ROOT").unwrap();
            let shown = frame::world_transform(pose.root * pose.bones[deck]);
            assert!(shown.translation.is_finite() && shown.rotation.is_finite());
            if phase == 6 && phase_ticks > 60 {
                break;
            }
        }
        eprintln!("native mount/push/dismount states: {states:?}");
        assert!(states.iter().any(|s| s == "PhysicsGround"), "mount never reached riding: {states:?}");
        assert!(saw_carry, "native dismount never reached BipedGround carry: {states:?}");
        assert!(remounted, "native carry never accepted a remount attempt: {states:?}");
        assert!(
            (100..=103).contains(&session.pose().physical_state),
            "native remount did not ride away: {:?}",
            session.pose().state
        );
        assert!(session.pose().velocity.length() > 0.5, "native remount did not preserve a playable push");
        assert!(states.iter().any(|s| s == "BipedGround"), "off-board graph never ran: {states:?}");
    }
}

fn should_hand_back(stowing: bool, stable_ground_s: f32) -> bool {
    stowing && stable_ground_s >= 0.2
}

/// Interpolate parent-local transforms, then rebuild the same-frame hierarchy; rigid contacts do not cut a chord.
fn interpolate_hierarchy(previous: &[Mat4], current: &[Mat4], parents: &[i32], alpha: f32) -> Vec<Mat4> {
    let mut shown = Vec::with_capacity(current.len());
    for (index, (a, b)) in previous.iter().zip(current).enumerate() {
        let parent = parents[index];
        let (a, b) = if parent > 0 {
            let parent = parent as usize;
            (previous[parent].inverse() * *a, current[parent].inverse() * *b)
        } else {
            (*a, *b)
        };
        let local = frame::interpolate(&Transform::from_matrix(a), &Transform::from_matrix(b), alpha).to_matrix();
        shown.push(if parent > 0 { shown[parent as usize] * local } else { local });
    }
    shown
}

fn apply_preferences(
    settings: Res<hakuba_settings::Settings>,
    mut ride: ResMut<Ride>,
    mut status: ResMut<SkateStatus>,
    mut applied: Local<Option<hakuba_settings::SkatePreferences>>,
) {
    if applied.as_ref() == Some(&settings.skate) {
        return;
    }
    *applied = Some(settings.skate.clone());
    if let Some(session) = ride.session.as_mut() {
        if let Err(error) = preferences::apply(session, &settings.skate) {
            status.failure = Some(error);
        }
    }
}
