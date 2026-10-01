// SPDX-License-Identifier: Apache-2.0
#include "FootPhysicalOutput.h"
#include "StockSettingsReader.h"
#include <cmath>
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate {
namespace {
Mat4 InversePhysicalBoard(const Mat4 &board) {
  Mat4 inverse{};
  for (std::size_t axis = 0; axis < 3; ++axis)
    for (std::size_t lane = 0; lane < 3; ++lane)
      inverse[axis][lane] = board[lane][axis];
  for (std::size_t lane = 0; lane < 4; ++lane) {
    const float z = -board[3][2] * inverse[2][lane];
    const float yz = std::fma(-board[3][1], inverse[1][lane], z);
    inverse[3][lane] = std::fma(-board[3][0], inverse[0][lane], yz);
  }
  return inverse;
}
} // namespace
FootPhysicalOutput
FootPhysicalState::Update(const SkeletonPhysicalRecord &record, float dt,
                          FootPhysicalSettings s) {
  const auto inverse = InversePhysicalBoard(record.pose[0]);
  const std::array<Vec4, 2> positions{
      TransformSkeletonPoint(inverse, record.pose[15][3]),
      TransformSkeletonPoint(inverse, record.pose[19][3])};
  float inverse_dt = ReciprocalEstimate(dt);
  for (unsigned n = 0; n < 2; ++n)
    inverse_dt =
        std::fma(inverse_dt, std::fma(-inverse_dt, dt, 1.0f), inverse_dt);
  FootPhysicalOutput result;
  for (std::size_t foot = 0; foot < 2; ++foot)
    for (std::size_t lane = 0; lane < 4; ++lane)
      result.local_velocity[foot][lane] =
          (positions[foot][lane] - previous_local_toes[foot][lane]) *
          inverse_dt;
  previous_local_toes = positions;
  const Vec4 dimensions{s.deck_half_width, 0, s.deck_total_half_length, 0};
  Vec4 bounds;
  for (std::size_t lane = 0; lane < 4; ++lane)
    bounds[lane] = dimensions[lane] + s.padding[lane];
  result.world_velocity = {record.velocities[15], record.velocities[19]};
  for (std::size_t foot = 0; foot < 2; ++foot) {
    const auto &p = positions[foot];
    result.within_deck_box[foot] = std::fabs(p[0]) < bounds[0] &&
                                   std::fabs(p[1]) < bounds[1] &&
                                   std::fabs(p[2]) < bounds[2];
  }
  return result;
}
std::optional<FootPhysicalOutputs>
FootPhysicalOutputs::Load(const SettingsDatabase &data, std::string &error) {
  FootPhysicalOutputs result;
  StockSettingsReader reader(data);
  float width, front, middle;
  if (!reader.Float("physicsdeck", "default", "DeckWidth", width, error))
    return std::nullopt;
  result.settings.deck_half_width = width * 0.5f;
  if (!reader.Float("physicsdeck", "default", "DeckFrontEndSize", front,
                    error) ||
      !reader.Float("physicsdeck", "default", "DeckMidLength", middle, error))
    return std::nullopt;
  result.settings.deck_total_half_length = front + middle * 0.5f;
  std::vector<std::uint32_t> padding;
  if (!reader.Words("physics_skeletonik", "default", "FootOnDeckPadding", 4,
                    padding, error))
    return std::nullopt;
  std::memcpy(result.settings.padding.data(), padding.data(), 16);
  return result;
}
FootPhysicalOutput
FootPhysicalOutputs::Publish(const SkeletonPhysicalRecord &record, float dt) {
  output = state.Update(record, dt, settings);
  return output;
}
} // namespace atelier::skate
