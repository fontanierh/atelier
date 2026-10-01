// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GestureInputPublication.h"
#include "InputIntentions.h"
#include "PlayerInputTypes.h"
#include "PhysicalSimulationSettings.h"
#include "CameraRuntime.h"
#include "AnimationPhaseInput.h"
namespace atelier::skate {
// Borrow the original action packet and override only this tick's sampled
// offboard left-stick axes. Camera/state changes must not rotate it again.
class PlayerSimulationActions final : public ActionMap {
  ActionMap& source_;
  std::optional<StickPoint> offboard_axes_;
public:
  PlayerSimulationActions(ActionMap& source,std::optional<StickPoint> axes)
    :source_(source),offboard_axes_(axes){}
  float Value(std::uint32_t action) override;
  std::uint8_t State(std::uint32_t action) override;
};
class PlayerControls {
  std::optional<StickPoint> offboard_axes_;
  std::optional<GestureInputPublication> gestures_;
public:
  DerivedControllerInput controller{std::array<std::uint32_t,26>{}};
  std::optional<Vec4> offboard_direction;
  std::vector<ControllerIntent> intents;
  IntentMap action_intents;
  std::uint64_t ticks=0;
  std::uint32_t actor_flags=0;
  bool bumper_state_502=false,bumper_state_104=false;
  PushPreferences preferences;
  PlayerControls();
  // The native packager supplies the same seven authored gesture sets. Failed
  // construction never exposes a partial controls or recognizer owner.
  static std::optional<PlayerControls> Load(const SettingsDatabase&,
    std::vector<GestureSet> bank,std::string& error);
  void Update(ActionMap&,float dt,float magnitude_threshold,
    std::uint32_t physical_capabilities);
  bool UpdateForPhysics(ActionMap&,const PhysicalPlayerInput&,
    const PhysicalSimulationSettings&,const camera::CameraRuntime&,
    std::string& error);
  PlayerSimulationActions SimulationActions(ActionMap& source) const
    {return {source,offboard_axes_};}
  bool PublishGestures(std::uint32_t difficulty,std::uint32_t physical_state,
    std::string& error);
  // Source sample() scheduling: action packet -> UpdateForPhysics -> gestures.
  bool Sample(const TickInput&,const PhysicalPlayerInput&,
    const PhysicalSimulationSettings&,const AnimationProfile&,
    const camera::CameraRuntime&,std::string& error);
  const std::optional<StickPoint>& SampledOffboardAxes() const
    {return offboard_axes_;}
  bool HasGestures() const{return gestures_.has_value();}
  std::optional<std::string_view> HeldPattern() const
    {return gestures_?gestures_->HeldPattern():std::nullopt;}
};
// Complete original controls.rs local camera arithmetic; its rsqrt seed uses
// std sqrt/reciprocal and two fused refinements, distinct from NativeMath.
StickPoint PlayerCameraRelativeAxes(StickPoint,const Basis3& camera);
} // namespace atelier::skate
