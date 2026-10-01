// SPDX-License-Identifier: Apache-2.0
// Appended to the immutable whole-Biped test adapter, before its main.
#include "LandingOnDeckRuntime.h"
namespace landing_host_detail
{
using biped_landing::VO;using biped_landing::TO;
float PhysicalStep(){const std::uint32_t word=0x3c888889;float value;std::memcpy(&value,&word,4);return value;}
// GENERATED_UPDATE_OBSERVER
void OwnerOut(BipedOutput& o,const LandingOnDeckRuntime& owner)
{
    const auto& s=owner.state;o.Word(s.output.has_value());if(s.output)UpdateOut(o,*s.output);o.Float(s.time_to_land);
    for(bool b:{s.dangerous,s.near_deck,s.turning,s.hippy})o.Word(b);o.Word(std::uint32_t(s.takeoff_frames));
    for(float f:{s.spin_rate,s.applied_spin,s.transition_angle,s.accumulated_spin})o.Float(f);o.Word(std::uint32_t(s.half_turns));o.Word(std::uint32_t(s.next_half_turns));o.Word(std::uint32_t(s.LandingHalfTurns()));o.Word(s.RequestsBoardFlip());
    const auto& c=owner.configuration;const auto& a=c.state;for(float f:{a.minimum_auto_angle,a.automatic_speed,a.input_speed,a.input_delta,a.automatic_delta,a.maximum_landing_speed,c.root.root_y_offset,c.root.capsule_radius,c.root.capsule_length})o.Float(f);
}
void PacketOut(BipedOutput& o,const PhysicsPosePacket& p)
{
    o.Word(p.bone_count);o.Word(std::uint32_t(p.hierarchy.size()));for(const auto& m:p.hierarchy)o.Matrix(m);o.Word(std::uint32_t(p.local.size()));for(const auto& m:p.local)o.Matrix(m);
    o.Float(p.timestep);for(auto v:p.foot_surface_ids)o.Word(v);o.Word(p.flags);for(bool b:{p.board_flipped,p.mirrored,p.riding_switch,p.riding_fakie,p.weight_forwards,p.regular_stance})o.Word(b);o.Word(std::uint32_t(p.air_dismount_revert_frames));
}
void Snapshot(BipedOutput& o,const LandingOnDeckRuntime& owner,const PhysicsPosePacket& pose,const SkeletonWobble& wobble)
{
    o.Word(3);Block(o,[&]{OwnerOut(o,owner);});Block(o,[&]{PacketOut(o,pose);});Block(o,[&]{o.Word(wobble.active);o.Word(wobble.landing);o.Float(wobble.time);o.Float(wobble.amplitude);o.Float(wobble.direction);o.Word(wobble.SelectedLandingCurves());});
}
bool Pose(BipedInput& i,const AnimationPoseEvaluator& evaluator,PhysicsPosePacket& pose,BipedRuntimeOwners v,std::string& error)
{
    const auto kind=i.Word();pose.hierarchy.clear();pose.local.clear();
    if(kind!=4)
    {
        static const char* names[]={"RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"};PoseCommand cmd;cmd.kind=PoseCommand::Kind::Pose;cmd.name=names[kind];std::vector<Sqt> local;
        if(!evaluator.Evaluate({cmd},local,error)||!evaluator.Hierarchy(local,pose.hierarchy,error))return false;
        for(const auto& sqt:local)pose.local.push_back(SqtToMatrix(sqt));
    }
    const auto& x=v.processed;const auto deck=v.physical.DeckFrame();LandingInput input{0,x.flags_2468,x.flags_2472,x.flags_2476,0,v.physical.skeleton.record.centre_of_mass_velocity[1],v.physical.skeleton.record.centre_of_mass[1]-deck[3][1],0};
    return v.animated.ProcessPose(v.SkeletonOwners().AnimationOwners(),pose.hierarchy,input,x.timestep_2604,v.processed.flags_2468,v.processed.flags_2472,std::nullopt,error);
}
}
