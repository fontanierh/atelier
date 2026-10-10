#pragma once
#include "BodyFlip.h"
#include "BodySpin.h"
#include "PhysicalSimulationRuntime.h"
#include "PlantTrajectoryQueries.h"
#include "PlayerInputTypes.h"
namespace atelier::skate {
struct AirReckoningState {
  float spin_angle = 0, spin_speed = 0, secondary_lean_angle = 0;
  float flip_angle = 0, flip_speed = 0, flip_requested_speed = 0;
  Mat4 spin_transform = SkeletonIdentity;
  Vec4 flip_axis{1, 0, 0, 0};
  bool flip_active = false, flip_side = false;
  void ResetSpin() { spin_angle = spin_speed = 0; }
};
struct AirReckoningSettings {
  Vec4 ground_normal_smoothing;
  PointGraph<8> max_up_angle_delta, tilt_vs_rotation, tilt_vs_slope;
  PhysicalBodySpinSettings body_spin;
  PhysicalBodyFlipSettings body_flip;
};
struct AirReckoningInput {
  Vec4 landing_normal;
  float normal_blend, target_spin, flip_request;
  Vec4 com_to_deck;
  float timestep, physical_body_spin, grind_adjusted_body_spin;
  bool additive_spin, direct_spin, reverse_stance, easy_body_spins,
      perfect_body_flips;
};
struct AirReckoningMode {
  bool easy_body_spins, perfect_body_flips;
};
// Original 82BD3E78 includes all four lanes and parallel endpoint magnitude.
Vec4 ClampAirReckoningVectorWithinMaxAngle(Vec4 target, Vec4 from,
                                           float maximum);
bool UpdateAirReckoning(GroundOrientation &, ReckoningFrames &,
                        PhysicalBodySpinState &, AirReckoningState &,
                        const AirReckoningSettings &, const AirReckoningInput &,
                        std::string &);
bool UpdatePlantAirReckoning(GroundOrientation &, ReckoningFrames &,
                             PhysicalBodySpinState &, AirReckoningState &,
                             const AirReckoningSettings &, Vec4 up,
                             Vec4 heading, bool reverse, std::string &);
class AirReckoning final : public HandplantAirReckoning {
public:
  AirReckoningState state;
  AirReckoningSettings settings;
  std::array<AirReckoningMode, 5> modes;
  std::array<PointGraph<8>, 7> stock_spin_curves;
  float stock_spin_acceleration;
  bool Load(const SettingsDatabase &, std::string &);
  void SetSpinScale(float);
  PhysicsAirReckoningFields Fields(const PhysicalRidingOutputs &) const;
  bool Update(PhysicalRidingOutputs &, const ProcessedPhysicsInput &,
              float physical_body_spin, Vec4 landing_normal, float normal_blend,
              float target_spin, float flip_request,
              PhysicsAirReckoningFields &, std::string &);
  void UpdatePlant(PhysicalRidingOutputs &, const ProcessedPhysicsInput &,
                   Vec4 up, Vec4 heading) override;
};
} // namespace atelier::skate
