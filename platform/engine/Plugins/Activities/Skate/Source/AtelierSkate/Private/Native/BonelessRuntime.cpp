// SPDX-License-Identifier: Apache-2.0
#include "BonelessRuntime.h"
#include "GravityScale.h"
#include <cmath>
#include "PlantMath.h"
#include "StockSettingsReader.h"
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
bool BonelessRuntime::Load(const SettingsDatabase &data, std::string &error) {
  StockSettingsReader reader(data);
  BonelessRuntime loaded;
  constexpr const char *names[] = {"Hash_6D781EFAF01E707D",
      "Hash_C9112CCD0BCB1850", "Hash_88D0CDEFA38A36D6",
      "Hash_9228B7F18C223F9C"};
  for (std::size_t n = 0; n < 4; ++n) {
    std::vector<std::uint32_t> words;
    if (!reader.Words("Hash_CCB95A83C78B4FF9", "default", names[n], 20,
                      words, error)) return false;
    for (std::size_t i = 0; i < 8; ++i) {
      loaded.curves_[n].x[i] = plant_math::Float(words[i + 4]);
      loaded.curves_[n].y[i] = plant_math::Float(words[i + 12]);
    }
  }
  *this = loaded;
  error.clear();
  return true;
}
void BonelessRuntime::Enter(PhysicalSimulationRuntime &physical,
                           GroundPhaseLifecycle &life,
                           const ProcessedPhysicsInput &processed) {
  life.board_animated_290 = 1;
  auto &drive = physical.board.HookMut().drive;
  const std::array<std::uint32_t, 4> linear{0x426fffff, 0, 0x4560fffe, 2};
  std::copy(linear.begin(), linear.end(), drive.dynamics.begin());
  drive.EnableAngularSoft();
  right = (processed.flags_2468 & (1u << 26)) != 0;
  toe = right ? 19 : 15;
  anchor = physical.skeleton.record.pose[toe][3];
}
bool BonelessRuntime::Update(BonelessFrame frame, std::string &error) {
  auto o = frame.owners;
  PlantSkeletonFrame plant{o.processed, o.SkeletonOwners(), o.skeleton_input,
                          frame.actual_globals, o.skeleton_air};
  if (!AdvancePlantSkeleton(plant, anchor, toe, error)) return false;
  HoldPlantFoot(o.physical, o.ik, right, anchor, 3);
  if ((o.processed.flags_2480 & (1u << 13)) != 0)
    return Launch(frame, error);
  error.clear();
  return true;
}
bool BonelessRuntime::Launch(BonelessFrame frame, std::string &error) {
  using namespace plant_math;
  auto o = frame.owners;
  const auto &p = o.processed;
  auto vector = [](const RawVector &words) {
    return Vec4{Float(words[0]), Float(words[1]), Float(words[2]), Float(words[3])};
  };
  const auto up = vector(p.vectors_544_560_592_608[0]);
  const auto current = vector(p.vectors_544_560_592_608[3]);
  const auto prepared = vector(p.prepared_jump_704);
  const auto horizontal = Sub(prepared, Scale(up, Dot(prepared, up)));
  const auto speed = Length(horizontal);
  auto vertical = curves_[0].Evaluate(up[1]) * curves_[1].Evaluate(speed);
  if (height_scale != 1.0f || GravityScale() != 1.0f)
    vertical *= std::sqrt(height_scale * GravityScale());
  const auto scaled_speed = curves_[2].Evaluate(speed) * speed;
  const auto a = Madd(up, vertical - Dot(current, up), current);
  const auto b = Madd(Normalize(horizontal), scaled_speed, Scale(up, vertical));
  const auto blend = curves_[3].Evaluate(up[1]);
  auto velocity = Madd(b, blend, Scale(a, 1.0f - blend));
  if (std::fabs(Length(velocity) - Length(current)) > 10.0f) velocity = current;
  const auto forward = vector(p.effective_anim_transform_192[2]);
  const auto component = std::fmax(Dot(velocity, forward), 0.0f);
  if (component < 1.92f) velocity = Madd(forward, 1.92f - component, velocity);
  const auto com = vector(p.vectors_544_560_592_608[2]);
  const auto position = Madd(up, Dot(Sub(anchor, com), up) + 0.25f, com);
  AirLaunchInfo info;
  if (!BindAirLaunchInfo(BindAirPhaseInput(o), info, error)) return false;
  info.start_velocity = velocity;
  info.start_position_override = position;
  info.board_position_override = position;
  info.use_position_override = true;
  info.player_jumped = true;
  AirSelectorInput input;
  if (!BindAirSelectorInput(BindAirPhaseInput(o), o.settings, input, error)) return false;
  bool launched;
  if (!o.trajectory.Launch(info, input, o.physical.world, launched, error)) return false;
  bool valid;
  if (!o.trajectory.Update(input, o.physical.world,
          AirTrajectoryGrindContext::FromProcessed(p, o.physical.DeckFrame()[3]),
          valid, error)) return false;
  error.clear();
  return true;
}
} // namespace atelier::skate
