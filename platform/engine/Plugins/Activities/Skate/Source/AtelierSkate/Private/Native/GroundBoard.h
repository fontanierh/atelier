#pragma once
#include "GroundStateCorrections.h"
#include "GroundDrag.h"
#include "GroundPropulsion.h"
#include "GroundContactResponse.h"
#include "GroundForce.h"
#include "GroundLaunchInfo.h"
#include "SpeedModel.h"
#include "SpeedWobble.h"
#include "Steering.h"
#include "Pumping.h"
#include "SlideFriction.h"
#include "Straighten.h"
#include "Heading.h"
#include "AntiFlip.h"
namespace atelier::skate
{
struct GroundBoardSettings
{
    const SteeringSettings& steering;
    const SpeedWobbleSettings& speed_wobble;
    GroundPropulsionSettings propulsion;
    const GroundForceSettings& ground_force;
    const SpeedModelSettings& speed_model;
    const SlideFrictionSettings& slide_friction;
    const StraightenSettings& straighten;
    const HeadingSettings& heading;
    const AntiFlipSettings& anti_flip;
    const ManualSettings& manual;
    ManualMode manual_mode;
    LinearDragSettings linear_drag;
    float collision_response_duration, collision_response_scale;
    float ground_force_contact_time_limit, speed_model_reset_force_squared;
};
struct GroundForceFrame
{
    float argument_1_2752, processed_2776, processed_2780, previous_state_scalar_56;
    float ground_scalar_1216, ground_scalar_1232, ground_scalar_1236, ground_scalar_1240;
    float balance_2720, surface_speed_2656;
    Vec4 axis_384, velocity_400, axis_544;
};
struct GroundBoardInput
{
    SteeringInput steering;
    SpeedWobbleInput speed_wobble;
    std::uint32_t truck_flags_2468,truck_flags_2472;
    GroundContactFrame contact;
    Vec4 ground_vector_1216;
    GroundPropulsionInput propulsion;
    GroundForceFrame ground_force;
    SpeedModelInput speed_model;
    SlideFrictionInput slide_friction;
    PumpForceInput pump_force;
    StraightenInput straighten;
    HeadingInput heading;
    AntiFlipInput anti_flip;
    ManualInput manual;
    GroundDragInput ground_drag;
    float contact_time_2756;
    std::uint32_t trajectory_state_1776_bits;
    AntiFlipNudgeInput anti_flip_nudge;
    HangUpInput hang_up;
    HalfpipeWheelCatchInput halfpipe_wheel_catch;
    PinningInput pinning;
};
struct GroundBoardComponents
{
    SpeedWobbleState& speed_wobble;
    TruckSteeringState& truck_steering;
    SpeedModelState& speed_model;
    ManualState& manual;
    float& heading_previous;
    BoardForceQueue& force_queue;
    BodyInertias& inertias;
};
using GroundBoardContactResponse=GroundContactResponse;
struct GroundBoardCollisionResponse
{
    Vec4 force_2528,point_2544,vector_2592;
    QueuedPointForce TaggedForce() const;
};
enum class GroundBoardStage
{
    CenterOfMassHeight,SetWheelMaterials,ContactResponse,UpdateBodyAccumulator,
    SetAnimatedVelocity,WriteProcessedVelocity,BuildAnimatedPose,PublishAnimatedPose,
    UpdateExternalPlayer,CommitExternalPlayer,FinalizeAnimatedBoard,CollisionForce,
    ApplyCollisionVector,CollisionProjection,ManualEffect,PushForceSquared,AntiFlipNudge,
    ApplyCollisionDecay,ApplyStraighten,ApplyHeading,ApplyAntiFlip,ApplyManual,HangUps,
    HalfpipeWheelCatch,Pinning,StrongForceSquared
};
struct GroundBoardError
{
    enum class Kind {Service,Manual,Drag} kind=Kind::Service;
    GroundBoardStage stage=GroundBoardStage::CenterOfMassHeight;
    std::string source;
    ManualError manual;
    DragBindingError drag=DragBindingError::PartOutsideAssembly;
};
struct OrdinaryGroundResult
{
    bool manual_correction;
    std::uint32_t terminal_force_tag;
    bool terminal_force_queued,speed_model_reset;
};
struct GroundBoardOutcome
{
    enum class Kind {Animated,Collision,Ordinary} kind;
    bool tag_15_queued=false;
    OrdinaryGroundResult ordinary{};
};
// Concrete physical owners must supply every called service. The animated
// packet uses the actual retained launch layout rather than an opaque pose.
class GroundBoardServices:public ManualAngleMeasurement,public GroundCorrectionServices
{
public:
    virtual bool CenterOfMassHeight(float&,std::string&)=0;
    virtual bool SetContactWheelMaterials(std::string&)=0;
    virtual bool ContactResponse(GroundContactFrame,Vec4 previous,GroundBoardContactResponse&,std::string&)=0;
    virtual bool UpdateBodyAccumulator(std::string&)=0;
    virtual bool SetAnimatedVelocity(Vec4,std::string&)=0;
    virtual bool WriteProcessedVelocity(Vec4,std::string&)=0;
    virtual bool BuildAnimatedPose(GroundLaunchInfo&,std::string&)=0;
    virtual bool PublishAnimatedPose(const GroundLaunchInfo&,std::string&)=0;
    virtual bool UpdateExternalPlayer(const GroundLaunchInfo&,Vec4,std::string&)=0;
    virtual bool CommitExternalPlayer(std::string&)=0;
    virtual bool FinalizeAnimatedBoard(std::string&)=0;
    virtual bool CollisionForce(Vec4, std::optional<GroundBoardCollisionResponse>&,std::string&)=0;
    virtual bool CollisionForceDotVelocity(Vec4 force,Vec4 velocity,float&,std::string&)=0;
    virtual bool ApplyVector(Vec4,std::string&)=0;
    virtual bool ApplyAngularDisplacement(Vec4,std::string&)=0;
};
std::optional<GroundBoardOutcome> UpdateGroundBoard(PhysicsGroundState&,GroundBoardComponents,
    GroundBoardSettings,GroundBoardInput,GroundBoardServices&,GroundBoardError&);
}
