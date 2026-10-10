#pragma once
#include "SkeletonPoseFrames.h"
#include "Settings.h"
namespace atelier::skate
{
struct GrindAirLandingOrientation
{
    std::uint32_t kind=0;bool garbage=false;
    Vec4 boardslide_dir{},tipslide_dir{},backslash_dir{},high_side{};
};
struct GrindAirTarget
{
    Vec4 start{},end{};std::uint64_t owner=0;
    std::uint32_t primitive_flags=0;
    GrindAirLandingOrientation orientation;
};
struct GrindAirInput
{
    bool active;
    Mat4 board;
    Vec4 velocity,angular_velocity,up;
    float timestep;
    std::uint32_t flags_2468,flags_2472,flags_2480,flags_2484;
};
struct GrindAirSettings
{
    std::size_t frames=0;float stomp=0;
    std::array<Vec4,5> points{};
    std::array<float,7> ranges{},distances{},yaw_assist{};
    float max_offset=0,max_delta=0,max_angle=0;
    bool Validate(std::string&) const;
    static std::optional<GrindAirSettings> Load(const SettingsDatabase&,std::string&);
};
struct GrindAirDeckDimensions
{
    float middle_length,front_end_size,front_end_angle_degrees,truck_z_front,truck_y;
    std::array<Vec4,5> ContactPoints(float tip_fraction) const;
};
struct GrindAirPoseInput {Mat4 animation_to_world,world_to_animation;Vec4 physical_forward,animation_board_position;};
struct GrindAirAdjustment
{
    Vec4 axis,offset,angles;
    Mat4 LocalTransform(const GrindAirPoseInput&) const;
};
class GrindAir
{
public:
    std::optional<GrindAirTarget> target;
    Vec4 offset_delta{},offset{},angle_delta{},angles{};
    std::optional<std::size_t> selected_kind;
    std::array<float,12> headings{};
    void Start(GrindAirTarget);
    bool Update(GrindAirInput,const GrindAirSettings&,std::optional<GrindAirAdjustment>&,std::string&);
};
}
