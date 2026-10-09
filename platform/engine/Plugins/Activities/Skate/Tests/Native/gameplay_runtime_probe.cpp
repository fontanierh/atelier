// Whole production runtime from native data. No completed pose, input, contact,
// graph or solver result is supplied by this executable.
// clang-format off
#include "GameplayRuntime.h"
#include "gameplay_render_helpers.inc"
#include "gameplay_player_observers.inc"
#include "gameplay_camera_helpers.inc"
#include "gameplay_scoring_helpers.inc"
// clang-format on
#include <cmath>
#include <type_traits>
namespace {
void TextOut(Output &o, std::string_view value) {
  o.Word(std::uint32_t(value.size()));
  for (unsigned char c : value)
    o.Word(c);
}
void BytesOut(Output &o, const std::vector<std::uint8_t> &bytes) {
  o.Word(std::uint32_t(bytes.size()));
  for (auto v : bytes)
    o.Word(v);
}
void IntentsOut(Output &o, const IntentMap &map) {
  o.Word(std::uint32_t(map.Size()));
  for (const auto &entry : map.Entries()) {
    for (auto v : entry.first)
      o.Word(v);
    o.Float(entry.second);
  }
}
void GrindOut(Output &o, const FilteredGrindState &g) {
  o.Word(std::uint32_t(g.kind));
  o.Word(std::uint32_t(g.scorable_id));
  for (auto x : g.name)
    o.Word(x);
  for (auto x : g.scoring_name)
    o.Word(x);
  o.Word(g.on_front);
  o.Float(g.crouch);
  o.Wide(g.pathed_guid);
  o.Wide(g.local_guid);
}
void StateOut(Output &o, const PlayerStateRuntime &s) {
  o.Word(std::uint32_t(s.Current()));
  o.Word(std::uint32_t(s.requested_state));
  o.Word(s.state_count);
  o.Word(s.update_count);
  o.Word(s.initialized);
  for (auto v : s.state_flags)
    o.Word(v);
  const auto &t = s.selector;
  o.Word(bool(t.current_state));
  if (t.current_state)
    o.Word(std::uint32_t(*t.current_state));
  for (auto v :
       {t.nonspecific_collision_free_frames, t.nonspecific_collision_frames,
        t.something_colliding_frames, t.two_wheel_counter,
        t.three_wheel_counter, t.post_grind_jump_counter, t.air_frames,
        t.teleport_countdown, t.skitch_exit_countdown})
    o.Word(std::uint32_t(v));
  o.Word(t.revert_exited_normally);
  o.Word(t.request_teleport);
  const auto &p = s.post;
  for (auto w : p.jump_reference)
    o.Word(w);
  for (auto v : {p.jump_fix_frames, p.latch_frames, p.state_frames})
    o.Word(v);
  o.Float(p.heading_adjust);
  for (auto v : {p.complete, p.trajectory_pending, p.trajectory_valid,
                 p.trajectory_available, p.trajectory_new_candidate})
    o.Word(v);
  const auto &f = s.conditioning.filtered;
  for (auto v : {std::uint32_t(f.category), std::uint32_t(f.previous_category),
                 std::uint32_t(f.previous_physics_state),
                 std::uint32_t(f.air_count), std::uint32_t(f.nonspecific_count),
                 std::uint32_t(f.nonspecific_collision_free_count),
                 std::uint32_t(f.nonspecific_collision_count),
                 std::uint32_t(f.frames_since_ground_stairs),
                 std::uint32_t(f.must_change)})
    o.Word(v);
  GrindOut(o, f.CachedGrind());
  o.Word(bool(s.conditioning.filtered_output));
  if (s.conditioning.filtered_output) {
    const auto &v = *s.conditioning.filtered_output;
    o.Word(std::uint32_t(v.category));
    o.Word(std::uint32_t(v.previous_category));
    o.Word(v.grinding);
    GrindOut(o, v.grind);
    o.Float(v.last_grind_distance);
  }
}
void ControlsOut(Output &o, const PlayerControls &c) {
  for (auto w : c.controller.Words())
    o.Word(w);
  o.Word(bool(c.offboard_direction));
  if (c.offboard_direction)
    o.Floats(*c.offboard_direction);
  o.Word(std::uint32_t(c.intents.size()));
  for (auto v : c.intents) {
    TextOut(o, v.name);
    o.Float(v.value);
  }
  IntentsOut(o, c.action_intents);
  o.Wide(c.ticks);
  o.Word(c.actor_flags);
  o.Word(c.bumper_state_502);
  o.Word(c.bumper_state_104);
  o.Word(c.preferences.automatic_push_enabled);
  o.Word(c.preferences.automatic_push_right);
  o.Word(bool(c.SampledOffboardAxes()));
  if (c.SampledOffboardAxes())
    o.Floats(*c.SampledOffboardAxes());
  o.Word(c.HasGestures());
  if (c.HasGestures()) {
    const auto held = c.HeldPattern();
    o.Word(bool(held));
    if (held)
      TextOut(o, *held);
  }
}
void EventOut(Output &o, const PhysicsEvent &e) {
  o.Word(std::uint32_t(e.index()));
  std::visit(
      [&](const auto &v) {
        using T = std::decay_t<decltype(v)>;
        if constexpr (std::is_same_v<T, PhysicsStateChanged>) {
          o.Word(std::uint32_t(v.from));
          o.Word(std::uint32_t(v.to));
        } else if constexpr (std::is_same_v<T, PhysicsContact>)
          o.Word(std::uint32_t(v.body));
      },
      e);
}
void ExchangeOut(Output &o, const SimulationExchange &e) {
  o.Wide(e.Commands().Tick());
  o.Word(std::uint32_t(e.Commands().Commands().size()));
  for (const auto &c : e.Commands().Commands()) {
    o.Word(std::uint32_t(c.index()));
    std::visit(
        [&](const auto &v) {
          using T = std::decay_t<decltype(v)>;
          if constexpr (std::is_same_v<T, PhysicsSetVelocity>) {
            o.Word(std::uint32_t(v.body));
            VectorOut(o, v.linear);
            VectorOut(o, v.angular);
          } else if constexpr (std::is_same_v<T, PhysicsApplyImpulse>) {
            o.Word(std::uint32_t(v.body));
            VectorOut(o, v.impulse);
            VectorOut(o, v.point);
          } else if constexpr (std::is_same_v<T, PhysicsRequestState>)
            o.Word(std::uint32_t(v.state));
          else {
            o.Word(std::uint32_t(v.body));
            o.Word(v.enabled);
          }
        },
        c);
  }
  o.Word(std::uint32_t(e.Events().size()));
  for (const auto &v : e.Events())
    EventOut(o, v);
  o.Word(e.Output() != nullptr);
  if (const auto *v = e.Output()) {
    o.Wide(v->tick);
    o.Word(std::uint32_t(v->state));
    for (auto p :
         {v->board_position, v->board_linear_velocity, v->rider_root_position,
          v->rider_linear_velocity, v->ground_normal})
      VectorOut(o, p);
    o.Word(v->contact_count);
    VectorOut(o, v->predicted_position);
    o.Word(v->grounded);
    o.Word(v->wiping_out);
    o.Word(v->landed);
    o.Word(std::uint32_t(v->events.size()));
    for (const auto &p : v->events)
      EventOut(o, p);
  }
}
void ActorOut(Output &o, const SkaterAnimation &a) {
  o.Wide(a.ticks);
  o.Word(a.state.flags);
  o.Float(a.state.phase);
  o.Word(a.CheckpointStance());
  o.Word(std::uint32_t(a.state.publication.natural_stance));
  o.Word(std::uint32_t(a.state.publication.relative_stance));
  o.Word(a.animation.requested_stance);
  o.Word(a.animation.reset_action_intents);
  IntentsOut(o, a.animation.motion_intents);
  IntentsOut(o, a.animation.filtered_intents);
  gameplay_camera_wire::Output bytes;
  gameplay_camera_wire::WriteValue(bytes, a.action_controller);
  gameplay_camera_wire::WriteValue(bytes, a.motion_controller);
  BytesOut(o, bytes.data);
}
void GameplaySnapshot(Output &o, GameplayRuntime &g) {
  const auto &p = *g.physical;
  o.Word(9);
  Block(o, [&] {
    const auto begin = o.words.size();
    Snapshot(o, g.handplant, g.air_reckoning, *g.skeleton_air, p, *g.animated,
             *g.ik, *g.skeleton_input, g.animation_input, g.input->processed,
             g.ground_lifecycle.board_animated_290);
    o.words[begin] = 13;
    Block(o, [&] { OutputOwner(o, *g.skeleton_output, g.wobble); });
    Block(o, [&] { FeetOwner(o, *g.foot_physical); });
    Block(o, [&] {
      FinalPose(o, g.render_pose, g.pose_generation, *g.animation,
                g.input->physical, g.input->processed, g.wipeout);
    });
  });
  Block(o, [&] { Observe(o, g.input->player); });
  Block(o, [&] { Observe(o, g.input->physical); });
  Block(o, [&] { Observe(o, g.input->processed); });
  Block(o, [&] { StateOut(o, *g.player_state); });
  Block(o, [&] { ControlsOut(o, *g.controls); });
  Block(o, [&] {
    o.Wide(p.ticks);
    o.Word(std::uint32_t(p.contact_count));
    o.Word(p.failed);
    o.Word(p.processed_flags_2468);
    o.Word(p.board_wiping_out);
    o.Word(g.network_active);
    const auto t = g.trainer;
    o.Floats(std::array<float, 11>{
        t.pop, t.grind_pop, t.push_speed, t.push_power, t.braking, t.steering,
        t.wobble, t.offboard_jump, t.grip, t.turn_power, t.manual_drag});
    o.Word(t.hold_fakie);
    const auto &f = g.centre_of_mass_filter;
    for (auto v :
         {f.velocity, f.position, f.position_velocity, f.accumulated_error})
      o.Floats(v);
    o.Word(f.position_valid);
    const auto c = g.centre_of_mass_output;
    o.Floats(c.velocity);
    o.Floats(c.acceleration);
    o.Floats(c.position);
    o.Word(g.clock.TicksUntilReset());
    o.Wide(g.clock.PeriodNanoseconds());
    o.Word(bool(g.input->PendingTeleport()));
    if (g.input->PendingTeleport())
      o.Matrix(*g.input->PendingTeleport());
    ExchangeOut(o, g.exchange);
    ActorOut(o, *g.animation);
  });
  Block(o, [&] {
    gameplay_camera_wire::Output bytes;
    gameplay_camera_wire::ObserveRuntime(bytes, g.camera);
    BytesOut(o, bytes.data);
  });
  Block(o, [&] {
    gameplay_score_wire::Output score;
    score.State(g.scoring);
    o.words.insert(o.words.end(), score.words.begin(), score.words.end());
  });
}
std::optional<WorldGeometry> FlatWorld(ContactMaterial material,
                                       std::string &error) {
  // Exact source-authored ground.rs quad, winding and query metadata.
  const std::array<Vec3, 4> v{{{-50, -.035f, -50},
                               {50, -.035f, -50},
                               {50, -.035f, 50},
                               {-50, -.035f, 50}}};
  std::vector<WorldTriangle> triangles;
  for (const auto order :
       {std::array<unsigned, 3>{0, 2, 1}, std::array<unsigned, 3>{0, 3, 2}})
    triangles.push_back(
        {TriangleFromVolume({v[order[0]], v[order[1]], v[order[2]]}, 0,
                            {1, 1, 1}, 0x10),
         material, 0});
  const auto bounds = Bounds::FromPoints(v);
  if (!bounds)
    return std::nullopt;
  QueryMetadata metadata;
  metadata.packed_surfaces = {0, 0};
  const AffineTransform identity;
  metadata.meshes.push_back(
      {{0, 2}, identity, identity, *bounds, -1, 0, 1, QueryPool::Ground});
  const char *failure = nullptr;
  auto result = WorldGeometry::WithQueryMetadata(std::move(triangles),
                                                 std::move(metadata), failure);
  if (!result)
    error = failure;
  return result;
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 2)
    return 2;
  // Reference immutable observation helpers without executing their drivers.
  (void)&Publish;
  (void)&Text;
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  std::string error;
  std::shared_ptr<const GameplayResources> resources;
  if (!LoadGameplayResources(argv[1], resources, error)) {
    std::cerr << error;
    return 2;
  }
  auto settings = PhysicalSimulationSettings::Load(
      resources->settings, resources->physical_skeleton,
      resources->animation->evaluator->frames.rig, error);
  if (!settings)
    return 2;
  auto empty = PlayerGrindStaticProvider::FromConverted({}, error);
  if (!empty)
    return 2;
  const auto provider =
      std::make_shared<const PlayerGrindStaticProvider>(std::move(*empty));
  const auto count = i.Word();
  o.Word(count);
  for (std::uint32_t c = 0; c < count; ++c) {
    const auto stance = i.Word(), rows = i.Word();
    o.Word(rows);
    auto world = FlatWorld(settings->board.floor_material, error);
    std::unique_ptr<GameplayRuntime> g;
    if (!world || !GameplayRuntime::Create(
                      resources, std::move(*world), provider,
                      settings->Spawn({0, -.035f, 0}), "easy", g, error)) {
      std::cerr << error;
      return 2;
    }
    g->animation->SetCustomisation(stance, 0);
    o.Status(true, "");
    GameplaySnapshot(o, *g);
    for (std::uint32_t n = 0; n < rows; ++n) {
      const auto op = i.Word();
      o.Word(op);
      error.clear();
      bool okay = true;
      switch (op) {
      case 0: {
        const auto tick = i.Wide();
        const auto available = i.Word() != 0;
        okay = g->Advance(
            TickInput(tick, GameplayActions(i.Floats<18>()), available), error);
        break;
      }
      case 1:
        okay = g->TravelTo(i.Matrix(), error);
        break;
      case 2: {
        const auto v = i.Floats<3>();
        g->Launch({v[0], v[1], v[2]});
        break;
      }
      case 3: {
        const auto v = i.Floats<4>();
        okay = g->Tune(v[0], v[1], v[2], v[3], error);
        break;
      }
      case 4: {
        const auto natural = i.Word(), style = i.Word();
        g->animation->SetCustomisation(natural, style);
        break;
      }
      case 5: {
        const auto value = i.Float();
        if (std::isfinite(value) && value > 0)
          g->camera.SetAspectRatio(value);
        break;
      }
      default:
        return 2;
      }
      o.Status(okay, error);
      GameplaySnapshot(o, *g);
    }
  }
  if (i.at != i.data.size())
    return 2;
  for (auto w : o.words)
    for (unsigned lane = 0; lane < 4; ++lane)
      std::cout.put(char(w >> (lane * 8)));
  return std::cout ? 0 : 2;
}
