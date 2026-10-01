// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimatedSkeleton.h"
#include "FootIkCore.h"
#include "PlayerInputTypes.h"
namespace atelier::skate
{
class FootIk
{
public:
    foot_ik::State state;
    foot_ik::Geometry geometry;
    foot_ik::Settings settings;
    foot_ik::PostSettings post_settings;
    std::array<std::size_t,24> bone_indices{};
    static std::optional<FootIk> Load(const SettingsDatabase&,const AnimationRig&,const AnimatedSkeleton&,std::string&);
    void EnableFeet(bool enabled){state.EnableFeet(enabled);}
    std::array<Vec4,2> PhysicalToePositions(const SkeletonPhysicalRecord&) const;
    bool Update(const AnimatedSkeleton&,AnimatedSkeletonOwners,const std::vector<Mat4>& actual_globals,
        const ProcessedPhysicsInput&,std::size_t contact_bone,const Mat4& physical_board,Vec4 hips_world_position,
        std::array<Mat4,24>& drives,std::string& error);
    std::array<bool,4> PostPhysics(SkeletonBody& body,const foot_ik::PostInput& input)
    {return foot_ik::PostPhysics(state,body,geometry,settings,post_settings,input);}
};
}
