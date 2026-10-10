#include "AirReckoning.h"
#include "PhysicsSkeleton.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace {
float Float(std::uint32_t word) {
  float v;
  std::memcpy(&v, &word, 4);
  return v;
}
std::vector<std::uint8_t> File(const std::string &path) {
  std::ifstream file(path, std::ios::binary);
  if (!file)
    std::abort();
  return {std::istreambuf_iterator<char>(file), {}};
}
struct Input {
  std::vector<std::uint8_t> data;
  std::size_t at = 0;
  std::uint32_t Word() {
    if (at + 4 > data.size())
      std::abort();
    std::uint32_t v = 0;
    for (unsigned i = 0; i < 4; ++i)
      v |= std::uint32_t(data[at++]) << (8 * i);
    return v;
  }
  float Float() { return ::Float(Word()); }
  template <std::size_t N> std::array<std::uint32_t, N> Words() {
    std::array<std::uint32_t, N> v;
    for (auto &w : v)
      w = Word();
    return v;
  }
  template <std::size_t N> std::array<float, N> Floats() {
    std::array<float, N> v;
    for (auto &f : v)
      f = Float();
    return v;
  }
  Mat4 Matrix() {
    Mat4 v;
    for (auto &r : v)
      r = Floats<4>();
    return v;
  }
};
struct Output {
  std::vector<std::uint32_t> words;
  void Word(std::uint32_t w) { words.push_back(w); }
  void Float(float v) {
    std::uint32_t w;
    std::memcpy(&w, &v, 4);
    Word(w);
  }
  template <std::size_t N> void Words(std::array<std::uint32_t, N> v) {
    for (auto w : v)
      Word(w);
  }
  template <std::size_t N> void Floats(std::array<float, N> v) {
    for (float f : v)
      Float(f);
  }
  void Matrix(Mat4 v) {
    for (auto r : v)
      Floats(r);
  }
  void Optional(std::optional<float> v) {
    Word(v.has_value());
    if (v)
      Float(*v);
  }
  void Status(bool okay, const std::string &error) {
    Word(okay);
    if (!okay) {
      Word(std::uint32_t(error.size()));
      for (unsigned char c : error)
        Word(c);
    }
  }
};
PointGraph<8> Graph(Input &i) { return {i.Floats<8>(), i.Floats<8>()}; }
std::optional<float> Optional(Input &i) {
  if (i.Word())
    return i.Float();
  return std::nullopt;
}
PhysicalBodyFlipSettings FlipSettings(Input &i) {
  return {Optional(i), Optional(i), Optional(i), i.Float()};
}
AirReckoningState State(Input &i) {
  AirReckoningState s;
  s.spin_angle = i.Float();
  s.spin_speed = i.Float();
  s.secondary_lean_angle = i.Float();
  s.flip_angle = i.Float();
  s.flip_speed = i.Float();
  s.flip_requested_speed = i.Float();
  s.spin_transform = i.Matrix();
  s.flip_axis = i.Floats<4>();
  s.flip_active = i.Word() != 0;
  s.flip_side = i.Word() != 0;
  return s;
}
void Orientation(Input &i, GroundOrientation &s) {
  const auto xyz = [&] {
    const auto v = i.Floats<3>();
    return Vec3{v[0], v[1], v[2]};
  };
  s.dynamic_up = xyz();
  s.up = xyz();
  s.target = xyz();
  s.up_velocity = xyz();
  s.ground_normal = xyz();
  s.ground_blend = i.Float();
  s.ground_filter.words = i.Words<24>();
  s.slow_filter.words = i.Words<24>();
  s.fast_filter.words = i.Words<24>();
}
ReckoningFrames Frames(Input &i) {
  ReckoningFrames s;
  s.ground = i.Matrix();
  s.system = i.Matrix();
  s.unflipped = i.Matrix();
  s.inverse_system = i.Matrix();
  s.body_flip = i.Matrix();
  s.heading = i.Floats<4>();
  s.target_lean_angle = i.Float();
  s.lateral_tilt = i.Floats<4>();
  return s;
}
void StateOut(Output &o, const AirReckoningState &s) {
  o.Floats(std::array<float, 6>{s.spin_angle, s.spin_speed,
                                s.secondary_lean_angle, s.flip_angle,
                                s.flip_speed, s.flip_requested_speed});
  o.Matrix(s.spin_transform);
  o.Floats(s.flip_axis);
  o.Word(s.flip_active);
  o.Word(s.flip_side);
}
void FramesOut(Output &o, const ReckoningFrames &s) {
  for (auto m :
       {s.ground, s.system, s.unflipped, s.inverse_system, s.body_flip})
    o.Matrix(m);
  o.Floats(s.heading);
  o.Float(s.target_lean_angle);
  o.Floats(s.lateral_tilt);
}
void SettingsOut(Output &o, const AirReckoningSettings &s) {
  o.Floats(s.ground_normal_smoothing);
  for (auto g : {s.max_up_angle_delta, s.tilt_vs_rotation, s.tilt_vs_slope}) {
    o.Floats(g.x);
    o.Floats(g.y);
  }
  o.Floats(std::array<float, 2>{s.body_spin.derivative_floor,
                                s.body_spin.acceleration_limit});
  for (auto g : s.body_spin.curves) {
    o.Floats(g.x);
    o.Floats(g.y);
  }
  o.Floats(s.body_spin.input_fade_threshold);
  o.Optional(s.body_flip.smoothing);
  o.Optional(s.body_flip.maximum_speed);
  o.Optional(s.body_flip.spin_scale);
  o.Float(s.body_flip.missing_attribute_value);
}
void RuntimeOut(Output &o, const AirReckoning &a,
                const PhysicalRidingOutputs &r) {
  StateOut(o, a.state);
  o.Words(r.body_spin);
  const auto &s = r.reckoning;
  for (auto v : {s.dynamic_up, s.up, s.target, s.up_velocity, s.ground_normal})
    o.Floats(std::array<float, 3>{v.x, v.y, v.z});
  o.Float(s.ground_blend);
  o.Words(s.ground_filter.words);
  o.Words(s.slow_filter.words);
  o.Words(s.fast_filter.words);
  FramesOut(o, r.reckoning_frames);
  SettingsOut(o, a.settings);
  for (auto m : a.modes) {
    o.Word(m.easy_body_spins);
    o.Word(m.perfect_body_flips);
  }
  for (auto g : a.stock_spin_curves) {
    o.Floats(g.x);
    o.Floats(g.y);
  }
  o.Float(a.stock_spin_acceleration);
}
AirReckoningInput CoreInput(Input &i) {
  return {i.Floats<4>(), i.Float(),     i.Float(),     i.Float(),
          i.Floats<4>(), i.Float(),     i.Float(),     i.Float(),
          i.Word() != 0, i.Word() != 0, i.Word() != 0, i.Word() != 0,
          i.Word() != 0};
}
void FieldsOut(Output &o, PhysicsAirReckoningFields f) {
  o.Floats(f.current_landing_normal_1152);
  o.Floats(f.collision_reference_normal_1216);
  o.Floats(
      std::array<float, 2>{f.body_spin_angle_1568, f.body_spin_speed_1572});
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 7)
    return 2;
  SettingsDatabase stock;
  PhysicsSkeletons definitions;
  AnimationPoseFrames poses;
  std::string error;
  if (!stock.Load(File(argv[2]), error) ||
      !definitions.Load(File(argv[3]), argv[5], error) ||
      !poses.rig.Load(File(argv[4]), error)) {
    std::cerr << error;
    return 2;
  }
  const auto *definition = definitions.Find("PHYS_TPOSE");
  if (!definition)
    return 2;
  AnimationPoseEvaluator evaluator(std::move(poses));
  if (!evaluator.LoadAuthoredClips(argv[6], error)) {
    std::cerr << error;
    return 2;
  }
  const auto settings = PhysicalSimulationSettings::Load(
      stock, *definition, evaluator.frames.rig, error);
  if (!settings) {
    std::cerr << error;
    return 2;
  }
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  const auto count = i.Word();
  o.Word(count);
  for (unsigned c = 0; c < count; ++c) {
    const auto rows = i.Word();
    o.Word(rows);
    SettingsDatabase data;
    if (!data.Load(File(std::string(argv[1]) + "/case-" + std::to_string(c) +
                        "/settings.simulation"),
                   error)) {
      std::cerr << error;
      return 2;
    }
    AirReckoning a;
    const bool loaded = a.Load(data, error);
    o.Status(loaded, error);
    if (!loaded) {
      if (rows)
        std::abort();
      continue;
    }
    auto physical = PhysicalSimulationRuntime::Initialize(
        *settings, stock, evaluator, WorldGeometry(std::vector<WorldTriangle>{}),
        settings->Spawn({0, -.035f, 0}), error);
    if (!physical) {
      std::cerr << error;
      return 2;
    }
    auto &r = physical->riding;
    RuntimeOut(o, a, r);
    for (unsigned n = 0; n < rows; ++n) {
      const auto op = i.Word();
      o.Word(op);
      switch (op) {
      case 0:
        a.state = State(i);
        r.body_spin = i.Words<44>();
        Orientation(i, r.reckoning);
        r.reckoning_frames = Frames(i);
        break;
      case 1: {
        ProcessedPhysicsInput p{};
        p.flags_2468 = i.Word();
        p.flags_2472 = i.Word();
        p.flags_2484 = i.Word();
        p.state_variant_index_2528 = i.Word();
        p.timestep_2604 = i.Float();
        p.grind_adjusted_body_spin_2644 = i.Float();
        p.animation_com_to_deck_752 = i.Words<4>();
        const float body = i.Float();
        const auto normal = i.Floats<4>();
        const float blend = i.Float(), target = i.Float(), flip = i.Float();
        PhysicsAirReckoningFields f;
        const bool okay =
            a.Update(r, p, body, normal, blend, target, flip, f, error);
        o.Status(okay, error);
        if (okay)
          FieldsOut(o, f);
        break;
      }
      case 2: {
        ProcessedPhysicsInput p{};
        p.flags_2468 = i.Word();
        const auto up = i.Floats<4>(), heading = i.Floats<4>();
        a.UpdatePlant(r, p, up, heading);
        break;
      }
      case 3:
        a.SetSpinScale(i.Float());
        break;
      case 4:
        a.state.ResetSpin();
        break;
      case 5: {
        const float input = i.Float(), automatic = i.Float();
        const bool air = i.Word() != 0;
        const auto mode = std::uint8_t(i.Word());
        if (!UpdatePhysicalBodySpin(r.body_spin, a.settings.body_spin, input,
                                    automatic, air, mode, error))
          std::abort();
        break;
      }
      case 6:
        if (!UpdatePhysicalBodySpinGround(r.body_spin, i.Float(), error))
          std::abort();
        break;
      case 7: {
        const auto words = i.Words<44>();
        o.Status(SetPhysicalBodySpinWords(r.body_spin, words, error), error);
        break;
      }
      case 8: {
        PhysicalBodyFlipState s{i.Float(), i.Float(), i.Float(), i.Matrix(),
                                i.Matrix()};
        const auto settings = FlipSettings(i);
        const PhysicalBodyFlipInput input{i.Float(),     i.Float(),
                                          i.Floats<4>(), i.Floats<4>(),
                                          i.Float(),     i.Word() != 0};
        UpdatePhysicalBodyFlip(s, settings, input);
        o.Floats(std::array<float, 3>{s.angle, s.speed, s.requested_speed});
        o.Matrix(s.spin_transform);
        o.Matrix(s.combined_transform);
        break;
      }
      case 9: {
        const auto target = i.Floats<4>(), from = i.Floats<4>();
        o.Floats(
            ClampAirReckoningVectorWithinMaxAngle(target, from, i.Float()));
        break;
      }
      case 10:
        a.settings.body_spin.derivative_floor = i.Float();
        a.settings.body_spin.acceleration_limit = i.Float();
        for (auto &g : a.settings.body_spin.curves)
          g = Graph(i);
        a.settings.body_spin.input_fade_threshold = i.Floats<4>();
        break;
      case 11:
        if (!UpdateAirReckoning(r.reckoning, r.reckoning_frames, r.body_spin,
                                a.state, a.settings, CoreInput(i), error))
          std::abort();
        break;
      case 12:
        a.settings.body_flip = FlipSettings(i);
        break;
      case 13:
        FieldsOut(o, a.Fields(r));
        break;
      default:
        std::abort();
      }
      RuntimeOut(o, a, r);
    }
  }
  if (i.at != i.data.size())
    std::abort();
  for (auto w : o.words) {
    char b[4];
    for (unsigned n = 0; n < 4; ++n)
      b[n] = char(w >> (8 * n));
    std::cout.write(b, 4);
  }
}
