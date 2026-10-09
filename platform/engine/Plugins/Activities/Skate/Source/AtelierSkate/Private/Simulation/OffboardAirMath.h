#pragma once
#include "OffboardAirSelector.h"
#include "OffboardVectorMath.h"
#include <limits>
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::offboard_air_math
{
inline void Shift(AirTrajectory& t,float time){const auto p=AirTrajectoryPositionAt(t,time);t.velocity=AirTrajectoryVelocityAt(t,time);t.position=p;}
inline void Adjust(AirTrajectory& t,std::int32_t frame,Vec4 delta,float maximum)
{if(frame<=0)return;const auto correction=Mul(delta,Reciprocal(float(frame)*Step()));const auto scalar=Dot(correction,correction)>maximum*maximum?maximum/Length(correction):1; t.velocity=Madd(correction,scalar,t.velocity);}
inline bool Valid(AirTrajectoryQueryResult q){return q.contact_time>=0;}
inline Vec4 SuggestedNormal(AirTrajectoryQueryResult q){return Valid(q)?q.landing_normal:Up;}
inline Vec4 Lanes(Vec3 v){return {v.x,v.y,v.z,0};}
inline Vec3 XYZ(Vec4 v){return {v[0],v[1],v[2]};}
std::pair<Vec4,Vec4> Jump(const BipedControllerState&,const PointGraph<8>&,OffboardAirLaunchSettings,const OffboardAirLaunchInput&,Vec4 forward);
bool Prepare(OffboardAirLaunchPacket,Vec4 gravity,OffboardAirQuerySettings,std::vector<OffboardAirCandidate>&,Vec4& offset,Vec4& correction,std::string&);
}
