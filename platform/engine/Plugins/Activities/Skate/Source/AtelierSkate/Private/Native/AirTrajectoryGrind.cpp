// SPDX-License-Identifier: Apache-2.0
#include "AirTrajectoryGrind.h"
#include "AirTrajectoryLaunch.h"
#include "AirTrajectorySelectorMath.h"
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace M=air_trajectory_detail;
Vec4 AirTrajectoryPrediction::CollisionPosition() const {return AirTrajectoryPositionAt(request.trajectory,result.contact_time);}
Vec4 AirTrajectoryPrediction::CollisionVelocity() const {return AirTrajectoryVelocityAt(request.trajectory,static_cast<float>(result.contact_frame)*M::Step());}
GrindAirTarget AirTrajectoryGrindTarget::AirTarget() const {return {edge.start,edge.end,edge.owner,primitive_flags,orientation};}
float AirTrajectoryGrindEvaluation::PenaltyInput() const
{
    if (effective_lock_distance)
    {
        const float denominator=*effective_lock_distance+M::Bits(0x3e19999a);
        if (denominator<penalty_domain) return (penalty_domain/denominator)*distance;
    }
    return distance;
}
std::vector<std::size_t> AirTrajectoryBoxFilter(const std::vector<std::size_t>& indices,
    const std::vector<PlayerGrindPrimitive>& primitives,Vec4 takeoff)
{
    std::vector<Vec4> directions;directions.reserve(indices.size());
    for (const auto index:indices)
    {
        // Rust indexing panics outside the provider contract; never permit UB.
        if (index>=primitives.size()) std::abort();
        const auto d=M::Sub(primitives[index].end,primitives[index].start);
        directions.push_back(M::Scale(d,InverseLengthSquared(Dot3(d,d),2)));
    }
    std::vector<std::size_t> accepted;accepted.reserve(indices.size());
    for (std::size_t i=0;i<indices.size();++i)
    {
        const auto a=primitives[indices[i]];bool keep=true;
        for (std::size_t j=0;j<indices.size();++j)
        {
            if (i==j) continue;
            const auto crossed=M::Cross(directions[i],directions[j]);
            if (!(Dot3(crossed,crossed)<M::Bits(0x38d1b717))) continue;
            const auto b=primitives[indices[j]];const auto delta=M::Sub(b.start,a.start);
            const auto perpendicular=M::Sub(delta,M::Scale(directions[j],Dot3(directions[j],delta)));
            const float distance=Dot3(perpendicular,perpendicular);
            if (!(distance>M::Bits(0x38d1b717)&&distance<M::Bits(0x3c23d70b))) continue;
            const auto middle=M::Scale(M::Add(a.start,a.end),0.5f),from=M::Sub(b.start,middle);
            if (!(Dot3(from,M::Sub(b.end,middle))<0)) continue;
            const auto up=M::Normalize(M::Cross(M::Cross(directions[i],M::Up),directions[i]));
            const float height=Dot3(delta,up);
            const auto alternative=M::Add(middle,M::Sub(from,M::Scale(directions[j],Dot3(directions[j],from))));
            const auto first=M::Sub(middle,takeoff),second=M::Sub(alternative,takeoff);
            if ((height>-0.02f&&Dot3(first,first)>Dot3(second,second))||height>0.02f) keep=false;
        }
        if (keep) accepted.push_back(indices[i]);
    }
    return accepted;
}
std::optional<float> AirTrajectoryDescendingPlaneTime(AirTrajectory t,Vec4 point,Vec4 normal)
{
    const float c=Dot3(normal,t.position)-Dot3(point,normal),b=Dot3(normal,t.velocity);
    const float a=Dot3(normal,M::Scale(t.acceleration,RefinedReciprocal(2,2)));
    const float discriminant=b*b-(4*a)*c;if (discriminant<0) return std::nullopt;
    const float inverse=RefinedReciprocal(2*a,2);
    if (discriminant>0)
    {
        const float root=discriminant*InverseLengthSquared(discriminant,2);
        return VectorMax(inverse*(-b+root),inverse*(-b-root));
    }
    const float time=inverse*-b;return time>0?std::optional<float>{time}:std::nullopt;
}
namespace
{
float FoldedApproachAngle(Vec4 a,Vec4 b,Vec4 normal)
{
    float angle=M::AngleBetween(a,b);const float aa=Dot3(a,a),bb=Dot3(b,b);
    if (aa>M::Bits(0x38d1b717)&&bb>M::Bits(0x38d1b717))
    {
        const auto unit_a=M::Scale(a,InverseLengthSquared(aa,1)),unit_b=M::Scale(b,InverseLengthSquared(bb,1));
        if (Dot3(M::Cross(unit_a,unit_b),normal)<0) angle=M::Bits(0x40c90fdb)-angle;
    }
    const float turns=angle*M::Bits(0x3e22f983),fraction=turns-std::floor(turns);
    const float wrapped=(fraction-(fraction>0.5f?1.0f:0.0f))*M::Bits(0x40c90fdb);
    const float sign=wrapped>0?1.0f:-1.0f,magnitude=wrapped*sign;
    const float folded=magnitude>M::Bits(0x3fc90fdb)?magnitude-M::Bits(0x40490fdb):magnitude;
    return std::fabs(sign*folded);
}
Vec4 ClampGrindAngle(Vec4 target,Vec4 reference,float limit)
{
    const auto a=M::Normalize(target),b=M::Normalize(reference),axis=M::Cross(a,b);
    const float dot=Dot3(a,b);
    // f32::clamp keeps an unordered input rather than f32::min/max's peer.
    const float angle=Acos(dot<-1?-1:dot>1?1:dot);
    const float turns=std::floor(std::fma(angle,M::Bits(0x3e22f983),0.5f));
    const float wrapped=std::fma(-turns,M::Bits(0x40c90fdb),angle);
    if (std::fabs(wrapped)<limit||M::Bits(0x37800000)>Dot3(axis,axis)) return target;
    const auto unit=M::Normalize(axis);const auto trigonometry=SinCos(-limit*0.5f);
    const auto q=M::Scale(unit,trigonometry.first);
    return M::Scale(M::Madd(M::Cross(q,M::Madd(reference,trigonometry.second,M::Cross(q,reference))),2,reference),M::Length(target));
}
}
std::optional<AirTrajectoryGrindCandidate> ConsiderAirTrajectoryGrindPrimitive(
    AirTrajectoryPrediction prediction,PlayerGrindPrimitive edge,std::size_t primitive,float padding)
{
    auto delta=M::Sub(edge.end,edge.start);const auto unscaled=M::Cross(delta,M::Cross(M::Up,delta));
    const auto normal=M::Scale(unscaled,InverseLengthSquared(Dot3(unscaled,unscaled),2));
    const float rail_length=M::Length(delta);if (rail_length>1) delta=M::Scale(delta,RefinedReciprocal(rail_length,2));
    const auto offset=M::Madd(normal,prediction.request.radius,M::Scale(normal,padding));
    const auto time=AirTrajectoryDescendingPlaneTime(prediction.request.trajectory,M::Add(edge.start,offset),normal);
    if (!time) return std::nullopt;
    const auto trajectory_point=M::Sub(AirTrajectoryPositionAt(prediction.request.trajectory,*time),offset);
    const auto direction=M::Normalize(delta),difference=M::Sub(trajectory_point,edge.start);
    const float distance=M::Length(M::Cross(difference,direction));
    const auto point=M::Madd(direction,Dot3(direction,difference),edge.start),extension=M::Scale(delta,0.1f);
    if (!(Dot3(M::Sub(point,M::Sub(edge.start,extension)),M::Sub(point,M::Add(edge.end,extension)))<0)) return std::nullopt;
    const auto velocity=prediction.request.trajectory.velocity;
    const auto approach=M::Normalize(M::Sub(velocity,M::Scale(normal,Dot3(normal,velocity))));
    auto horizontal=M::Sub(point,prediction.request.trajectory.position);horizontal[1]=0;
    return AirTrajectoryGrindCandidate{point,trajectory_point,direction,approach,distance,*time,
        FoldedApproachAngle(horizontal,direction,normal),M::SaturatedInteger(*time*M::Bits(0x426fffff)),primitive};
}
std::optional<AirTrajectoryGrindCandidate> TakeBestAirTrajectoryGrind(
    std::vector<AirTrajectoryGrindCandidate>& candidates,float difficulty_distance,const PointGraph<8>& height_penalty)
{
    std::optional<std::size_t> chosen;float fallback=1000,best_angle=M::Bits(0x40490fdb),height=-10000;
    for (std::size_t i=0;i<candidates.size();++i)
    {
        const auto& candidate=candidates[i];
        if (candidate.distance<difficulty_distance)
        {
            const float benefit=best_angle-candidate.angle;
            if (benefit>height_penalty.Evaluate(candidate.point[1]-height))
            {height=candidate.point[1];fallback=-1;best_angle=candidate.angle;chosen=i;}
        }
        else if (candidate.distance<fallback) {fallback=candidate.distance;chosen=i;}
    }
    if (!chosen) return std::nullopt;
    const auto result=candidates[*chosen];candidates.erase(candidates.begin()+static_cast<std::ptrdiff_t>(*chosen));return result;
}
Vec4 AirTrajectoryGrindLandingNormal(Vec4 direction,Vec4 velocity,Vec4 support,float velocity_scalar,float maximum_angle_degrees)
{
    const auto across=M::Sub(velocity,M::Scale(direction,Dot3(direction,velocity)));
    const auto target=M::Madd(across,-velocity_scalar,M::Up);
    const auto limited=ClampGrindAngle(target,support,maximum_angle_degrees*M::Bits(0x3c8efa35));
    const float component=Dot3(limited,M::Normalize(direction));
    return M::Normalize(component>0?M::Sub(limited,M::Scale(direction,component)):limited);
}
void ApplyAirTrajectoryGrindTarget(AirTrajectoryPrediction& prediction,AirTrajectoryGrindCandidate candidate,
    Vec4 correction,Vec4 support_normal,Vec4 reference_velocity,float maximum_adjust,float landing_velocity_scalar,float landing_max_angle)
{
    AdjustAirTrajectoryVelocity(prediction.request.trajectory,candidate.frame,correction,maximum_adjust);
    prediction.result.contact_frame=candidate.frame;prediction.result.contact_time=static_cast<float>(candidate.frame)*M::Step();
    prediction.result.contact_normal=AirTrajectoryGrindLandingNormal(candidate.direction,reference_velocity,support_normal,landing_velocity_scalar,landing_max_angle);
}
std::optional<Vec4> AdmitAirTrajectoryGrindDisplacement(AirTrajectoryPrediction prediction,
    AirTrajectoryGrindCandidate candidate,PlayerGrindPrimitive edge,Vec4 reference_velocity,Vec4 processed_592,
    AirTrajectoryGrindSurfaceEvidence surface,const AirTrajectoryGrindAssistLimits& limits,std::optional<float>& effective_lock_distance)
{
    const auto natural=AirTrajectoryPositionAt(prediction.request.trajectory,prediction.result.contact_time);
    if (candidate.point[1]-natural[1]<M::Bits(0xbecccccd)||candidate.direction[1]>0.9f) return std::nullopt;
    const auto direction=M::Normalize(M::Sub(edge.end,edge.start));
    const auto perpendicular=M::Sub(reference_velocity,M::Scale(direction,Dot3(direction,reference_velocity)));
    if (std::fabs(perpendicular[1]*(1-std::fabs(direction[1])))>limits.max_downward_speed||surface.kind==3) return std::nullopt;
    auto horizontal=perpendicular;horizontal[1]=0;
    const float max_speed=surface.kind==2?limits.max_speed_squared_ledge:limits.max_speed_squared_rail;
    if (Dot3(horizontal,horizontal)>max_speed) return std::nullopt;
    const auto delta=M::Sub(candidate.trajectory_point,candidate.point);float lock_distance=limits.lock_distance;
    if (surface.kind==2)
    {
        const bool incoming=Dot3(delta,surface.side)>0,body=Dot3(M::Sub(processed_592,edge.start),surface.side)>0;
        lock_distance*=limits.ledge_scalars[(incoming?0:2)+(body?0:1)];
    }
    lock_distance=VectorMax(lock_distance,0.1f);effective_lock_distance=lock_distance;
    if (candidate.distance>=lock_distance) return std::nullopt;
    const auto miss=M::Sub(candidate.trajectory_point,edge.start);
    auto correction=M::Scale(M::Sub(miss,M::Scale(candidate.direction,Dot3(candidate.direction,miss))),-1);
    const float distance=M::Length(correction);
    if (distance>=limits.lock_distance)
    {
        const float half_dimension=std::fma(limits.deck_dimensions[1],0.5f,limits.deck_dimensions[0]*0.5f);
        correction=M::Scale(correction,std::fma(-limits.tip_scalar,half_dimension,distance)/distance);
    }
    const auto original=prediction.request.trajectory.velocity,adjusted=M::Madd(correction,RefinedReciprocal(candidate.time,2),original);
    const float angle=Dot3(original,original)*Dot3(adjusted,adjusted)>M::Bits(0x38d1b717)?M::AngleBetween(original,adjusted):0;
    if (angle>limits.maximum_adjust_angle*M::Bits(0x3c8efa35)) return std::nullopt;
    return correction;
}
}
