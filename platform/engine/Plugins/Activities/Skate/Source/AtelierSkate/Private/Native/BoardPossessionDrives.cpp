// SPDX-License-Identifier: Apache-2.0
#include "BoardPossessionDrives.h"
#include "SkeletonDriveFrames.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
DriveBodyState Body(BodySnapshot b,std::size_t index)
{
    const auto& r=b.rates;return {index,b.state_flags,r.orientation,r.basis,r.position,r.linear_velocity,
        r.angular_velocity,r.force_acceleration,r.torque_acceleration,b.inertia.inverse_mass,PackWorldInverseInertia(r.world_inverse_inertia)};
}
DriveFrame Frame(const Mat4& v)
{
    Basis3 basis;for(unsigned i=0;i<3;++i)basis.columns[i]={v[i][0],v[i][1],v[i][2]};
    return {QuaternionFromBasis(basis),{v[3][0],v[3][1],v[3][2]}};
}
DriveParams Params(std::array<std::uint32_t,4> v)
{return {Scalar(v[0]),Scalar(v[1]),Scalar(v[2]),DriveType::Hard};}
}
void AppendBoardPossessionDrives(const BoardPossessionState& state,BodySnapshot deck,
    const std::array<BodySnapshot,2>& hands,std::size_t deck_reaction,
    std::array<std::size_t,2> hand_reactions,float dt,std::vector<DriveRows>& rows)
{
    for(unsigned i=0;i<2;++i)
    {
        if(((deck.state_flags|hands[i].state_flags)&4)==0)continue;const auto& drive=state.hands[i];
        rows.push_back(BuildDriveRows(Body(hands[i],hand_reactions[i]),Body(deck,deck_reaction),
            PrepareBoneDriveFrames({Frame(drive.child),Frame(drive.parent)}),
            {Params(drive.dynamics[0]),Params(drive.dynamics[1])},dt));
    }
}
}
