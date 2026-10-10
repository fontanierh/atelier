#include "RespawnRuntime.h"
#include "GroundSurfaceRuntime.h"
#include "PlayerInputRuntime.h"
#include "SkaterAnimation.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Floats(RawVector bits)
{Vec4 result;for(unsigned i=0;i<4;++i)std::memcpy(&result[i],&bits[i],4);return result;}
}
std::optional<RespawnRuntime> RespawnRuntime::Load(const SettingsDatabase& data,Mat4 initial,std::uint32_t stance,std::string& error)
{RespawnSettings settings;if(!settings.Load(data,error))return std::nullopt;return RespawnRuntime{{initial,stance,false,0},settings};}
bool RespawnRuntime::Request(const WorldGeometry& world,SkaterAnimation& animation,TeleportStateRuntime& teleport,std::string& error)
{
    const auto stance=animation.CheckpointStance();RespawnScene scene(world,settings_);std::optional<RespawnCandidate> candidate;
    if(!history_.Automatic(stance,scene,candidate,error))return false;animation.RequestCheckpointStance(candidate->stance);teleport.Reply({candidate->transform,!candidate->offboard});return true;
}
bool RespawnRuntime::Observe(const PhysicalSimulationRuntime& physics,const PlayerInputRuntime& input,const SkaterAnimation& animation,RespawnCompletedState completed,std::string& error)
{
    const auto& physical=input.physical;const auto& p=input.processed;auto deck=physics.DeckFrame();
    if((p.flags_2468&0x00100000)!=0)RespawnFlip(deck);deck[3][1]+=.2f;
    auto offboard=physics.roots.animation_to_world;if((p.flags_2476&4)!=0)RespawnFlip(offboard);
    const auto velocity=Floats(physical.skateboard.vector_80);const auto stance=animation.CheckpointStance();
    std::uint32_t bits;std::memcpy(&bits,&measurements_,4);++bits;std::memcpy(&measurements_,&bits,4);
    std::uint32_t category;if(!ActivePlayerGroundSurface(physics.riding,physics.board,category,error))return false;
    const auto feet=(p.left_surface_2596>>7)&31;
    const RespawnObservation observation{measurements_,physics.roots.animation_to_world[3],Floats(physical.reckoning.vector_64),
        physical.state.flag_69!=0,physical.state.state_16,completed.state_frames,(p.grind.flags_1516&0x08000000)!=0,
        completed.offboard_contact_active,category&0xffff,{feet,feet},RespawnHeading(deck,velocity),offboard,stance,false};
    RespawnScene scene(physics.world,settings_);return history_.Observe(observation,settings_.minimum_frames,scene,error);
}
}
