#pragma once
#include "BoardAssembly.h"
#include "CollisionBody.h"

namespace atelier::skate
{
struct BoardContactReport
{
    BoardBodyId part;
    CollisionBody other;
    bool is_body_a;
    Vec3 normal,position,relative_linear_velocity;
    std::uint16_t other_surface;
    Vec3 normal_force_on_a,friction_force_on_a;
    std::array<Vec3,2> tangents;
};
void CollectBoardContactReports(std::vector<BoardContactReport>& output,const std::vector<ContactConstraint>& contacts,
    const std::array<BodySnapshot,BoardBodyCount>& bodies,float frequency);
}
