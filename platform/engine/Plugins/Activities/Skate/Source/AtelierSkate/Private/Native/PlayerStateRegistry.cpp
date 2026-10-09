#include "PlayerStateRegistry.h"
namespace atelier::skate
{
namespace
{
bool Ordinary(PhysicalStateId state)
{
    switch(state)
    {
    case PhysicalStateId::PhysicsGround:case PhysicalStateId::PhysicsAir:
    case PhysicalStateId::FootPlant:case PhysicalStateId::Boneless:
    case PhysicalStateId::HandPlant:case PhysicalStateId::RevertGround:
    case PhysicalStateId::KnownAir:case PhysicalStateId::BipedAir:
    case PhysicalStateId::BipedGround:case PhysicalStateId::OffBoardPushing:
    case PhysicalStateId::GroundAnimation:case PhysicalStateId::SlideGround:
    case PhysicalStateId::WipeoutGround:case PhysicalStateId::Teleporting:
    case PhysicalStateId::LandingOnDeck:return true;
    default:return false;
    }
}
}
PlayerStateCapability PlayerStateRegistry::Capability(PhysicalStateId state) const
{
    const bool supported=IsGrindState(state)||state==PhysicalStateId::Nonspecific
        ||state==PhysicalStateId::Sleeping||Ordinary(state);
    return {state,supported,supported&&state!=PhysicalStateId::Sleeping,supported};
}
bool PlayerStateRegistry::CanTransition(PhysicalStateId current,PhysicalStateId requested) const
{
    if(!Capability(current).supported||!Capability(requested).supported)return false;
    if(current!=PhysicalStateId::Sleeping&&(IsGrindState(current)||IsGrindState(requested)
        ||current==PhysicalStateId::Nonspecific||requested==PhysicalStateId::Nonspecific))return true;
    return (current==PhysicalStateId::Sleeping&&requested==PhysicalStateId::PhysicsGround)
        ||(Ordinary(current)&&Ordinary(requested));
}
}
