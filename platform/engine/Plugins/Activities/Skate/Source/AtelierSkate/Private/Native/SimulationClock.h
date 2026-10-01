// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CameraEffects.h"
#include <string>
#include <vector>
namespace atelier::skate {
// One host cadence owner, distinct from the physical integration timestep.
// The coordinator dispatches camera requests at the next frame's start and
// calls FinishTick at the original post-camera boundary.
class SimulationClock {
public:
  bool Apply(camera::SimulationRateRequest,std::string& error);
  bool ApplyRequests(const std::vector<camera::SimulationRateRequest>&,
                     std::string& error);
  void FinishTick();
  std::uint32_t TicksUntilReset() const {return ticks_until_reset_;}
  std::uint64_t PeriodNanoseconds() const {return timer_period_nanoseconds_;}
private:
  std::uint32_t ticks_until_reset_=0;
  std::uint64_t timer_period_nanoseconds_=16666600;
};
} // namespace atelier::skate
