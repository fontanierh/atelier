// SPDX-License-Identifier: Apache-2.0
#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::offboard_air_math
{
bool Prepare(OffboardAirLaunchPacket p,Vec4 gravity,OffboardAirQuerySettings s,std::vector<OffboardAirCandidate>& output,Vec4& out_offset,Vec4& out_correction,std::string& error)
{
    if(p.kind_112>std::numeric_limits<std::uint32_t>::max()-p.kind_108){error="BipedAir candidate count overflow";return false;}
    const auto count=std::size_t(p.kind_108+p.kind_112);
    if(p.kind_108==0||count>16||!std::isfinite(s.height)||!std::isfinite(s.sphere_radius)||s.sphere_radius<=0){error="Invalid authored BipedAir selector settings";return false;}
    for(const auto value:{p.scalar_96,p.scalar_100,p.scalar_104})if(!std::isfinite(value)){error="Nonfinite BipedAir launch packet";return false;}
    for(const auto& v:{p.velocity_0,p.secondary_velocity_16,p.position_32,p.up_48,p.forward_64,p.board_position_80,gravity})for(const auto x:v)if(!std::isfinite(x)){error="Nonfinite BipedAir launch packet";return false;}
    const auto initial=Mul(Up,-(s.height-s.sphere_radius));Vec4 correction{0,.1f,0,0};
    if(p.has_board_position_116)correction=Add(correction,Sub(p.board_position_80,Add(p.position_32,initial)));
    const auto offset=Add(initial,correction),base=Sub(p.velocity_0,Mul(correction,Reciprocal(1)));
    std::vector<Vec4> velocities(count,base);
    if(count>1)
    {
        const auto speed=Length(p.velocity_0);Vec4 axis{},right{};
        if(speed>=.001f){axis=Mul(p.velocity_0,Reciprocal(speed));right=Cross(Up,axis);if(Length(right)<.1f)right=Cross(axis,p.forward_64);right=Mul(right,Reciprocal(Length(right)));}
        else{axis=Up;right=Mul(p.forward_64,-1);}
        const auto vertical=Cross(axis,right);const std::array<float,3> tangents{std::tan(p.scalar_96),std::tan(p.scalar_100),std::tan(p.scalar_104)};
        const auto base_speed=Length(base);auto minimum=Length(Flat(p.velocity_0));
        for(std::size_t n=1;n<p.kind_108;++n)
        {
            const auto angle=(1-(float(n)/float(p.kind_108-1))*2)*Bits(0x40490fdb),sin=Sin(angle),cos=Cos(angle),cone=cos<=0?tangents[1]:tangents[2];
            const auto v=Madd(vertical,cos*cone,Madd(right,sin*tangents[0],base));velocities[n]=Mul(v,base_speed*Reciprocal(Length(v)));
            minimum=VectorMin(minimum,Length(Flat(velocities[n])));
        }
        if(p.kind_112>0)
        {
            const auto secondary=Flat(p.secondary_velocity_16);const auto n=Length(secondary);
            const auto direction=n>.01f?Mul(secondary,Reciprocal(n)):UnitOr(p.forward_64,{});
            const auto increment=VectorMin(VectorMax(minimum,1),4)/float(p.kind_112+1);float secondary_speed=0;
            const auto q=Bits(0x41a95811),vertical_speed=q*Inverse(q);
            for(std::size_t n2=p.kind_108;n2<count;++n2){secondary_speed+=increment;velocities[n2]=Madd(direction,secondary_speed,{0,vertical_speed,0,0});}
        }
    }
    std::vector<OffboardAirCandidate> candidates;candidates.reserve(count);
    for(const auto& velocity:velocities)
    {
        AirTrajectory trajectory{Add(p.position_32,offset),velocity,gravity,2};Shift(trajectory,float(s.start_index)*Step());
        if(!ValidateOffboardAirRequest(OffboardAirRequest(trajectory,s.sphere_radius),error))return false;
        OffboardAirCandidate candidate;candidate.trajectory=trajectory;candidate.start_frame_112=s.start_index;candidates.push_back(candidate);
    }
    output=std::move(candidates);out_offset=offset;out_correction=initial;error.clear();return true;
}
}
