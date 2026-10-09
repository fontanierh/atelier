#pragma once
#include "SkeletonPoseFrames.h"
#include <optional>

namespace atelier::skate::foot_ik
{
enum class Mode {Disabled,OnDeck,External,Local};
struct LimbBinding {std::size_t part;std::optional<std::size_t> parent_part;};
inline const std::array<LimbBinding,4> Limbs{{{15,16},{19,20},{3,std::nullopt},{7,std::nullopt}}};
struct LimbStatus
{
    Mode mode=Mode::Disabled;
    float board_blend=0,external_blend=0,target_blend=0;
    bool external_target_set=false,local_target_set=false;
    Vec4 external_target_local_delta{},part_position{};
};
struct LimbFrames
{
    Mat4 target=SkeletonIdentity,world=SkeletonIdentity,external_world=SkeletonIdentity;
    Mat4 board=SkeletonIdentity,parent_world=SkeletonIdentity,external_parent_world=SkeletonIdentity;
    Mat4 parent_board=SkeletonIdentity;
    bool within_contact_bounds=false;
};
struct ExternalTarget
{
    Vec4 world_position{},animation_position{},normal{};
    bool normal_set=false;
    float normal_blend=0;
};
struct FootContact {std::uint32_t query_state=0;Vec4 position{};float desired_offset=0,offset=0;};
struct ContactState
{
    std::array<FootContact,2> feet{};
    bool support_failed=false,support_failed_this_update=false;
};
struct BlendSettings {Vec4 hand_inner_padding{},hand_outer_padding{};float external_blend_step=0,board_blend_step=0;};
struct AngleLimits {float minimum_degrees=0,maximum_degrees=0;};
struct Settings
{
    AngleLimits angle_limits;
    BlendSettings blend;
    Vec4 post_ik_padding{},contact_bounds{},foot_on_deck_padding{};
    float wipeout_feet_offset=0,deck_half_width=0,deck_half_length=0,deck_total_half_length=0,deck_front_angle_degrees=0;
};
struct PostSettings {float minimum_board_up=0,wipeout_height=0,riding_height=0;};
struct Geometry
{
    std::array<std::optional<std::size_t>,24> parents{};
    std::array<Mat4,24> inverse_part_frames{};
    static std::optional<Geometry> Create(std::array<std::optional<std::size_t>,24>,const std::array<Mat4,24>&,std::string&);
    bool ValidateLimbs(const std::array<LimbBinding,4>&,std::string&) const;
};
struct State
{
    std::array<LimbStatus,4> limbs{};
    std::array<LimbFrames,4> frames{};
    std::array<ExternalTarget,4> external_targets{};
    ContactState contacts;
    bool feet_enabled=true;
    void Reset(){*this=State{};}
    void EnableFeet(bool enabled){feet_enabled=enabled;}
    void MarkSupportFailedThisUpdate(){contacts.support_failed_this_update=true;}
};
struct UpdateInput
{
    std::uint32_t flags_2468,flags_2472,flags_2480;
    const Mat4& animation_to_world;
    const Mat4& world_to_animation;
    const Mat4& physical_board;
    const Mat4& contact_board;
    const Mat4& inverse_contact_board;
    const std::array<Mat4,24>& animation;
    const std::array<Mat4,24>& original_animation;
    const std::array<Mat4,4>& targets;
    Vec4 hips_world_position;
    std::size_t contact_bone;
    std::array<std::size_t,2> foot_bones;
    std::array<std::optional<Vec4>,2> current_contacts;
};
struct PostInput
{
    std::uint32_t state_id,category_id;
    bool board_body_flag_868,wipeout;
    std::uint32_t flags_2468,flags_2484;
    float value_2664;
    std::uint32_t state_2520;
    const Mat4& world_to_animation;
    const Mat4& board;
};
enum class SolveResult {Solved,Extended,Invalid};
}
