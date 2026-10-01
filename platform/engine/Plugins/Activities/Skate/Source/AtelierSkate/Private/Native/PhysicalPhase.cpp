// SPDX-License-Identifier: Apache-2.0
#include "PhysicalPhase.h"
#include <algorithm>
namespace atelier::skate {
std::optional<PhysicalStateId> ParsePhysicalStateId(std::uint32_t value) {
  for (auto state : PhysicalStates)
    if (std::uint32_t(state) == value)
      return state;
  return std::nullopt;
}
std::string_view PhysicalStateName(PhysicalStateId value) {
  const std::array<std::string_view, 26> names{
      "PhysicsGround",   "SlideGround",     "RevertGround",
      "GroundAnimation", "Skitching",       "FollowPath",
      "PhysicsAir",      "KnownAir",        "PhysicsAirSecondary",
      "WipeoutGround",   "GrindBoardslide", "GrindFiftyFifty",
      "GrindTipslide",   "GrindFiveO",      "GrindBackslash",
      "GrindDarkslide",  "BipedGround",     "BipedAir",
      "OffBoardPushing", "LandingOnDeck",   "HandPlant",
      "FootPlant",       "Boneless",        "Sleeping",
      "Nonspecific",     "Teleporting"};
  for (std::size_t i = 0; i < PhysicalStates.size(); ++i)
    if (PhysicalStates[i] == value)
      return names[i];
  return {};
}
std::uint32_t PhysicalStateOwnerOffset(PhysicalStateId value) {
  const std::array<std::uint32_t, 26> offsets{
      1696, 1700, 1704, 1708, 1772, 1760, 1712, 1720, 1716,
      1748, 1728, 1732, 1736, 1740, 1744, 1724, 1764, 1768,
      1776, 1792, 1780, 1784, 1788, 1692, 1752, 1756};
  for (std::size_t i = 0; i < PhysicalStates.size(); ++i)
    if (PhysicalStates[i] == value)
      return offsets[i];
  return 0;
}
bool PhysicsCommandBuffer::Push(std::uint64_t tick, PhysicsCommand command,
                                std::string &error) {
  if (tick != tick_) {
    error = "Physics command belongs to tick " + std::to_string(tick) +
            ", buffer owns tick " + std::to_string(tick_);
    return false;
  }
  commands_.push_back(std::move(command));
  error.clear();
  return true;
}
bool PhysicsCommandBuffer::Clear(std::uint64_t tick, std::string &error) {
  if (tick != tick_) {
    error = "Cannot clear physics commands for tick " + std::to_string(tick) +
            "; buffer owns tick " + std::to_string(tick_);
    return false;
  }
  commands_.clear();
  error.clear();
  return true;
}
bool PhysicsEventBuffer::Emit(std::uint64_t tick, PhysicsEvent event,
                              std::string &error) {
  if (tick != tick_) {
    error = "Physics event belongs to tick " + std::to_string(tick) +
            ", buffer owns tick " + std::to_string(tick_);
    return false;
  }
  events_.push_back(std::move(event));
  error.clear();
  return true;
}
bool SimulationExchange::RequestState(PhysicalStateId state,
                                      std::string &error) {
  return commands_.Push(commands_.Tick(), PhysicsRequestState{state}, error);
}
} // namespace atelier::skate
