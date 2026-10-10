#pragma once
#include "SlideStateSettings.h"
#include "BoardRuntime.h"
#include "Steering.h"
#include "Manual.h"
#include "GroundForce.h"
#include "GroundContactResponse.h"
#include "RidingCollisionResponse.h"
namespace atelier::skate
{
struct SlideLifecycleTargets
{
    bool& skeleton_elapsed_16505;
    float& air_spin_angle;
    float& air_spin_speed;
    std::uint8_t& board_animated_290;
    ManualState& manual;
    std::uint32_t& wipeout_mode;
    float& wipeout_balance;
};
void EnterSlideState(SlideState&,BoardRuntime&,SlideLifecycleTargets,std::uint32_t category,float surface_speed);
void ExitSlideState(SlideState&,ContactMaterial& wheel_material,const ContactMaterial& standard_wheel_material);
struct SlideGroundForceFrame
{
    float argument_1_2752,ground_scalar_1216,ground_scalar_1240,ground_scalar_1236,balance_2720,surface_speed_2656;
    Vec4 axis_384,velocity_400,axis_544;
};
struct SlideGroundInputs
{
    SteeringInput steering;
    ManualInput manual;
    GroundContactFrame contact;
    SlideGroundForceFrame force;
    const SteeringSettings& steering_settings;
    const ManualSettings& manual_settings;
    ManualMode manual_mode;
    const GroundForceSettings& force_settings;
    const WallRideSettings& wall_settings;
};
// Read after Skeleton Ground and Slide's own capture, from the actual processed
// packet, toolkit, animation input and reckoning. Every numeric lane is explicit.
struct SlideCompletedFrame
{
    std::uint32_t surface_mode,pumping_mode,flags_2468,flags_2472,wheel_count;
    SlideInput slide;
    Vec4 up,collision_displacement,collision_velocity,travel_direction;
    Vec3 ground_normal;
    float total_mass,gravity,scalar_2652,processed_timestep;
};
struct SlideCollisionForce {Vec4 force_2528,point_2544,vector_2592;};
// No default implementations: these are the original live producer/retained
// owner boundaries. The physical coordinator supplies their concrete owners.
class SlideStateServices
{
public:
    virtual ~SlideStateServices()=default;
    virtual bool RequireCurrentSlideToolkit(std::string& error)=0;
    virtual bool UpdateSlideReckoning(std::string& error)=0;
    virtual bool UpdateSlideSkeletonGround(std::string& error)=0;
    virtual bool CaptureSlidePhysicsError(std::string& error)=0;
    virtual std::optional<SlideCompletedFrame> ReadCompletedSlideFrame(std::string& error)=0;
    // Selects the actual pumping mode before running GroundSettings::input.
    virtual std::optional<SlideGroundInputs> PrepareSlideGroundInput(std::uint32_t pumping_mode,std::string& error)=0;
    // Applied response replaces the real retained force; early/late false
    // leaves it untouched. The caller deliberately ignores angular publication.
    virtual bool CalculateSlideCollisionForce(RidingCollisionPhysical,std::optional<SlideCollisionForce>& applied,std::string& error)=0;
    // Actual launch-info/selector/launch/grind-context/update sequence. Runtime
    // has already published all board velocities and cleared linear drags.
    virtual bool LaunchSlideTrajectory(Vec4 velocity,std::string& error)=0;
};
struct SlideRuntimeTargets {BoardRuntime& board;ManualState& manual;TruckSteeringState& steering;ContactMaterial& wheel_material;};
bool UpdateSlideState(SlideState&,const SlideStateSettings&,SlideRuntimeTargets,SlideStateServices&,std::string& error);
}
