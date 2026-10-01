// SPDX-License-Identifier: Apache-2.0
#include "WipeoutPhysicalRuntime.h"
#include "WipeoutPhysicalMath.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
bool WipeoutPhysicalRuntime::UpdateSkeleton(WipeoutPhysicalOwners o,float start,float end,float controlled,float extra,bool skip_targets,float& residual,std::string& error)
{
    auto& p=o.physical;auto& roots=p.roots;auto& frames=p.board_frames;const auto& processed=o.input.processed;
    roots.initialize_heading=false;const auto inverse_hips=InverseSkeletonRigid(o.animated.animation_hips);auto predicted=p.skeleton.record.pose[23];
    predicted[3]=Madd(p.skeleton.record.velocities[23],Step(),p.skeleton.record.pose[23][3]);auto root=ComposeSkeletonAffine(predicted,inverse_hips);
    float weight=processed.state_timer_2664+Step();weight=-weight>=0?0:weight;weight=1.0f-weight>=0?weight:1;
    auto desired=frames.centre_of_mass;desired[1]+=Word(0xbf4ccccd);const auto com_velocity=FromWords(processed.vectors_544_560_592_608[3]);
    const auto next=Madd(com_velocity,Step(),root[3]);root[3]=Madd(desired,weight,Scale(next,1.0f-weight));roots.animation_to_world=root;roots.world_to_animation=InverseSkeletonRigid(root);
    const SkeletonTargetInput target{o.animated.animation_hips,o.animated.animation_board,roots.animation_to_world,roots.inverse_board,frames.skate_root,frames.com_frame,frames.lifted_com_frame,o.skeleton_input.teleporting};
    if(!skip_targets){p.animation_board_to_physics=p.skeleton_drives.targets.UpdateHookPositions(target);const auto positions=p.skeleton_drives.targets.UpdateExtraTargets(p.skeleton,target.com_frame,target.lifted_com_frame);
        p.extra_target_positions={positions.com,positions.lifted_com,positions.following_com};p.pose_errors.SetTargets(positions);}
    frames.skate_root=roots.animation_to_world;frames.UpdateComLift(roots.animation_to_world,frames.centre_of_mass,0);
    if(processed.state_timer_2664==0){
        if(!o.ik.Update(o.animated,{p.animation_record,p.roots,p.board_frames},o.globals,processed,o.animation_input.contacts.bone,p.board_frames.physical_board,p.skeleton.PartTransforms()[23][3],p.drive_frames,error))return false;
    }
    const WipeoutDriveWeights weights{start,end,controlled,(processed.flags_2484&0x20)?extra:0,(processed.flags_2484&0x10)?extra:0};
    if(!UpdateWipeoutDrives(p.skeleton_drives,p.drive_frames,drives,weights,residual,error))return false;o.animated.motion.next_trajectory=SkeletonIdentity;return true;
}
}
