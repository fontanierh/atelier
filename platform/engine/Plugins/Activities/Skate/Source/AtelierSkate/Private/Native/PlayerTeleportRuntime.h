#pragma once
#include "PlayerInputRuntime.h"
#include "GroundStateRuntime.h"
#include "SkeletonController.h"
#include "SkeletonAirRuntime.h"
#include "FootplantRuntime.h"
#include "Handplant.h"
#include "OffboardGrabCache.h"
#include "WipeoutRequests.h"
namespace atelier::skate
{
struct PlayerTeleportLifecycle
{
    GroundStateRuntime& ground;
    SkeletonControllerState& skeleton_controller;
    SkeletonAir& skeleton_air;
    FootplantRuntime& footplant;
    Handplant& handplant;
    OffboardGrabCache& offboard_grab;
    WipeoutRequests& wipeout;
    SkeletonWobble& wobble;
    bool& skeleton_elapsed_16505;
    std::uint8_t& board_animated_290;
};
struct PlayerTeleportFrame
{
    const AnimationInputPacket& packet;
    SkeletonInputPose pose;
    // Same mutable callback snapshot used by the following ProcessData. Source
    // refreshes four fields at ResetSystems, even if a later pose step fails.
    SkeletonInputCollision& collision;
    bool& teleported;
};
Mat4 HorizontalPlayerTeleportSpawn(Mat4 requested);
// Complete current input_teleport.rs reset_player over the actual owners.
// The input coordinator provides this scope's packet and callback snapshot;
// state selection and possession-stop scheduling remain separate. The source
// global reset does not call Ground.Enter.
class PlayerTeleportRuntime
{
public:
    explicit PlayerTeleportRuntime(PlayerTeleportLifecycle lifecycle):lifecycle_(lifecycle){}
    bool ResetPlayer(PlayerInputOwners,Mat4 requested,PlayerInputState&,PhysicalPlayerInput&,
        ProcessedPhysicsInput&,PlayerTeleportFrame,std::string& error);
private:
    PlayerTeleportLifecycle lifecycle_;
};
}
