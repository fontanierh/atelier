// SPDX-License-Identifier: Apache-2.0
#include "AirTrajectoryScoring.h"
#include "AirTrajectoryLaunch.h"
#include "AirTrajectorySelectorMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace M=air_trajectory_detail;
namespace
{
bool WallScore(AirTrajectoryPrediction& p,bool reject_grind,const AirTrajectorySelectorSettings& s,
    float& highest,AirTrajectorySelectionServices& services,float& output,std::string& error)
{
    const auto normal=p.result.contact_normal;
    if (!(std::fabs(normal[1])<0.5f)) {output=0;return true;}
    const auto start=M::Madd(normal,s.wall_ride_test_distance,p.result.contact_position);
    const auto end=M::Add(start,{0,-10,0,0});std::optional<AirTrajectorySurfaceHit> hit;
    if (!services.Line(start,end,0,hit,error)) return false;
    if (!hit||!(Dot3(hit->normal,normal)<s.wall_ride_normal_dot_limit)) {output=0;return true;}
    const float height=std::fabs(hit->position[1]-start[1]);
    if (reject_grind) {output=height*s.wall_ride_height_score-1000;return true;}
    const auto position=p.CollisionPosition();auto delta=M::Sub(p.request.trajectory.position,position);
    float slope=delta[1];delta[1]=0;const float horizontal=M::Length(delta);
    if (horizontal>M::Bits(0x3c23d70a)) slope*=RefinedReciprocal(horizontal,2);
    if (slope>s.wall_ride_angle_allow_landing) {output=height*s.wall_ride_height_score-1000;return true;}
    if (height<s.wall_ride_minimum_height) {output=height-1000;return true;}
    const float boost=s.wall_ride_boost.Evaluate(height);if (position[1]>highest) highest=position[1];
    AdjustAirTrajectoryVelocity(p.request.trajectory,p.result.contact_frame,{0,boost,0,0},s.maximum_trajectory_adjust);
    output=height*s.wall_ride_height_score;return true;
}
}
bool ScoreAirTrajectoryCandidates(AirTrajectoryCandidate* candidates,std::size_t count,
    std::uint16_t pass,bool adjusted_on_vert,AirSelectorInput input,const AirTrajectorySelectorSettings& s,
    AirTrajectorySelectionServices& services,bool& all_miss,std::string& error)
{
    bool missed=true;float highest_wall=-1000000;
    for (std::size_t index=0;index<count;++index)
    {
        auto& c=candidates[index];c.score=0;c.wall_score=0;c.wall_ride=false;c.grind.reset();
        if (!(c.prediction.result.contact_time>=0)) continue;
        missed=false;if (c.prediction.result.contact_frame<s.minimum_trajectory_frames) continue;
        const bool middle=index==0&&pass==1;
        const float middle_bonus=middle&&!adjusted_on_vert?s.score_middle_bonus:0;
        c.collision_position=c.prediction.CollisionPosition();
        c.normal=c.prediction.result.landing_normal;c.prediction.result.contact_normal=c.normal;
        c.collision_velocity=c.prediction.CollisionVelocity();
        const float force_dot=Dot3(c.normal,c.collision_velocity);
        const float sideways=M::Length(M::Cross(c.normal,M::Normalize(c.collision_velocity)));
        const float scalar=s.landing_force_scalar.Evaluate(std::fabs(force_dot));
        const float force_score=(force_dot*s.score_landing_force)*scalar;
        const float direction_score=(sideways*s.score_landing_direction)*scalar;
        AirTrajectoryGrindEvaluation evaluation{};
        const bool acquire=middle&&!((input.flags_2472&0x20000000)!=0&&(input.offboard_flags_1776&0x04000000)!=0&&(input.offboard_flags_1776&0x08000000)==0);
        if (!services.EvaluateGrind(c.prediction,acquire,evaluation,error)) return false;
        c.grind=evaluation.target;
        float grind_score=0;
        if ((input.flags_2476&0x02000000)!=0) grind_score=0;
        else if (evaluation.score!=0) grind_score=evaluation.score;
        else if (input.grind_lock_distance>0.5f||!middle) grind_score=s.grind_penalty_vs_distance.Evaluate(evaluation.PenaltyInput());
        if (grind_score<=0)
        {
            float wall_score=0;
            if (!WallScore(c.prediction,grind_score<0,s,highest_wall,services,wall_score,error)) return false;
            c.wall_score=wall_score;c.wall_ride=c.wall_score>0;
            if (c.wall_score<0) c.prediction.result.contact_normal=M::Up;
        }
        float surface_score=0;
        if (grind_score<=1)
        {
            switch ((c.prediction.result.surface>>7)&31)
            {
                case 6:surface_score=s.surface_unrideable_score;c.prediction.result.contact_normal=input.reference_up;break;
                case 7:surface_score=s.surface_dont_align_score;c.prediction.result.contact_normal=input.reference_up;break;
                case 8:surface_score=s.surface_dont_align_score;break;
                default:break;
            }
        }
        c.normal=c.prediction.result.contact_normal;float transition=0;
        if (adjusted_on_vert)
        {
            if (input.directional_input<0.5f&&grind_score>0)
            {c.grind.reset();grind_score=s.grind_penalty_vs_distance.Evaluate(0);}
            const float sign=input.directional_input>=0.5f?1.0f:-1.0f;auto heading=input.heading_direction;heading[1]=0;
            const float v=c.prediction.request.trajectory.velocity[1],g=c.prediction.request.trajectory.acceleration[1];
            const float apex=v<0||g>=0?0:v*RefinedReciprocal(-g,2);
            const float since_apex=std::fabs(c.prediction.result.contact_time-apex);
            const float penalty=since_apex>=s.minimum_time_after_apex?0:-500;
            const float coefficient=((1-std::fabs(input.ground_normal[1]))*sign)*s.score_transition;
            transition=Dot3(c.normal,M::Normalize(heading))*coefficient+penalty;
        }
        c.score=s.landing_time_bonus.Evaluate(c.prediction.result.contact_time)
            +(((((direction_score+1)+force_score)+middle_bonus)+grind_score)+transition);
        c.score+=surface_score;
    }
    // Apply wall bonuses only after every candidate has updated the highest Y.
    for (std::size_t index=0;index<count;++index)
    {
        auto& c=candidates[index];
        if (c.prediction.result.contact_time>=0&&c.prediction.result.contact_frame>=s.minimum_trajectory_frames)
        {
            if (c.wall_score==0&&c.prediction.CollisionPosition()[1]>highest_wall) c.wall_score=2000;
            c.score+=c.wall_score;
        }
    }
    all_miss=missed;error.clear();return true;
}
}
