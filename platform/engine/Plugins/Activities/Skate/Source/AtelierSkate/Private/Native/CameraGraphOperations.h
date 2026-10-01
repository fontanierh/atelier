// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CameraManager.h"
#include "CompiledGraph.h"
#include "GraphConditions.h"
namespace atelier::skate::camera {
struct CameraGraphSubject {
  float time_since_player_input = 0;
  std::uint32_t wipeout_tweak = 0;
  bool onboard_air = false, preparing_to_jump = false, manual = false,
       offboard_air = false, running_out = false, footplant = false,
       handplant = false, hippy_jump = false, hippy_hurdle = false,
       boneless = false, moving_object = false, skitching = false,
       dropping_in = false;
  float slow_motion_air_duration = 0;
};
struct CameraGraphEnvironment {
  std::uint32_t camera_type = 0;
  bool on_road = false, ledge_left = false, ledge_right = false;
  std::vector<std::string> volumes;
};
enum class CameraBoolean : std::uint32_t {
  Observer,
  WipingOut,
  BrokenBone,
  Offboard,
  OffboardAir,
  OnboardAir,
  FixedInAir,
  Preparing,
  Manual,
  DroppingIn,
  MovingObject,
  Skitching,
  Footplant,
  Handplant,
  Boneless,
  HippyJump,
  HippyHurdle,
  Grinding,
  WasGrinding,
  OnGround,
  Reentry,
  Road,
  LedgeLeft,
  LedgeRight,
  WorldPainter,
  Threat,
  BadCollision
};
enum class CameraValue : std::uint32_t {
  Speed,
  SpeedY,
  Acceleration,
  AirTime,
  LandingHeight,
  MaxHeight,
  HeightRatio,
  FrontsideAngle,
  TransferAngle,
  LaunchIncline,
  LandingIncline,
  GrindIncline,
  Incline,
  AbsoluteIncline,
  CentredTime,
  TurningTime,
  TimeSinceInput
};
struct CameraCondition {
  enum class Kind { Type, Previous, Tweak, Volume, Boolean, Numeric };
  Kind kind = Kind::Type;
  std::uint32_t value = 0;
  std::vector<std::uint32_t> shot_hashes;
  std::string volume;
  CameraBoolean boolean = CameraBoolean::Observer;
  CameraValue numeric_value = CameraValue::Speed;
  NumericCondition numeric;
  bool Parse(const GraphAttributes &attributes, std::string &error);
  bool Evaluate(const CameraMan &manager, const ManagerSubject &subject,
                CameraGraphSubject physical,
                const CameraGraphEnvironment &world) const;
};
std::vector<std::string> ShotNames(const GraphAttributes &attributes);
struct CameraBehavior {
  enum class Kind { Choose, Print, SlowMotion };
  Kind kind = Kind::Choose;
  std::vector<std::string> names;
  float incoming = -1, outgoing = -1;
  std::string text;
};
struct CameraGraph {
  CompiledGraph program;
  graph::Controller controller{0};
  std::vector<CameraCondition> conditions;
  std::vector<CameraBehavior> behaviors;
  std::vector<std::optional<SlowMotionController>> slow_motion;
  SlowMotionSettings slow_motion_settings;
  // PrintText2D's ordered warning messages are retained for the host logger.
  std::vector<std::string> printed_messages;
  bool FromGraph(const Graph &source, SlowMotionSettings settings,
                 std::string &error);
  bool Update(float dt, CameraMan &manager, const ManagerSubject &subject,
              CameraGraphSubject physical, const CameraGraphEnvironment &world,
              const StockShots &database,
              std::vector<SimulationRateRequest> &rates, std::string &error);
};
} // namespace atelier::skate::camera
