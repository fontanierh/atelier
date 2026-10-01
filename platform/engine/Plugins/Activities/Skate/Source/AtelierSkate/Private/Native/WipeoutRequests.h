// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
struct WipeoutRequestInput
{
    std::uint32_t flags_2468,flags_2476,flags_2480,flags_2484;
    float animation_up_y;
    std::uint32_t category;
};
struct WipeoutRequests
{
    std::array<bool,34> reasons{};
    std::array<float,34> values{};
    std::uint32_t count=0;
    float cooldown=0;
    std::int32_t contact_frames=0;
    float balance=0;
    std::uint32_t mode=0;
    void InitializePlayer();
    void Teleport();
    void EnterGround();
    void Request(std::size_t,float);
    void ClearAfterSelection();
    void ResetSystems();
    bool RequestsRunout(const WipeoutRequestInput&) const;
    bool RequestsWipeout(const WipeoutRequestInput&) const;
};
}
