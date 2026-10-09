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
// One tick's sticks read at 120 Hz (GameplaySession::Step's readings), as the Xbox packet carries them: half a tick
// before the tick's end and at its end.
struct FineSticks {
  std::array<std::int16_t,2> half_left{},half_right{},left{},right{};
};
class PlayerControls {
  std::optional<StickPoint> offboard_axes_;
  std::optional<Basis3> offboard_basis_;
  std::optional<GestureInputPublication> gestures_;
  std::optional<FineSticks> fine_;
  // A packet's sticks as PublishGestures reads them from the controller words: conditioned, and the left stick
  // camera-relative off the board (UpdateForPhysics).
  std::array<StickPoint,2> GestureAxes(std::array<std::int16_t,2> left,std::array<std::int16_t,2> right) const;
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
  // The next tick's 120 Hz sticks, used only when the recogniser reads two samples per tick (FeelTuning::flick_120hz).
  // Without them the tick reads its packet once, for both samples' worth.
  void SetFineSticks(std::optional<FineSticks> sticks){fine_=sticks;}
  // Source sample() scheduling: action packet -> UpdateForPhysics -> gestures.
  bool Sample(const TickInput&,const PhysicalPlayerInput&,
    const PhysicalSimulationSettings&,const AnimationProfile&,
    const camera::CameraRuntime&,std::string& error);
  const std::optional<StickPoint>& SampledOffboardAxes() const
    {return offboard_axes_;}
  bool HasGestures() const{return gestures_.has_value();}
  // The gesture manager's last publication (its per-recognizer trace), for hosts.
  const GestureInputPublication* Gestures() const{return gestures_?&*gestures_:nullptr;}
  GestureInputPublication* MutableGestures(){return gestures_?&*gestures_:nullptr;}
  std::optional<std::string_view> HeldPattern() const
    {return gestures_?gestures_->HeldPattern():std::nullopt;}
};
// Complete original controls.rs local camera arithmetic; its rsqrt seed uses
// std sqrt/reciprocal and two fused refinements, distinct from NativeMath.
StickPoint PlayerCameraRelativeAxes(StickPoint,const Basis3& camera);
} // namespace atelier::skate
