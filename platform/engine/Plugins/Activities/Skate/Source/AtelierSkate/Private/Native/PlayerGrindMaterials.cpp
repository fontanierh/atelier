// SPDX-License-Identifier: Apache-2.0
#include "PlayerGrindMaterials.h"
namespace atelier::skate
{
void PlayerGrindMaterials::Apply(PlayerGrindMaterialMode mode,BoardRuntime& board,BoardPhysicsSettings& s) const
{
    if(mode==PlayerGrindMaterialMode::Unchanged)return;
    const std::array<ContactMaterial,3> materials=mode==PlayerGrindMaterialMode::Standard?standard_:std::array<ContactMaterial,3>{};
    board.SetCollisionGroup(4);s.collision.wheel_material=materials[0];s.collision.truck_material=materials[1];s.collision.deck_material=materials[2];
}
bool PlayerGrindLiveHost::ApplyMaterialMode(PlayerGrindMaterialMode mode,std::string&){materials_.Apply(mode,board_,settings_);return true;}
bool PlayerGrindLiveHost::SurfaceProbe(const WorldGeometry& w,std::array<std::uint32_t,2> a,std::size_t i,PlayerGrindProbe p,std::optional<PlayerGrindProbeHit>& out,std::string& error)
{return PlayerGrindSurfaceProbe(w,a,i,p,out,error);}
bool PlayerGrindLiveHost::ForceExitLine(const WorldGeometry& w,std::array<std::uint32_t,2> a,PlayerGrindForceExitProbe p,std::optional<PlayerGrindForceExitHit>& out,std::string& error)
{return PlayerGrindForceExitLine(w,a,p,out,error);}
}
