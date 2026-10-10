#include "GroundAnimationSettings.h"
#include "GroundJumpMath.h"
#include "StockSettingsReader.h"
namespace atelier::skate {
bool GroundAnimationSettings::Load(const SettingsDatabase &data,
                                   std::string &error) {
  GroundAnimationSettings next;
  const StockSettingsReader read(data);
  std::vector<std::uint32_t> words;
  if (!read.Words("physics_jump", "default", "VerticalResponse", 32, words,
                  error))
    return false;
  constexpr std::array<std::string_view, 5> keys{"easy", "normal", "hardcore",
                                                 "motorized", "test"};
  for (std::size_t i = 0; i < keys.size(); ++i) {
    auto &m = next.modes[i];
    if (!read.Float("physics_mode", keys[i], "Hash_BE3F74F978D777E5",
                    m.minimum_height_64, error) ||
        !read.Float("physics_mode", keys[i], "JumpMinHeight",
                    m.minimum_height_68, error) ||
        !read.Float("physics_mode", keys[i], "JumpMaxHeight", m.maximum_height,
                    error))
      return false;
  }
  auto &s = next.jump;
  for (std::size_t i = 0; i < 16; ++i) {
    s.vertical_response.x[i] = ground_jump_math::Float(words[i]);
    s.vertical_response.y[i] = ground_jump_math::Float(words[16 + i]);
  }
  const auto graph = [&](std::string_view name, bool negative,
                         PointGraph<8> &output) {
    const std::size_t count = negative ? 20 : 16;
    if (!read.Words("physics_jump", "default", name, count, words, error))
      return false;
    const std::size_t offset = negative ? 4 : 0;
    for (std::size_t i = 0; i < 8; ++i) {
      output.x[i] = ground_jump_math::Float(words[offset + i]);
      output.y[i] = ground_jump_math::Float(words[offset + 8 + i]);
    }
    return true;
  };
  if (!graph("JumpYScalarVsGroundNormalY", true, s.y_scalar_vs_normal_y) ||
      !graph("JumpSpeedScalarVsAngle", true, s.speed_scalar_vs_angle) ||
      !graph("MinHeightVsSpeed", false, s.minimum_height_vs_speed) ||
      !graph("MaxHeightVsSpeed", false, s.maximum_height_vs_speed))
    return false;
  const auto scalar = [&](std::string_view name, float &out) {
    return read.Float("physics_jump", "default", name, out, error);
  };
  if (!scalar("SpeedResponseMaxSpeed", s.speed_response_max_speed) ||
      !scalar("MinScalar", s.minimum_scalar) ||
      !scalar("JumpYBonusMax", s.maximum_y_bonus) ||
      !scalar("JumpAdjustZFactor", s.adjust_z_factor) ||
      !scalar("JumpAdjustXFactor", s.adjust_x_factor) ||
      !scalar("AbsoluteMinHeight", s.absolute_minimum_height) ||
      !scalar("HippyJumpMinHeight", s.hippy_minimum_height) ||
      !scalar("HippyJumpMaxHeight", s.hippy_maximum_height))
    return false;
  *this = std::move(next);
  error.clear();
  return true;
}
} // namespace atelier::skate
