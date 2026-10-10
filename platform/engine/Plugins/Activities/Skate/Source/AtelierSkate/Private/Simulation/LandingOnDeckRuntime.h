#pragma once
#include "BipedGroundRuntime.h"
#include "LandingOnDeckSettings.h"
#include "AnimationPublication.h"
namespace atelier::skate
{
// State503 borrows the same Manager68, Biped skeleton16016 and physical/pose
// owners used by501 and500. The pose is the authoritative animation packet;
// shared.hierarchy references its hierarchy vector.
struct LandingOnDeckOwners
{
    BipedRuntimeOwners shared;
    BipedGroundRuntime& biped;
    PhysicsPosePacket& pose;
    SkeletonWobble& wobble;
};
class LandingOnDeckRuntime
{
public:
    LandingOnDeckState state;
    LandingOnDeckConfiguration configuration;
    bool Load(const SettingsDatabase&,std::string& error);
    bool Enter(LandingOnDeckOwners,std::string& error);
    bool Advance(LandingOnDeckOwners,std::string& error);
    bool PostPhysics(LandingOnDeckOwners,const WipeoutFrame& actual_frame,std::string& error);
    bool Fill(LandingOnDeckOwners,std::string& error) const;
    void Exit(LandingOnDeckOwners);
private:
    static void ClearIk(FootIk&);
    bool UpdateSkeleton(LandingOnDeckOwners,Vec4 position,std::string& error);
};
}
