// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "DriveBuild.h"
namespace atelier::skate
{
void SetChildAngularFrame(std::array<std::uint32_t,16>& frames,const std::array<std::uint32_t,12>& basis);
void SetParentAngularFrame(std::array<std::uint32_t,16>& frames,const std::array<std::uint32_t,12>& basis);
struct HookDriveState
{
    std::array<std::uint32_t,16> frames{};
    std::array<std::uint32_t,8> dynamics{};
    static HookDriveState Initial();
    void EnableAnimationSoft(std::uint8_t& animated);
    void EnableAngularSoft();
    void EnableAngularOnly(std::uint8_t& animated);
    void DisableAnimation(std::uint8_t& animated);
    void DisableLinear();
    void DisableAngular();
    DriveDynamics SolverDynamics() const;
};
}
