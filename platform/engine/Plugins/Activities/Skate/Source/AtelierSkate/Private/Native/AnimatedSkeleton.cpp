// SPDX-License-Identifier: Apache-2.0
#include "AnimatedSkeleton.h"
#include "SkeletonSettingReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
bool AnimationBoneEqual(std::string_view a,std::string_view b)
{
    if(a.size()!=b.size())return false;const auto lower=[](unsigned char c){return c>='A'&&c<='Z'?c+32:c;};for(unsigned i=0;i<a.size();++i)if(lower(a[i])!=lower(b[i]))return false;return true;
}
LandingSettings LoadLandingSettings(detail::SkeletonSettingReader& f)
{
    const auto scalar=[&](std::string_view n){return f.Scalar("physics_animation",n);};
    return {f.NegativeGraph<4>("physics_animation","LandingAdjustManualBlend"),f.NegativeGraph<4>("physics_animation","LandingAdjustGrindBlend"),f.NegativeGraph<4>("physics_animation","LandingAdjustCoffinBounceHeight"),
        scalar("LandingAdjustMinYPos"),scalar("LandingAdjustMaxVel"),scalar("LandingAdjustManualK2"),scalar("LandingAdjustManualK1"),scalar("LandingAdjustGroundMinCompressionTime"),scalar("LandingAdjustGroundK2"),scalar("LandingAdjustGroundK1"),
        scalar("LandingAdjustGrindStartUsingAnimTargetAfterTime"),scalar("LandingAdjustGrindK2"),scalar("LandingAdjustGrindK1"),scalar("LandingAdjustGrindBlendTowardsAnimTargetSpeed"),scalar("LandingAdjustDesiredCom"),
        scalar("LandingAdjustCoffinBounceTime"),scalar("LandingAdjustCoffinBounceMaxVel"),scalar("LandingAdjustCoffinBounceFramesToBlendAway"),scalar("LandingAdjustCoffinBounceBaseHeight")};
}
}
std::optional<AnimatedSkeletonSettings> AnimatedSkeletonSettings::Load(const SettingsDatabase& data,const PhysicsSkeleton& physical,const AnimationRig& rig,bool hat,std::string& error)
{
    error.clear();if(physical.bones.size()!=24){error="Stock skater physics skeleton must contain24 parts";return std::nullopt;}
    AnimatedSkeletonSettings settings;detail::SkeletonSettingReader fields(data,error);std::array<Vec3,24> sizes;std::array<std::uint32_t,24> shapes;
    const auto lookup=[&](std::string_view name)->std::optional<std::size_t>{for(std::size_t i=0;i<rig.bones.size();++i)if(AnimationBoneEqual(rig.bones[i].name,name))return i;error="Stock physics bone "+std::string(name)+" is absent from the animation hierarchy";return std::nullopt;};
    for(std::size_t part=0;part<24;++part)
    {
        const auto& bone=physical.bones[part];const auto index=lookup(bone.name);if(!index)return std::nullopt;settings.bone_indices[part]=*index;
        Vec4 translation;for(unsigned i=0;i<4;++i)translation[i]=detail::SkeletonSettingFloat(bone.words[16+i]);settings.physics_frames[part]=PhysicsBoneFrame(bone.Rotation(),translation);
        const auto size=bone.Size();sizes[part]={size[0],size[1],size[2]};const auto words=fields.Words<6>("physics_skeleton_bones","PART_"+bone.name);if(!error.empty())return std::nullopt;shapes[part]=words[3];
    }
    const std::array<const char*,4> names{{"LeftToeBase_Reparented","RightToeBase_Reparented","LeftHand_Reparented","RightHand_Reparented"}};
    for(unsigned i=0;i<4;++i){const auto index=lookup(names[i]);if(!index)return std::nullopt;settings.target_bones[i]=*index;}
    settings.masses=SkeletonAnimationMasses::FromBoneData(sizes,shapes,hat);settings.landing_on_board_blend=fields.NegativeGraph<8>("physics_animation","LandingOnDeckBLendVsTime");settings.landing=LoadLandingSettings(fields);
    if(!error.empty())return std::nullopt;return settings;
}
bool AnimatedSkeleton::ProcessPose(AnimatedSkeletonOwners owners,const std::vector<Mat4>& globals,LandingInput input,float dt,std::uint32_t& flags2468,std::uint32_t& flags2472,std::optional<LandingOnBoardPoseInput> on_board,std::string& error)
{
    error.clear();if(globals.empty()){error="Animation has no trajectory bone";return false;}motion.ProcessTrajectory(globals[0],owners.roots.animation_to_world,dt);
    std::array<Mat4,24> parts;if(!MapAnimationParts(globals,settings.bone_indices,settings.physics_frames,parts,error))return false;unadjusted_board=parts[0];SkeletonMotion::PublishUnadjustedBoard(parts[0],flags2472);
    const std::array<unsigned,4> physical_parts{{15,19,3,7}};
    for(unsigned i=0;i<4;++i){if(settings.target_bones[i]>=globals.size()){error="Missing animation IK target bone";return false;}targets[i]=ComposeSkeletonAffine(globals[settings.target_bones[i]],settings.physics_frames[physical_parts[i]]);}
    input.animation_com_height=owners.record.centre_of_mass[1]-parts[0][3][1];
    if(on_board){const auto& p=*on_board;const auto adjustment=LandingOnBoardPoseAdjustment(owners.roots.world_to_animation,p.deck,parts[0],p.offset,owners.board_frames.com_velocity[1],p.flags_2480,p.time,settings.landing_on_board_blend);if(adjustment)board_offset.RefreshTransform(*adjustment);}
    landing.Update(input,settings.landing,board_offset);board_offset.Update(parts[0],targets);owners.record.Update(parts,owners.roots.animation_to_board,settings.masses);
    animation_board=parts[0];animation_hips=parts[23];board_at_y_delta=motion.PublishAdjustedBoard(parts[0],flags2468);return true;
}
}
