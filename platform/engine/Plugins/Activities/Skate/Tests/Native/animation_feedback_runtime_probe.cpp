// SPDX-License-Identifier: Apache-2.0
#include "AnimationFeedbackRuntime.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace {
std::vector<std::uint8_t> File(const char *path) {
  std::ifstream f(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(f), {}};
}
struct Input : detail::DataReader {
  explicit Input(const std::vector<std::uint8_t> &b) : DataReader{b} { at = 0; }
  Vec4 Vector() {
    Vec4 out;
    for (auto &v : out)
      v = Float();
    return out;
  }
  Vec3 Vector3() { return {Float(), Float(), Float()}; }
  Mat4 Matrix() {
    Mat4 out;
    for (auto &v : out)
      v = Vector();
    return out;
  }
  BoardMotionOutput Motion() {
    BoardMotionOutput m;
    m.angular_velocity = Vector3();
    m.linear_velocity = Vector3();
    m.ground_velocity = Vector3();
    m.speed = Float();
    m.ground_speed = Float();
    m.forward_speed = Float();
    for (auto &c : m.effective_basis.columns)
      for (auto &v : c)
        v = Float();
    return m;
  }
  PumpingState Pumping() {
    PumpingState p;
    p.previous_position = Vector();
    p.previous_normal = Vector();
    for (auto v :
         {&p.smoothed_height_change, &p.pumping_time, &p.previous_height,
          &p.pumping, &p.pump_acceleration, &p.angular_speed, &p.absorption,
          &p.ground_normal_absorption, &p.minimum_crouch,
          &p.deck_angle_absorption, &p.reset_only_scalar})
      *v = Float();
    p.record_valid = Word() != 0;
    p.intentional_pumping = std::uint8_t(Word());
    return p;
  }
};
struct Output {
  std::vector<std::uint8_t> bytes;
  void Word(std::uint32_t v) {
    for (unsigned lane = 0; lane < 4; ++lane)
      bytes.push_back(std::uint8_t(v >> (lane * 8)));
  }
  void Float(float v) {
    std::uint32_t word;
    std::memcpy(&word, &v, 4);
    Word(word);
  }
  template <std::size_t N> void Floats(const std::array<float, N> &values) {
    for (auto v : values)
      Float(v);
  }
  void Status(bool ok, const std::string &error) {
    Word(ok);
    Word(ok ? 0 : std::uint32_t(error.size()));
    if (!ok)
      bytes.insert(bytes.end(), error.begin(), error.end());
  }
  void Owner(const AnimationFeedbackRuntime &o) {
    const auto &s = o.settings;
    for (auto c : s.filter_coefficients)
      Floats(c);
    for (auto p : {s.input_curve, s.quickness_curve, s.speed_curve}) {
      Floats(p.x);
      Floats(p.y);
    }
    Floats(s.smoothing_curve.x);
    Floats(s.smoothing_curve.y);
    Floats(s.parameters);
    Float(o.bump_settings.scale_x_acc);
    Float(o.bump_settings.min_bump_mag);
    Floats(o.state.history);
    for (auto f : o.state.filters)
      Floats(f);
    Floats(o.previous_lateral_tilt);
    Floats(o.published_previous_lateral_tilt);
  }
  void Feedback(const AnimationPhysicalFeedback &v) {
    const auto t = v.turning;
    Floats(std::array<float, 6>{t.field_32, t.field_36, t.field_52, t.field_56,
                                t.field_60, t.body_168});
    const auto c = v.crouching;
    Floats(std::array<float, 8>{c.body_84, c.body_164, c.body_188, c.force_516,
                                c.ground_force_520, c.minimum_crouch_528,
                                c.deck_angle_532, c.animation_height_72});
    Float(v.pumping_acceleration);
    Floats(v.ground_acceleration);
    Word(v.bumped);
    Floats(v.conditioned_turn);
  }
};
} // namespace
int main(int argc, char **argv) {
  if (argc != 2)
    return 2;
  SettingsDatabase data;
  std::string error;
  if (!data.Load(File(argv[1]), error)) {
    std::cerr << error;
    return 2;
  }
  const auto raw =
      std::vector<std::uint8_t>{std::istreambuf_iterator<char>(std::cin), {}};
  Input input(raw);
  Output out;
  const auto count = input.Word();
  out.Word(count);
  for (std::uint32_t c = 0; c < count; ++c) {
    const auto commands = input.Word();
    out.Word(commands);
    AnimationFeedbackRuntime owner;
    const auto ok = owner.Load(data, error);
    out.Status(ok, error);
    if (!ok) {
      if (commands)
        return 2;
      continue;
    }
    out.Owner(owner);
    for (std::uint32_t j = 0; j < commands; ++j) {
      const auto op = input.Word();
      out.Word(op);
      if (op == 0) {
        const auto motion = input.Motion();
        const auto pumping = input.Pumping();
        SpeedWobbleState wobble;
        for (auto &w : wobble.words)
          w = input.Word();
        const AnimationReckoningFeedback reckoning{
            input.Vector3(), input.Vector3(), input.Vector3(), input.Float()};
        const AnimationControlFeedback controls{input.Word(), input.Float(),
                                                input.Word() != 0};
        const AnimationGroundAccelerationInput acceleration{
            input.Matrix(), input.Matrix(), input.Vector()};
        const auto lateral = input.Vector();
        out.Feedback(owner.Update(motion, pumping, wobble, reckoning, controls,
                                  acceleration, lateral));
      } else if (op == 1)
        owner.Reset();
      else if (op == 2) {
        if (!owner.Load(data, error))
          return 2;
      } else
        return 2;
      out.Owner(owner);
    }
  }
  if (!input.ok || input.Remaining() != 0)
    return 2;
  std::cout.write(reinterpret_cast<const char *>(out.bytes.data()),
                  std::streamsize(out.bytes.size()));
  return 0;
}
