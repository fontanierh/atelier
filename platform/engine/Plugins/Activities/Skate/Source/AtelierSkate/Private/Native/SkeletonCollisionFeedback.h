// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonCollisionMode.h"
namespace atelier::skate
{
struct SkeletonFeedbackSettings
{
    SkeletonCollisionSettings body;
    float small_object_mass,ground_plane_max_distance,ground_plane_max_angle,skater_scalar,ai_scalar;
    Vec4 groin_offset,face_offset;
    float groin_radius,face_radius;
};
struct SkeletonContactBody {std::uint32_t state_flags;float inverse_mass;Vec4 linear_velocity;};
struct SkeletonContactReport
{
    std::size_t part;
    Vec4 normal,point;
    std::uint32_t tag,other_group;
    std::optional<std::int32_t> other_entity;
    SkeletonContactBody body_a,body_b;
    bool side_a;
    Vec4 solved_vector;
};
struct SkeletonCollisionInput
{
    float dt;
    Vec4 plane_point,plane_normal,reference_velocity,com_velocity;
    bool ragdoll,disable_ground_filter,ai_collision_scalar,offboard,entering_offboard,category_600,request_partial_ragdoll;
    const SkeletonPhysicalRecord& physical;
    const std::array<float,SkeletonAnimationPartCount>& part_weights;
    const std::array<Mat4,SkeletonPartCount>& body_frames;
};
struct SkeletonBoneContact
{
    Vec4 normal{},specific_normal{},tangent{},specific_tangent{},point{};
    float force=0,specific_force=0;
    std::uint32_t tag=0,specific_tag=0;
    std::array<bool,4> groups{};
};
struct SkeletonContactRegion
{
    float force=0,weighted_force=0,tangent_speed=0;
    std::uint32_t material_flags=0;
    Vec4 normal{};
    std::optional<std::size_t> part;
};
struct SkeletonContactPlane {Vec4 normal{};std::size_t part=0;};
struct SkeletonSpecificContact
{
    std::size_t part;
    Vec4 local_point,world_point;
    float radius_squared;
    bool current,recent;
};
struct SkeletonContactFlags
{
    bool material_6=false,noncompliant=false,compliant=false,recovering=false,group_8=false,nonboard=false,ragdoll=false;
    bool conflicting=false,impaled=false,has_impulse=false,foot_board=false,material_10=false,material_11=false,material_12=false,any=false;
};
class SkeletonCollisionFeedback
{
public:
    SkeletonFeedbackSettings settings;
    std::array<float,24> contact_age{},priority{};
    std::array<bool,24> compliant{},current{};
    std::array<SkeletonBoneContact,24> bones{};
    std::array<SkeletonContactRegion,8> regions{};
    std::vector<SkeletonContactPlane> planes;
    std::array<SkeletonSpecificContact,2> specific;
    Vec4 highest_normal{0,1,0,0},foot_normal{0,1,0,0};
    std::array<Vec4,2> material_normals{};
    float timer=0,drive_weight=0,maximum_priority=0;
    std::array<float,3> wipeout_times{};
    float maximum_skater_force=0;
    std::int32_t other_skater=-1;
    float maximum_group_8_force=0,maximum_group_11_force=0,material_12_height=0;
    SkeletonContactFlags flags{};
    explicit SkeletonCollisionFeedback(SkeletonFeedbackSettings settings);
    void Reset();
    void SetUpNormal();
    void Update(const SkeletonCollisionInput& input,const std::vector<SkeletonContactReport>& reports);
    Vec4 FilterError(Vec4 error,Vec4 axis) const;
private:
    void BeginFrame(const SkeletonCollisionInput& input);
    bool IgnoreGround(const SkeletonCollisionInput& input,const SkeletonContactReport& report) const;
    void ObserveNormal(bool ragdoll,const SkeletonContactReport& report,std::uint32_t material);
    void RecordForce(const SkeletonContactReport& report,bool specific,Vec4 relative,float force,float weighted_force);
    bool CheckConflicting(const SkeletonCollisionInput& input) const;
    bool CheckImpaled() const;
};
}
