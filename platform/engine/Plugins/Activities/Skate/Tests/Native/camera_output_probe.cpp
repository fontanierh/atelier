#include "AnimationMetadata.h"
#include "CameraOutputRuntime.h"
#include "PhysicsSkeleton.h"
#include "StockSettingsReader.h"
#include <cassert>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <type_traits>

using namespace atelier::skate;
using namespace atelier::skate::camera;
struct Input {
  std::vector<std::uint8_t> data;
  std::size_t at = 0;
  std::uint32_t Word() {
    assert(at + 4 <= data.size());
    const auto value = std::uint32_t(data[at]) |
                       (std::uint32_t(data[at + 1]) << 8) |
                       (std::uint32_t(data[at + 2]) << 16) |
                       (std::uint32_t(data[at + 3]) << 24);
    at += 4;
    return value;
  }
  float Float() {
    const auto word = Word();
    float value;
    std::memcpy(&value, &word, 4);
    return value;
  }
  std::string String() {
    const auto size = Word();
    assert(size <= data.size() - at);
    std::string result(reinterpret_cast<const char *>(data.data() + at), size);
    at += size;
    return result;
  }
};
struct Output {
  std::vector<std::uint8_t> data;
  void Word(std::uint32_t value) {
    for (unsigned shift = 0; shift < 32; shift += 8)
      data.push_back(std::uint8_t(value >> shift));
  }
  void Float(float value) {
    std::uint32_t word;
    std::memcpy(&word, &value, 4);
    Word(word);
  }
  void String(std::string_view value) {
    Word(std::uint32_t(value.size()));
    data.insert(data.end(), value.begin(), value.end());
  }
  void Status(bool okay, const std::string &error) {
    Word(okay);
    if (!okay)
      String(error);
  }
};
template <class T> T ReadValue(Input &input);
void WriteValue(Output &o, float value) { o.Float(value); }
void WriteValue(Output &o, std::uint32_t value) { o.Word(value); }
void WriteValue(Output &o, std::int32_t value) { o.Word(std::uint32_t(value)); }
void WriteValue(Output &o, std::uint64_t value) {
  o.Word(std::uint32_t(value));
  o.Word(std::uint32_t(value >> 32));
}
void WriteValue(Output &o, std::uint8_t value) { o.Word(value); }
void WriteValue(Output &o, bool value) { o.Word(value); }
void WriteValue(Output &o, const std::string &value) { o.String(value); }
void WriteValue(Output &o, const Basis3 &value) {
  for (const auto &column : value.columns)
    for (float lane : column)
      o.Float(lane);
}
void WriteValue(Output &, const graph::Frame &);
void WriteValue(Output &, const graph::ActiveBehavior &);
void WriteValue(Output &, const graph::Controller &);
// @OWNER_FIXTURE_CPP@
// @CPP_OBSERVERS@

void WriteValue(Output &output, const graph::Frame &value) {
  WriteValue(output, value.dt);
  WriteValue(output, value.current);
  WriteValue(output, value.last);
  WriteValue(output, value.state_times);
}
void WriteValue(Output &output, const graph::ActiveBehavior &value) {
  WriteValue(output, value.behavior);
  WriteValue(output, value.instance);
}
void WriteValue(Output &output, const graph::Controller &value) {
  WriteValue(output, value.frame);
  WriteValue(output, value.active);
}
std::vector<std::uint8_t> File(const std::string &path) {
  std::ifstream stream(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(stream),
          std::istreambuf_iterator<char>()};
}
void ObserveRuntime(Output &output, const CameraRuntime &runtime) {
  WriteValue(output, runtime.manager);
  WriteValue(output, runtime.subject);
  WriteValue(output, runtime.graph.controller);
  WriteValue(output, runtime.graph.slow_motion);
  WriteValue(output, runtime.trajectories);
  WriteValue(output, runtime.frame);
  WriteValue(output, runtime.latest_subject);
  WriteValue(output, runtime.simulation_rate_requests);
  WriteValue(output, runtime.graph.printed_messages);
}
WorldGeometry ReadWorld(Input &input) {
  std::vector<WorldTriangle> triangles;
  const auto count = input.Word();
  for (std::uint32_t index = 0; index < count; ++index) {
    std::array<Vec3, 3> vertices;
    for (auto &vertex : vertices)
      vertex = {input.Float(), input.Float(), input.Float()};
    const auto fatness = input.Float();
    const auto edges = ReadValue<std::array<float, 3>>(input);
    const auto flags = input.Word();
    const ContactMaterial material{input.Float(), input.Float(), input.Float()};
    const auto tag = input.Word();
    triangles.push_back(
        {TriangleFromVolume(vertices, fatness, edges, flags), material, tag});
  }
  return WorldGeometry(std::move(triangles));
}

