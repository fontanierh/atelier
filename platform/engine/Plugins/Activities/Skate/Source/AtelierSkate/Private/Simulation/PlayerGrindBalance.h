#pragma once
#include "PlayerGrindContact.h"
namespace atelier::skate
{
struct PlayerGrindBalanceContact
{
    const PlayerGrindSurface& surface;
    Vec4 primitive_direction,directed_grind_direction;
    std::uint32_t kind;PlayerGrindEntryKind entry_kind;
};
struct PlayerGrindTargetUpInput {std::uint32_t category,previous_state;Vec4 board_up;};
struct PlayerGrindExitLeanInput {std::uint32_t category,current_state,grind_substate;float timestep;};
struct PlayerGrindBalanceVectors {Vec4 grind_normal,target_up;};
class PlayerGrindForceExitQueries
{
public:
    virtual ~PlayerGrindForceExitQueries()=default;
    virtual bool Query(PlayerGrindForceExitProbe,std::optional<PlayerGrindForceExitHit>&,std::string& error)=0;
};
struct PlayerGrindBalanceState
{
    float elapsed=0,exit_angle_degrees=0,entry_delay=2;std::int32_t frames_away=21;
    Vec4 previous_normal{0,1,0,0},exit_direction{1,0,0,0};
    void UpdateTargetUp(PlayerGrindTargetUpInput,const PlayerGrindBalanceContact*,PlayerGrindBalanceVectors&);
    float UpdateExitLean(PlayerGrindExitLeanInput,const PlayerGrindBalanceContact*,const PointGraph<8>&,PlayerGrindBalanceVectors&);
    bool UpdateForceExit(Vec4 primitive_location,std::uint32_t& flags,PlayerGrindForceExitQueries&,std::string& error) const;
};
}
