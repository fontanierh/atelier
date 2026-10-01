// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace atelier::skate {
enum class PhysicalStateId : std::uint32_t {
  PhysicsGround = 100,
  SlideGround = 101,
  RevertGround = 102,
  GroundAnimation = 103,
  Skitching = 104,
  FollowPath = 105,
  PhysicsAir = 200,
  KnownAir = 201,
  PhysicsAirSecondary = 202,
  WipeoutGround = 300,
  GrindBoardslide = 400,
  GrindFiftyFifty = 401,
  GrindTipslide = 402,
  GrindFiveO = 403,
  GrindBackslash = 404,
  GrindDarkslide = 405,
  BipedGround = 500,
  BipedAir = 501,
  OffBoardPushing = 502,
  LandingOnDeck = 503,
  HandPlant = 600,
  FootPlant = 601,
  Boneless = 602,
  Sleeping = 700,
  Nonspecific = 701,
  Teleporting = 702
};
inline constexpr std::array<PhysicalStateId, 26> PhysicalStates{
    PhysicalStateId::PhysicsGround,
    PhysicalStateId::SlideGround,
    PhysicalStateId::RevertGround,
    PhysicalStateId::GroundAnimation,
    PhysicalStateId::Skitching,
    PhysicalStateId::FollowPath,
    PhysicalStateId::PhysicsAir,
    PhysicalStateId::KnownAir,
    PhysicalStateId::PhysicsAirSecondary,
    PhysicalStateId::WipeoutGround,
    PhysicalStateId::GrindBoardslide,
    PhysicalStateId::GrindFiftyFifty,
    PhysicalStateId::GrindTipslide,
    PhysicalStateId::GrindFiveO,
    PhysicalStateId::GrindBackslash,
    PhysicalStateId::GrindDarkslide,
    PhysicalStateId::BipedGround,
    PhysicalStateId::BipedAir,
    PhysicalStateId::OffBoardPushing,
    PhysicalStateId::LandingOnDeck,
    PhysicalStateId::HandPlant,
    PhysicalStateId::FootPlant,
    PhysicalStateId::Boneless,
    PhysicalStateId::Sleeping,
    PhysicalStateId::Nonspecific,
    PhysicalStateId::Teleporting};
std::optional<PhysicalStateId> ParsePhysicalStateId(std::uint32_t);
std::string_view PhysicalStateName(PhysicalStateId);
std::uint32_t PhysicalStateOwnerOffset(PhysicalStateId);
inline std::uint32_t PhysicalStateCategory(PhysicalStateId state) {
  return (std::uint32_t(state) / 100) * 100;
}
inline bool IsGrindState(PhysicalStateId state) {
  return std::uint32_t(state) >= 400 && std::uint32_t(state) <= 405;
}
enum class PhysicsBody { Board, Rider };
struct PhysicsSetVelocity {
  PhysicsBody body;
  Vec3 linear, angular;
};
struct PhysicsApplyImpulse {
  PhysicsBody body;
  Vec3 impulse, point;
};
struct PhysicsRequestState {
  PhysicalStateId state;
};
struct PhysicsSetContactMode {
  PhysicsBody body;
  bool enabled;
};
using PhysicsCommand = std::variant<PhysicsSetVelocity, PhysicsApplyImpulse,
                                    PhysicsRequestState, PhysicsSetContactMode>;
struct PhysicsStateChanged {
  PhysicalStateId from, to;
};
struct PhysicsLanding {};
struct PhysicsWipeout {};
struct PhysicsContact {
  PhysicsBody body;
};
using PhysicsEvent = std::variant<PhysicsStateChanged, PhysicsLanding,
                                  PhysicsWipeout, PhysicsContact>;
class PhysicsCommandBuffer {
public:
  explicit PhysicsCommandBuffer(std::uint64_t tick) : tick_(tick) {}
  std::uint64_t Tick() const { return tick_; }
  const std::vector<PhysicsCommand> &Commands() const { return commands_; }
  bool IsEmpty() const { return commands_.empty(); }
  bool Push(std::uint64_t, PhysicsCommand, std::string &error);
  bool Clear(std::uint64_t, std::string &error);

private:
  std::uint64_t tick_;
  std::vector<PhysicsCommand> commands_;
};
class PhysicsEventBuffer {
public:
  explicit PhysicsEventBuffer(std::uint64_t tick) : tick_(tick) {}
  std::uint64_t Tick() const { return tick_; }
  const std::vector<PhysicsEvent> &Events() const { return events_; }
  bool Emit(std::uint64_t, PhysicsEvent, std::string &error);

private:
  std::uint64_t tick_;
  std::vector<PhysicsEvent> events_;
};
struct PhysicalOutputSnapshot {
  std::uint64_t tick;
  PhysicalStateId state;
  Vec3 board_position, board_linear_velocity, rider_root_position,
      rider_linear_velocity;
  Vec3 ground_normal;
  std::uint32_t contact_count;
  Vec3 predicted_position;
  bool grounded, wiping_out, landed;
  std::vector<PhysicsEvent> events;
};
// Actual source host exchange, owned once by the global physical coordinator.
class SimulationExchange {
public:
  explicit SimulationExchange(std::uint64_t tick)
      : commands_(tick), events_(tick) {}
  bool EmitEvent(std::uint64_t tick, PhysicsEvent event, std::string &error) {
    return events_.Emit(tick, std::move(event), error);
  }
  void PublishOutput(PhysicalOutputSnapshot output) {
    physical_output_ = std::move(output);
  }
  const PhysicalOutputSnapshot *Output() const {
    return physical_output_ ? &*physical_output_ : nullptr;
  }
  const std::vector<PhysicsEvent> &Events() const { return events_.Events(); }
  const PhysicsCommandBuffer &Commands() const { return commands_; }
  bool RequestState(PhysicalStateId, std::string &error);

private:
  PhysicsCommandBuffer commands_;
  PhysicsEventBuffer events_;
  std::optional<PhysicalOutputSnapshot> physical_output_;
};
} // namespace atelier::skate
