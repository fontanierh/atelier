#include "CameraGraphOperations.h"
#include <charconv>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
std::vector<std::string> ShotNames(const GraphAttributes &a) {
  std::vector<std::string> names;
  for (std::size_t index = 1;; ++index) {
    const auto name = a.Text("shot" + std::to_string(index));
    if (!name)
      break;
    names.emplace_back(*name);
  }
  return names;
}
bool CameraCondition::Parse(const GraphAttributes &a, std::string &error) {
  const auto name = a.Text("name");
  if (!name) {
    error = "Camera condition requires name";
    return false;
  }
  const std::array<const char *, 27> booleans{"IsInObserverMode",
                                              "IsWipingOut",
                                              "IsBrokenBoneSlowMo",
                                              "IsOffboard",
                                              "IsAirOffboard",
                                              "IsInOnBoardAir",
                                              "IsFixedInAir",
                                              "IsPreparingToJump",
                                              "IsInManual",
                                              "SkaterIsDroppingIn",
                                              "SkaterIsMovingObject",
                                              "SkaterIsSkitching",
                                              "SkaterIsPerformingFootPlant",
                                              "SkaterIsPerformingHandPlant",
                                              "SkaterIsPerformingBoneless",
                                              "SkaterIsPerformingHippyJump",
                                              "SkaterIsPerformingHippyHurdle",
                                              "SkaterIsGrinding",
                                              "SkaterWasGrinding",
                                              "IsPlayerSkateboardOnGround",
                                              "IsReentry",
                                              "SkaterIsOnRoad",
                                              "IsGrindLedgeLeft",
                                              "IsGrindLedgeRight",
                                              "IsInWorldPainterRegion",
                                              "SkaterIsUnderThreat",
                                              "IsCameraInBadCollision"};
  for (std::size_t index = 0; index < booleans.size(); ++index)
    if (*name == booleans[index]) {
      kind = Kind::Boolean;
      boolean = static_cast<CameraBoolean>(index);
      return true;
    }
  const std::array<const char *, 17> values{"CameraSubjectSpeed",
                                            "CameraSubjectSpeedY",
                                            "CameraSubjectAcceleration",
                                            "PredictedAirTime",
                                            "PredictedLandingHeight",
                                            "PredictedMaxHeight",
                                            "PredictedHeightDistanceRatio",
                                            "FrontsideAngle",
                                            "TransferAngle",
                                            "LaunchInclineAngle",
                                            "LandingInclineAngle",
                                            "GrindInclineAngle",
                                            "InclineAngle",
                                            "InclineAngleAbs",
                                            "TurningCentredTime",
                                            "TurningTime",
                                            "TimeSinceLastPlayerInput"};
  for (std::size_t index = 0; index < values.size(); ++index)
    if (*name == values[index]) {
      kind = Kind::Numeric;
      numeric_value = static_cast<CameraValue>(index);
      numeric = ParseNumericCondition(a);
      return true;
    }
  if (*name == "IsCameraTypeActive") {
    kind = Kind::Type;
    auto type = a.Text("type");
    if (!type) {
      error = "IsCameraTypeActive requires type";
      return false;
    }
    if (!type->empty() && (*type)[0] == '+')
      type = type->substr(1);
    const auto parsed =
        std::from_chars(type->data(), type->data() + type->size(), value);
    if (parsed.ec != std::errc{} || parsed.ptr != type->data() + type->size()) {
      error = "Invalid normal camera type";
      return false;
    }
    return true;
  }
  if (*name == "IsPreviousShot") {
    kind = Kind::Previous;
    for (const auto &shot : ShotNames(a))
      shot_hashes.push_back(GraphKeyHash(shot));
    return true;
  }
  if (*name == "IsInVolume") {
    kind = Kind::Volume;
    const auto name = a.Text("volume");
    if (!name) {
      error = "IsInVolume requires volume";
      return false;
    }
    volume = *name;
    return true;
  }
  if (*name == "IsWipeoutBodyTweak") {
    kind = Kind::Tweak;
    const auto tweak = a.Text("tweak").value_or("");
    value = tweak == "CannonBall" ? 1
            : tweak == "JudoKick" ? 2
            : tweak == "SwanDive" ? 3
            : tweak == "Torpedo"  ? 4
                                  : 0;
    return true;
  }
  error = "Unimplemented stock camera condition " + std::string(*name);
  return false;
}
bool CameraCondition::Evaluate(const CameraMan &m, const ManagerSubject &s,
                               CameraGraphSubject g,
                               const CameraGraphEnvironment &world) const {
  const auto &f = m.rig.fields;
  const auto &state = m.state;
  if (kind == Kind::Type)
    return value == world.camera_type;
  if (kind == Kind::Previous) {
    const auto hash = GraphKeyHash(m.shots.current.definition.name);
    for (const auto name : shot_hashes)
      if (name == hash)
        return true;
    return false;
  }
  if (kind == Kind::Tweak)
    return value == g.wipeout_tweak;
  if (kind == Kind::Volume) {
    for (const auto &name : world.volumes)
      if (name.size() >= volume.size() &&
          name.compare(0, volume.size(), volume) == 0)
        return true;
    return false;
  }
  if (kind == Kind::Boolean) {
    switch (boolean) {
    case CameraBoolean::Observer:
      return s.special_effect != 0;
    case CameraBoolean::WipingOut:
      return s.rig.wiping_out != 0;
    case CameraBoolean::BrokenBone:
      return s.rig.broken_bone_slowmo != 0;
    case CameraBoolean::Offboard:
      return s.rig.off_board != 0 || g.running_out;
    case CameraBoolean::OffboardAir:
      return g.offboard_air;
    case CameraBoolean::OnboardAir:
      return g.onboard_air;
    case CameraBoolean::FixedInAir:
      return s.rig.air_flag_452 != 0;
    case CameraBoolean::Preparing:
      return g.preparing_to_jump;
    case CameraBoolean::Manual:
      return g.manual;
    case CameraBoolean::DroppingIn:
      return g.dropping_in;
    case CameraBoolean::MovingObject:
      return g.moving_object;
    case CameraBoolean::Skitching:
      return g.skitching;
    case CameraBoolean::Footplant:
      return g.footplant;
    case CameraBoolean::Handplant:
      return g.handplant;
    case CameraBoolean::Boneless:
      return g.boneless;
    case CameraBoolean::HippyJump:
      return g.hippy_jump;
    case CameraBoolean::HippyHurdle:
      return g.hippy_hurdle;
    case CameraBoolean::Grinding:
      return f.height_mode == 2;
    case CameraBoolean::WasGrinding:
      return f.previous_height_mode == 2;
    case CameraBoolean::OnGround:
      return f.height_mode == 0;
    case CameraBoolean::Reentry:
      return (state.flags & 0x10) != 0;
    case CameraBoolean::Road:
      return world.on_road;
    case CameraBoolean::LedgeLeft:
      return world.ledge_left;
    case CameraBoolean::LedgeRight:
      return world.ledge_right;
    case CameraBoolean::WorldPainter:
    case CameraBoolean::Threat:
      return false;
    case CameraBoolean::BadCollision:
      return (m.rig.positioner.flags & 0x80) != 0 &&
             m.rig.positioner.distance < f.distance * 0.75f;
    }
  }
  const float degrees = Bits(0x42652ee1);
  float number = 0;
  switch (numeric_value) {
  case CameraValue::Speed: {
    const auto n = s.rig.transform[2], v = f.velocity;
    number = (v[0] * n[0] + v[1] * n[1]) + v[2] * n[2];
    break;
  }
  case CameraValue::SpeedY:
    number = f.velocity[1];
    break;
  case CameraValue::Acceleration:
    number = f.smoothed_acceleration;
    break;
  case CameraValue::AirTime:
    number = s.ValidTrajectoryDuration();
    break;
  case CameraValue::LandingHeight:
    number = state.landing_height_delta;
    break;
  case CameraValue::MaxHeight:
    number = state.apex_height;
    break;
  case CameraValue::HeightRatio:
    number = state.apex_height_ratio;
    break;
  case CameraValue::FrontsideAngle:
    number = state.frontside_angle;
    break;
  case CameraValue::TransferAngle:
    number = state.launch_landing_heading_delta * degrees;
    break;
  case CameraValue::LaunchIncline:
    number = state.launch_incline * degrees;
    break;
  case CameraValue::LandingIncline:
    number = state.landing_incline * degrees;
    break;
  case CameraValue::GrindIncline:
    number = state.direction_incline * degrees;
    break;
  case CameraValue::Incline:
    number = state.velocity_incline * degrees;
    break;
  case CameraValue::AbsoluteIncline:
    number = std::abs(state.absolute_velocity_incline * degrees);
    break;
  case CameraValue::CentredTime:
    number = state.centred_time;
    break;
  case CameraValue::TurningTime:
    number = state.steering_time;
    break;
  case CameraValue::TimeSinceInput:
    number = g.time_since_player_input;
    break;
  }
  return numeric.Matches(number);
}
bool CameraGraph::FromGraph(const Graph &source, SlowMotionSettings settings,
                            std::string &error) {
  CameraGraph next;
  GraphBinding binding;
  if (!binding.Bind(source, error) || !next.program.FromBinding(binding, error))
    return false;
  for (const auto id : next.program.operations.conditions) {
    const auto &op = binding.operations[id];
    CameraCondition condition;
    if (!condition.Parse(
            GraphAttributes(source.elements[op.element].attributes), error))
      return false;
    next.conditions.push_back(std::move(condition));
  }
  for (const auto id : next.program.operations.behaviors) {
    const auto &op = binding.operations[id];
    const GraphAttributes a(source.elements[op.element].attributes);
    CameraBehavior b;
    if (op.name == "CameraChooseShot") {
      b.kind = CameraBehavior::Kind::Choose;
      b.names = ShotNames(a);
      if (b.names.empty()) {
        error = "CameraChooseShot has no named shot";
        return false;
      }
      b.incoming = Bits(a.FloatBits("transitionIn", 0xbf800000));
      b.outgoing = Bits(a.FloatBits("transitionOut", 0xbf800000));
    } else if (op.name == "PrintText2D") {
      b.kind = CameraBehavior::Kind::Print;
      b.text = a.Text("text").value_or("");
    } else if (op.name == "SlowMotionController")
      b.kind = CameraBehavior::Kind::SlowMotion;
    else {
      error = "Unimplemented camera behavior " + op.name;
      return false;
    }
    next.behaviors.push_back(std::move(b));
  }
  if (!next.program.operations.hooks.empty()) {
    error = "Camera graph has unimplemented transition hooks";
    return false;
  }
  next.controller = graph::Controller(binding.states.size());
  next.slow_motion.resize(next.behaviors.size());
  next.slow_motion_settings = settings;
  *this = std::move(next);
  error.clear();
  return true;
}
namespace {
struct CameraHost final : graph::Host {
  CameraGraph &graph;
  CameraMan &manager;
  const ManagerSubject &subject;
  CameraGraphSubject physical;
  const CameraGraphEnvironment &world;
  const StockShots &database;
  std::optional<std::string> error;
  std::vector<SimulationRateRequest> rates;
  CameraHost(CameraGraph &g, CameraMan &m, const ManagerSubject &s,
             CameraGraphSubject p, const CameraGraphEnvironment &w,
             const StockShots &d)
      : graph(g), manager(m), subject(s), physical(p), world(w), database(d) {}
  std::uint32_t ConditionActivation(graph::Id id,
                                    const graph::Frame &) override {
    return std::uint32_t(
        graph.conditions[id].Evaluate(manager, subject, physical, world));
  }
  graph::Context GetContext() const override { return {}; }
  std::uint32_t Allocate(graph::Id, const graph::Frame &) override { return 0; }
  void Begin(graph::Id id, graph::Context, const graph::Frame &) override {
    const auto &b = graph.behaviors[id];
    if (b.kind == CameraBehavior::Kind::Choose) {
      if (b.names.empty()) {
        error = "CameraChooseShot has no named shot";
        return;
      }
      bool changed;
      std::string failure;
      if (!manager.SetShot(b.names.front(), false, subject, database, changed,
                           failure)) {
        error = std::move(failure);
        return;
      }
      manager.shots.ApplyGraphTransition(b.incoming, b.outgoing);
    } else if (b.kind == CameraBehavior::Kind::Print)
      graph.printed_messages.push_back("Stock camera graph: " + b.text);
    else {
      const auto [instance, request] =
          SlowMotionController::Begin(graph.slow_motion_settings);
      graph.slow_motion[id] = instance;
      rates.push_back(request);
    }
  }
  void Update(graph::Id id, graph::Context,
              const graph::Frame &frame) override {
    if (graph.slow_motion[id])
      rates.push_back(graph.slow_motion[id]->Update(
          frame.dt, physical.slow_motion_air_duration,
          graph.slow_motion_settings));
  }
  void End(graph::Id id, graph::Context, const graph::Frame &) override {
    if (graph.slow_motion[id]) {
      graph.slow_motion[id].reset();
      rates.push_back(SlowMotionController::End());
    }
  }
  void Hook(graph::Id, const graph::Frame &) override {
    error = "camera hooks rejected during load";
  }
  void Release(std::uint32_t) override {}
};
} // namespace
bool CameraGraph::Update(float dt, CameraMan &manager,
                         const ManagerSubject &subject,
                         CameraGraphSubject physical,
                         const CameraGraphEnvironment &world,
                         const StockShots &database,
                         std::vector<SimulationRateRequest> &rates,
                         std::string &error) {
  CameraHost host(*this, manager, subject, physical, world, database);
  controller.Update(program.program, dt, host);
  if (host.error) {
    error = *host.error;
    return false;
  }
  rates = std::move(host.rates);
  error.clear();
  return true;
}
} // namespace atelier::skate::camera
