#include "FootIk.h"
#include "SkeletonSettingReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
std::optional<FootIk> FootIk::Load(const SettingsDatabase& data,const AnimationRig& animation,const AnimatedSkeleton& skeleton,std::string& error)
{
    std::array<std::optional<std::size_t>,24> parents{};
    for(unsigned part=0;part<24;++part)
    {
        const auto bone=skeleton.settings.bone_indices[part];if(bone>=animation.bones.size()){error="IK bone exceeds stock hierarchy";return std::nullopt;}
        auto ancestor=animation.bones[bone].parent;std::vector<bool> visited(animation.bones.size(),false);
        while(ancestor>=0)
        {
            const auto index=static_cast<std::size_t>(ancestor);
            if(index>=visited.size()||visited[index]){error="Invalid stock IK hierarchy ancestor for part "+std::to_string(part);return std::nullopt;}visited[index]=true;
            const auto found=std::find(skeleton.settings.bone_indices.begin(),skeleton.settings.bone_indices.end(),index);
            if(found!=skeleton.settings.bone_indices.end()){parents[part]=static_cast<std::size_t>(found-skeleton.settings.bone_indices.begin());break;}
            ancestor=animation.bones[index].parent;
        }
    }
    const auto geometry=foot_ik::Geometry::Create(parents,skeleton.settings.physics_frames,error);if(!geometry||!geometry->ValidateLimbs(foot_ik::Limbs,error))return std::nullopt;
    FootIk result;result.geometry=*geometry;detail::SkeletonSettingReader r(data,error);
    const float half_width=r.Scalar("physicsdeck","DeckWidth")*0.5f,half_length=r.Scalar("physicsdeck","DeckMidLength")*0.5f;
    auto& s=result.settings;s.angle_limits.minimum_degrees=r.Scalar("physics_animation","IKMinAngle");s.angle_limits.maximum_degrees=r.Scalar("physics_animation","IKMaxAngle");
    s.blend.hand_inner_padding=r.Vector("physics_skeletonik","IKOnPadding");s.blend.hand_outer_padding=r.Vector("physics_skeletonik","IKOffPadding");
    s.blend.external_blend_step=r.Scalar("physics_skeletonik","FeetIKMaxBlendDeltaOut");s.blend.board_blend_step=r.Scalar("physics_skeletonik","FeetIKMaxBlendDelta");
    s.post_ik_padding=r.Vector("physics_skeletonik","PostIKPadding");s.contact_bounds=r.Vector("physics_skeletonik","IKBoneOnDeckBBox");s.foot_on_deck_padding=r.Vector("physics_skeletonik","FootOnDeckPadding");s.wipeout_feet_offset=r.Scalar("physics_skeletonik","WipeoutFeetOffset");
    s.deck_half_width=half_width;s.deck_half_length=half_length;s.deck_total_half_length=r.Scalar("physicsdeck","DeckFrontEndSize")+half_length;s.deck_front_angle_degrees=r.Scalar("physicsdeck","DeckFrontEndAngle");
    result.post_settings.minimum_board_up=r.Scalar("physics_animation","PostIKMinYAxisVal");result.post_settings.wipeout_height=r.Scalar("animation","FeetRelativeHeightWipeout");result.post_settings.riding_height=r.Scalar("animation","FeetRelativeHeightOnDeck");
    if(!error.empty())return std::nullopt;result.bone_indices=skeleton.settings.bone_indices;return result;
}
std::array<Vec4,2> FootIk::PhysicalToePositions(const SkeletonPhysicalRecord& record) const
{
    return {{TransformSkeletonPoint(record.pose[19],geometry.inverse_part_frames[20][3]),TransformSkeletonPoint(record.pose[15],geometry.inverse_part_frames[16][3])}};
}
bool FootIk::Update(const AnimatedSkeleton& skeleton,AnimatedSkeletonOwners owners,const std::vector<Mat4>& globals,const ProcessedPhysicsInput& input,std::size_t contact_bone,const Mat4& physical_board,Vec4 hips_world_position,std::array<Mat4,24>& drives,std::string& error)
{
    drives=owners.record.pose;
    if(input.state_2508==702)return true;
    auto originals=owners.record.pose;
    for(unsigned part=0;part<24;++part){if(bone_indices[part]>=globals.size()){error="IK original joint is absent from the current pose";return false;}originals[part]=globals[bone_indices[part]];}
    const Mat4 animated_world=ComposeSkeletonAffine(owners.roots.animation_to_world,owners.record.pose[0]),special_inverse=InverseSkeletonRigid(animated_world);
    const bool special=input.state_2508==503;
    std::array<std::optional<Vec4>,2> contacts;
    for(unsigned foot=0;foot<2;++foot)if(input.line_tests_960_1008_1056[foot].valid!=0)
    {Vec4 p;for(unsigned i=0;i<4;++i)p[i]=detail::SkeletonSettingFloat(input.line_tests_960_1008_1056[foot].position[i]);contacts[foot]=p;}
    const foot_ik::UpdateInput update{input.flags_2468,input.flags_2472,input.flags_2480,owners.roots.animation_to_world,owners.roots.world_to_animation,
        special?animated_world:physical_board,special?animated_world:owners.roots.board,special?special_inverse:owners.roots.inverse_board,
        owners.record.pose,originals,skeleton.targets,hips_world_position,contact_bone,{bone_indices[15],bone_indices[19]},contacts};
    (void)foot_ik::Update(state,update,geometry,settings,drives);return true;
}
}
