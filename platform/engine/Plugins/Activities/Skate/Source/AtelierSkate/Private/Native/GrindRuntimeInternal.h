// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GrindRuntime.h"
#include <cmath>
#include <cstring>
namespace atelier::skate::grind_detail
{
inline float Float(std::uint32_t bits){float out;std::memcpy(&out,&bits,4);return out;}
inline Vec4 FloatVector(RawVector a){Vec4 out;std::memcpy(out.data(),a.data(),16);return out;}
inline RawVector Raw(Vec4 a){RawVector out;std::memcpy(out.data(),a.data(),16);return out;}
inline Vec3 Xyz(Vec4 a){return {a[0],a[1],a[2]};}
inline Vec4 Lanes(Vec3 a){return {a.x,a.y,a.z,0};}
inline Vec4 Lanes(std::array<float,3> a){return {a[0],a[1],a[2],0};}
inline Vec4 Sub(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]-=b[i];return a;}
inline Vec4 Scale(Vec4 a,float b){for(float& v:a)v*=b;return a;}
inline Vec4 Cross(Vec4 a,Vec4 b){return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1]),0};}
inline std::int32_t Increment(std::int32_t a){std::uint32_t w;std::memcpy(&w,&a,4);++w;std::memcpy(&a,&w,4);return a;}
inline SkeletonInputCollision Collision(const PhysicalSimulationRuntime& p)
{return {p.collision_feedback.flags.compliant,p.collision_feedback.flags.has_impulse,p.collision_pose_error,p.skeleton_collision.partial_ragdoll,p.collision_feedback.drive_weight};}
inline std::optional<PlayerGrindFamily> Family(PhysicalStateId id)
{
    switch(id){case PhysicalStateId::GrindFiftyFifty:return PlayerGrindFamily::FiftyFifty;case PhysicalStateId::GrindBoardslide:return PlayerGrindFamily::Boardslide;
    case PhysicalStateId::GrindTipslide:return PlayerGrindFamily::Tipslide;case PhysicalStateId::GrindFiveO:return PlayerGrindFamily::FiveO;
    case PhysicalStateId::GrindBackslash:return PlayerGrindFamily::Backslash;case PhysicalStateId::GrindDarkslide:return PlayerGrindFamily::Darkslide;default:return std::nullopt;}
}
inline AffineTransform Transform(Mat4 a)
{
    AffineTransform out;for(std::size_t i=0;i<3;++i)out.basis.columns[i]={a[i][0],a[i][1],a[i][2]};out.translation=Xyz(a[3]);return out;
}
inline bool Animated(GrindRuntimeOwners o,Mat4& target,std::string& error)
{return UpdateAnimatedSkeletonAir(o.skeleton_input,o.skeleton_air,o.physical.riding.reckoning_frames.system,o.input.processed,o.SkeletonOwners(),o.globals,Collision(o.physical),false,target,error);}
inline bool Ground(GrindRuntimeOwners o,Mat4& target,std::string& error)
{return o.skeleton_input.UpdateGround(o.physical.riding.reckoning_frames.system,o.input.processed,o.SkeletonOwners(),o.globals,Collision(o.physical),target,error);}
inline bool Reckon(GrindRuntimeOwners o,const GrindReckoningSettings& s,Vec4 normal,Vec4 heading,float smoothing,std::string& error)
{return UpdateGrindReckoning(o.physical.riding.reckoning,o.physical.riding.reckoning_frames,o.physical.riding.body_spin,o.air_reckoning.state,s,normal,heading,smoothing,(o.input.processed.flags_2468&0x00100000)!=0,0,error);}
}
