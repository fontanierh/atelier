#pragma once
#include "PhysicalSimulationRuntime.h"
#include "PlayerInputTypes.h"
namespace atelier::skate
{
struct PlayerDynamicNormalSettings
{
    float speed_damping,up_vector_damping,maximum_delta,speed_scale;
    PointGraph<8> maximum_delta_vs_speed;
    bool Load(const SettingsDatabase&,std::string& error);
};
// These four histories are input-owner fields, not a second body/contact cache.
// Only contacts already published by the actual shared solve are consumed.
struct PlayerDynamicNormal
{
    Vec3 normal{0,1,0},delta{0,1,0},acceleration{},last_contact_normal{};
    void Update(const BoardGroundState&,Vec3 gravity,float previous_ground_speed,const PlayerDynamicNormalSettings&);
};
struct PlayerBoardInputFrame
{
    Vec3 processed_forward,reckoning_normal_1216,reckoning_ground_up,retained_ground_normal_112;
    std::uint32_t processed_flags_2476;
};
void PublishPlayerBoardInput(PhysicalPlayerInput&,const BoardMotionOutput&,const BoardGroundState&,PlayerBoardInputFrame);
// Same live retained toolkit is required by host publication, never recreated
// from a fresh solved transform. Failure leaves every output field untouched.
bool PublishPlayerBoardOutputs(PhysicalPlayerInput&,const PhysicalRidingOutputs&,
    const std::optional<BoardToolkit>&,const PlayerDynamicNormal&,const ProcessedPhysicsInput&,std::string& error);
class PlayerTrajectoryGrindOwner
{
public:
    virtual ~PlayerTrajectoryGrindOwner()=default;
    // Must read the actual retained TrajectorySelector (the simulation flag9653).
    virtual bool GrindLockedToMiddle() const=0;
};
bool PublishPlayerGrindGraphOutputs(PhysicalPlayerInput&,const SkeletonPhysicalRecord&,Vec4 reckoning_up,
    const std::optional<BoardToolkit>&,const PlayerTrajectoryGrindOwner&,std::string& error);
}
