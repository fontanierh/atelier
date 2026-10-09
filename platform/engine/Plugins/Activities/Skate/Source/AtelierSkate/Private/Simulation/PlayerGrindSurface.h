#pragma once
#include "GrindAir.h"
#include <optional>
#include <vector>
namespace atelier::skate
{
struct PlayerGrindSurfaceInput {Vec4 start,end,reference;std::optional<Vec4> optional_probe;float deck_center_to_truck;};
struct PlayerGrindProbe {Vec4 start,end;float radius;};
struct PlayerGrindProbeHit {float fraction;Vec4 position,normal;std::uint32_t packed_surface;};
struct PlayerGrindInvestigation {Vec4 center,upmost_normal,direction;std::vector<PlayerGrindProbe> probes;};
enum class PlayerGrindGeometryKind:std::uint32_t {ThinRail=0,FatRail=1,Ledge=2,Impossible=3};
struct PlayerGrindSurface
{
    Vec4 center;
    std::array<Vec4,2> far_points;
    Vec4 upmost_normal,direction,high_side;
    std::array<float,2> normal_limits;
    PlayerGrindGeometryKind kind;
    std::uint32_t audio_surface,physics_surface,flags;
    Vec4 tilted_upmost_normal;
    static constexpr std::uint32_t Invalid=0x80000000,Curb=0x40000000,BlockedCrossSection=0x20000000,Stair=0x10000000,OptionalNormalTest=0x08000000,OptionalDropTest=0x04000000;
};
class PlayerGrindSurfaceQueries
{
public:
    virtual ~PlayerGrindSurfaceQueries()=default;
    virtual bool Query(std::size_t,PlayerGrindProbe,std::optional<PlayerGrindProbeHit>& result,std::string& error)=0;
};
std::optional<PlayerGrindInvestigation> PreparePlayerGrindSurface(PlayerGrindSurfaceInput);
PlayerGrindSurface ResolvePlayerGrindSurface(const PlayerGrindInvestigation&,
    const std::array<std::optional<PlayerGrindProbeHit>,7>&,std::uint32_t previous_flags);
bool InvestigatePlayerGrindSurface(PlayerGrindSurfaceInput,PlayerGrindSurfaceQueries&,PlayerGrindSurface& result,std::string& error);
// Uses the already published canonical landing-orientation transport consumed
// by GrindAir; no second orientation cache is created.
void UpdatePlayerGrindLandingOrientation(const PlayerGrindSurface*,Vec4 takeoff_position,
    Vec4 grind_position,Vec4& up,GrindAirLandingOrientation&);
Vec4 PlayerGrindTiltedNormal(Vec4 direction,Vec4 up,std::array<float,2> limits);
Vec4 PlayerGrindRotate(Vec4 axis,Vec4 value,float angle);
}
