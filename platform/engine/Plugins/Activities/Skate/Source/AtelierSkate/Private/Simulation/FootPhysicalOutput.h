#pragma once
#include "Settings.h"
#include "SkeletonBody.h"
namespace atelier::skate {
struct FootPhysicalSettings {
  float deck_half_width = 0, deck_total_half_length = 0;
  Vec4 padding{};
};
struct FootPhysicalOutput {
  std::array<Vec4, 2> local_velocity{}, world_velocity{};
  std::array<bool, 2> within_deck_box{};
};
struct FootPhysicalState {
  std::array<Vec4, 2> previous_local_toes{};
  void Reset() { *this = {}; }
  FootPhysicalOutput Update(const SkeletonPhysicalRecord &, float dt,
                            FootPhysicalSettings);
};
// Sole retained SkeletonIK3136/3152 history and completed foot publication.
class FootPhysicalOutputs {
public:
  FootPhysicalState state;
  FootPhysicalSettings settings;
  FootPhysicalOutput output;
  static std::optional<FootPhysicalOutputs> Load(const SettingsDatabase &,
                                                 std::string &error);
  FootPhysicalOutput Publish(const SkeletonPhysicalRecord &, float dt);
};
} // namespace atelier::skate
