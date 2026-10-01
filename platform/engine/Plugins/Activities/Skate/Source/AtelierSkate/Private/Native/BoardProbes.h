// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardGround.h"
namespace atelier::skate
{
struct BoardProbeHit {Vec3 point,normal;std::uint32_t surface_tag;};
struct BoardProbeState
{
    Vec3 start{},point{},normal{};
    std::uint32_t surface_tag=0;
    bool hit=false;
    void Start(Vec3 position){start=position;hit=false;}
    void Publish(std::optional<BoardProbeHit>);
    void Disable(){*this=BoardProbeState{};}
};
inline constexpr float DeckProbeRadius=0.15f;
WheelLine DeckProbe(Vec3 position);
struct WallLineInput {std::uint32_t state;Vec3 contact_normal,skater_up,deck_position;float time;};
std::optional<WheelLine> WallProbe(WallLineInput);
}
