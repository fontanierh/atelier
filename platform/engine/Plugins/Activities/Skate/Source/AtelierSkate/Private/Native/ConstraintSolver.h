// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace atelier::skate
{
// Compiled coefficients retain every lane, including carried fourth components.
// Reaction indices replace guest pointers; validation happens before any writes.
template<std::size_t N> struct Constraint
{
    std::array<std::uint32_t,N> words{};
    std::size_t reaction_a = 0, reaction_b = 0;
};
using ContactConstraint = Constraint<64>;
using JointConstraint = Constraint<96>;
using DriveConstraint = Constraint<96>;
using PackedReaction = std::array<std::uint32_t,16>;

// Each iteration completes contact, joint, then drive passes over the same
// reaction workspace. Invalid/aliased indices return false without mutation.
bool SolveConstraints(std::vector<ContactConstraint>& contacts,
    std::vector<JointConstraint>& joints, std::vector<DriveConstraint>& drives,
    std::vector<PackedReaction>& reactions, std::uint32_t iterations);
}
