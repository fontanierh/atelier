// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "HandplantSettings.h"
#include "PlayerGrindInputWorld.h"
namespace atelier::skate {
struct HandplantCandidate {
  Vec4 point;
  PlayerGrindPrimitive edge;
  std::int32_t side;
};
std::optional<HandplantCandidate>
SelectHandplantContact(const HandplantSettings &, Vec4 com, Vec4 velocity,
                       Vec4 normal, std::int32_t hint,
                       const std::vector<PlayerGrindPrimitive> &);
} // namespace atelier::skate