namespace {
RawVector Raw(Vec4 value) {
  RawVector out;
  for (std::size_t i = 0; i < 4; ++i)
    std::memcpy(&out[i], &value[i], 4);
  return out;
}
Vec3 Three(const std::array<float, 3> &value) {
  return {value[0], value[1], value[2]};
}
AffineTransform Affine(Mat4 value) {
  Basis3 basis;
  for (std::size_t i = 0; i < 3; ++i)
    for (std::size_t j = 0; j < 3; ++j)
      basis.columns[i][j] = value[i][j];
  return {basis, {value[3][0], value[3][1], value[3][2]}};
}
bool LoadGraph(const std::string &path, AnimationLoadedGraph &value,
               std::string &error) {
  return value.source.Load(File(path), error) &&
         value.binding.Bind(value.source, error) &&
         value.runtime.FromBinding(value.binding, error);
}
struct CompletedOwners {
  ProcessedPhysicsInput processed;
  PhysicalPlayerInput physical;
  std::optional<BoardToolkit> toolkit;
  GroundStateRuntime ground;
  PhysicsAnimationInput animation_input;
  AnimationPhysicalFeedback feedback;
  CentreOfMassFilter com;
  CentreOfMassOutput com_output;
  SimulationExchange exchange{0};
};
void Install(const CameraOwnerFixture &f, PhysicalSimulationRuntime &p,
             SkaterAnimation &animation, CompletedOwners &s) {
  p.ticks = f.ticks;
  p.board.SetTransform(Affine(f.board_transform));
  p.riding.motion.effective_basis = {f.effective_basis};
  p.roots.animation_to_world = f.skeleton_root;
  for (std::size_t i = 0; i < 26; ++i)
    p.skeleton.record.pose[i][3] = f.bone_positions[i];
  s.toolkit =
      f.toolkit_present
          ? std::optional<BoardToolkit>(BoardToolkit::FromBoard(
                p.board, f.flags_2468, f.deck_speed, f.axis_464, {0, 1, 0, 0}))
          : std::nullopt;
  auto &processed = s.processed;
  processed.flags_2468 = f.flags_2468;
  processed.flags_2472 = f.flags_2472;
  processed.flags_2476 = f.flags_2476;
  processed.flags_2480 = f.flags_2480;
  processed.flags_2484 = f.flags_2484;
  processed.state_2508 = f.processed_state;
  processed.category_2512 = f.processed_category;
  processed.state_variant_index_2528 = f.state_variant;
  processed.spin_input_2672 = f.spin;
  processed.time_since_last_input_2748 = f.input_age;
  processed.scalar_2652 = f.deck_speed;
  processed.state_timer_2664 = f.state_timer;
  processed.vectors_464_480_496_512_528[0] = Raw(f.axis_464);
  processed.vectors_544_560_592_608[3] = Raw(f.velocity_608);
  auto &physical = s.physical;
  physical.state.state_16 = f.physical_state;
  physical.state.category_12 = f.physical_category;
  physical.state.surface_height_32 = f.surface_height;
  physical.reckoning.vector_64 = Raw(f.centre_of_mass);
  physical.reckoning.vector_96 = Raw(f.reckoning_up);
  physical.skateboard.vector_80 = Raw(f.board_velocity);
  physical.skateboard.vector_64 = Raw(f.board_angular_velocity);
  physical.ground.vector_96 = Raw(f.last_ground_up);
  physical.air.trajectory_apex_0 = Raw(f.air.apex_0);
  physical.air.collision_position_16 = Raw(f.air.landing_position_16);
  physical.air.landing_normal_32 = Raw(f.air.landing_normal_32);
  physical.air.selector_vector_48 = Raw(f.air.launch_position_48);
  physical.air.landing_heading_80 = Raw(f.air.heading_80);
  physical.air.time_in_state_176 = f.air.time_176;
  physical.air.collision_time_180 = f.air.duration_180;
  physical.air.time_to_apex_196 = f.air.apex_time_196;
  physical.air.known_air_valid_437 = f.air_valid;
  physical.air.use_air_reckoning_452 = f.air_reckoning;
  physical.air.scalar_184 = f.slow_motion_air_duration;
  auto &off = physical.off_board;
  off.scalar_92 = f.offboard.duration_92;
  off.scalar_152 = f.offboard.time_152;
  off.scalar_156 = f.offboard.apex_time_156;
  off.vector_160 = Raw(f.offboard.launch_normal_160);
  off.vector_176 = Raw(f.offboard.launch_position_176);
  off.vector_192 = Raw(f.offboard.landing_normal_192);
  off.vector_208 = Raw(f.offboard.landing_position_208);
  off.vector_224 = Raw(f.offboard.heading_224);
  off.vector_240 = Raw(f.offboard.apex_240);
  off.flag_308 = f.offboard.object_held_304;
  off.hippy_hurdling_317 = f.offboard.hurdle_317;
  off.trajectory_valid_331 = f.offboard.use_trajectory_331;
  off.flag_334 = f.offboard.dropping_in_334;
  physical.grinds.direction_0 = Raw(f.grinds.direction_0);
  physical.grinds.camera_target_96 = Raw(f.grinds.camera_target_96);
  physical.grinds.grinding_316 = f.grinds.grinding_316;
  physical.scoring.capabilities_204 = f.capabilities;
  physical.animation.profile_148 = f.profile;
  physical.ground.hippy_jumping_322 = f.hippy_jump;
  animation.state.flags = f.animation_flags;
  animation.packet.riding_fakie = f.packet_fakie;
  s.animation_input.fields.balance = f.balance;
  s.animation_input.fields.turn = f.turn;
  s.animation_input.extra.look_x = f.look[0];
  s.animation_input.extra.look_y = f.look[1];
  s.animation_input.output.flags = f.intents;
  s.feedback.conditioned_turn = f.conditioned_turn;
  s.ground.pumping.pump_acceleration = f.pumping;
  if (f.com_reset)
    s.com.Reset();
  s.com_output = s.com.Update(f.com_input_position, f.com_input_velocity);
  s.exchange = SimulationExchange(f.output_tick);
  if (f.output_present)
    s.exchange.PublishOutput(
        {f.output_tick,
         *ParsePhysicalStateId(f.output_state),
         {f.board_transform[3][0], f.board_transform[3][1],
          f.board_transform[3][2]},
         {f.board_velocity[0], f.board_velocity[1], f.board_velocity[2]},
         {f.skeleton_root[3][0], f.skeleton_root[3][1], f.skeleton_root[3][2]},
         {},
         Three(f.ground_normal),
         7,
         Three(f.predicted_position),
         f.physical_category == 100,
         (f.flags_2468 & (1 << 18)) != 0,
         false,
         {}});
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 6)
    return 2;
  const std::string fixtures = argv[1], samples = argv[2], metadata = argv[3],
                    assets = argv[4], source_sha = argv[5];
  std::string error;
  SettingsDatabase data;
  PhysicsSkeletons skeletons;
  AnimationPoseFrames frames;
  auto source = std::make_shared<AnimationSource>();
  AnimationMetadata second;
  if (!data.Load(File(fixtures + "/settings.native"), error) ||
      !skeletons.Load(File(fixtures + "/physics.native"), source_sha, error) ||
      !frames.rig.Load(File(samples + "/rig.skate"), error) ||
      !source->metadata.Load(File(metadata + "/bank-0.skate"), error) ||
      !second.Load(File(metadata + "/bank-1.skate"), error) ||
      !source->metadata.Merge(second, error)) {
    std::cerr << error;
    return 2;
  }
  source->evaluator =
      std::make_shared<AnimationPoseEvaluator>(std::move(frames));
  if (!source->evaluator->LoadAuthoredClips(assets, error)) {
    std::cerr << error;
    return 2;
  }
  const auto *definition = skeletons.Find("PHYS_TPOSE");
  if (!definition)
    return 2;
  const auto settings = PhysicalSimulationSettings::Load(
      data, *definition, source->evaluator->frames.rig, error);
  if (!settings) {
    std::cerr << error;
    return 2;
  }
  AnimationStockGraphs graphs;
  if (!LoadGraph(fixtures + "/actor.action.native", graphs.action, error) ||
      !LoadGraph(fixtures + "/actor.motion.native", graphs.motion, error)) {
    std::cerr << error;
    return 2;
  }
  Input input{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output output;
  const auto cases = input.Word();
  output.Word(cases);
  for (std::uint32_t c = 0; c < cases; ++c) {
    std::unique_ptr<SkaterAnimation> animation;
    if (!SkaterAnimation::FromSource(data, graphs, "", source, animation,
                                     error)) {
      std::cerr << error;
      return 2;
    }
    auto world = ReadWorld(input);
    const auto camera_id = input.Word();
    auto physics = PhysicalSimulationRuntime::Initialize(
        *settings, data, *source->evaluator, std::move(world),
        settings->Spawn({0, -.035f, 0}), error);
    if (!physics) {
      std::cerr << error;
      return 2;
    }
    auto p = std::move(*physics);
    CompletedOwners s;
    if (!s.ground.Load(data, true, error) ||
        !s.animation_input.Load(data, source->evaluator->frames.rig, "normal",
                                error)) {
      std::cerr << error;
      return 2;
    }
    CameraRuntime camera;
    Graph camera_graph;
    if (!camera_graph.Load(File(fixtures + "/camera-" +
                                std::to_string(camera_id) + "/graph.native"),
                           error) ||
        !camera.Load(data, camera_graph,
                     File(fixtures + "/camera-" + std::to_string(camera_id) +
                          "/camera.native"),
                     error)) {
      std::cerr << error;
      return 2;
    }
    const auto rows = input.Word();
    output.Word(rows);
    for (std::uint32_t row = 0; row < rows; ++row) {
      const auto op = input.Word();
      output.Word(op);
      const auto f = ReadValue<CameraOwnerFixture>(input);
      Install(f, p, *animation, s);
      const CameraPublicationFrame frame{
          p,
          s.processed,
          s.physical,
          s.toolkit ? &*s.toolkit : nullptr,
          s.ground,
          s.animation_input,
          *animation,
          s.feedback,
          s.com_output,
          *ParsePhysicalStateId(f.selected_state),
          f.state_flag_81};
      const PhysicalOutputSnapshot original{
          f.publication_tick,
          *ParsePhysicalStateId(f.selected_state),
          {},
          {},
          {},
          {},
          Three(f.ground_normal),
          0,
          Three(f.predicted_position),
          false,
          false,
          false,
          {}};
      auto publication =
          PublishCameraOutput(frame, original, f.preferences,
                              std::uint8_t(animation->Stance().second),
                              f.context, f.publication_tick);
      if (op == 2) {
        publication.events.broken_bone_duration_200 =
            f.override_broken_duration;
        publication.ground_scalar_288 = f.override_ground_scalar;
      }
      WriteValue(output, publication);
      CameraSubjectSnapshot snapshot;
      const bool okay =
          PublishCameraSubject(frame, publication, snapshot, error);
      output.Status(okay, error);
      if (okay)
        WriteValue(output, snapshot);
      if (op == 1) {
        CameraOutputResult result;
        const bool advanced =
            AdvanceCameraOutput(frame, s.exchange, camera, result, error);
        output.Status(advanced, error);
        if (advanced)
          assert(result.simulation_rate_requests ==
                 &camera.simulation_rate_requests);
      }
      ObserveRuntime(output, camera);
      WriteValue(output, s.com_output.velocity);
      WriteValue(output, s.com_output.acceleration);
      WriteValue(output, s.com_output.position);
    }
  }
  assert(input.at == input.data.size());
  std::cout.write(reinterpret_cast<const char *>(output.data.data()),
                  std::streamsize(output.data.size()));
}
