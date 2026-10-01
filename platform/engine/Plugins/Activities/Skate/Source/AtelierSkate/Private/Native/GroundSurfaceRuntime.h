// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstdint>
#include <string>
namespace atelier::skate
{
class BoardRuntime;
struct PhysicalRidingOutputs;
// Original contact_feedback::choose_surface. Invalid histogram indices are
// source assertions; the exception-disabled boundary diagnoses them and retains
// output. Callers must propagate the failure before publishing any surface.
bool ChoosePlayerGroundSurface(std::array<std::uint32_t,4> surfaces,
    std::array<bool,4> contacts,bool forced_twelve,std::uint32_t& output,std::string& error);
bool ActivePlayerGroundSurface(const PhysicalRidingOutputs&,const BoardRuntime&,
    std::uint32_t& output,std::string& error);
}
