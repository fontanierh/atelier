#pragma once
#include "PlayerGrindInput.h"
#include "BoardPhysicsSettings.h"
namespace atelier::skate
{
// One source physics-owner cache, captured at initialization. The global owner
// supplies this same object to pre input and the later physical grind phases.
class PlayerGrindMaterials
{
public:
    explicit PlayerGrindMaterials(const BoardPhysicsSettings& s):standard_{s.standard_wheel_material,s.collision.truck_material,s.collision.deck_material}{}
    void Apply(PlayerGrindMaterialMode,BoardRuntime&,BoardPhysicsSettings&) const;
    const std::array<ContactMaterial,3>& Standard() const {return standard_;}
private:
    std::array<ContactMaterial,3> standard_;
};
class PlayerGrindLiveHost final:public PlayerGrindInputHost
{
public:
    PlayerGrindLiveHost(BoardRuntime& b,BoardPhysicsSettings& s,const PlayerGrindMaterials& m):board_(b),settings_(s),materials_(m){}
    bool ApplyMaterialMode(PlayerGrindMaterialMode,std::string& error) override;
    bool SurfaceProbe(const WorldGeometry&,std::array<std::uint32_t,2>,std::size_t,PlayerGrindProbe,std::optional<PlayerGrindProbeHit>&,std::string& error) override;
    bool ForceExitLine(const WorldGeometry&,std::array<std::uint32_t,2>,PlayerGrindForceExitProbe,std::optional<PlayerGrindForceExitHit>&,std::string& error) override;
private:
    BoardRuntime& board_;BoardPhysicsSettings& settings_;const PlayerGrindMaterials& materials_;
};
}
