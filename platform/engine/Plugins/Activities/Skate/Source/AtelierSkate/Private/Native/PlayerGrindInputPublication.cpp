// SPDX-License-Identifier: Apache-2.0
#include "PlayerGrindInput.h"
#include "PlayerGrindInputDetail.h"
namespace atelier::skate
{
using namespace player_grind_detail;
void PublishPlayerGrindSurface(GrindInvestigationFields& f,const PlayerGrindSurface& s)
{
    f.center_1360=Raw4(s.center);for(std::size_t i=0;i<2;++i)f.far_points_1376_1392[i]=Raw4(s.far_points[i]);
    f.upmost_normal_1408=Raw4(s.upmost_normal);f.surface_direction_1424=Raw4(s.direction);f.high_side_1440=Raw4(s.high_side);
    f.normal_limits_1456_1460=s.normal_limits;f.geometry_kind_1464=std::uint32_t(s.kind);f.audio_surface_1468=s.audio_surface;
    f.physics_surface_1472=s.physics_surface;f.geometry_flags_1476=s.flags;
}
bool MakePlayerGrindObservation(const ProcessedPhysicsInput& p,PlayerGrindPostContext c,std::optional<std::array<std::uint64_t,2>> metadata,
    const PlayerGrindJumper& j,std::optional<PlayerGrindObservation>& output,std::string& error)
{
    const auto& f=p.grind;
    // The original evaluates control's family before the jumper family.
    if(f.family_1248>5){error="Invalid published grind family "+std::to_string(f.family_1248);return false;}
    if(j.family>5){error="Invalid published grind family "+std::to_string(j.family);return false;}
    output=PlayerGrindObservation{
        {Float4(f.point_1120),Float4(f.direction_1136),Float4(f.normal_1152),Float4(f.target_up_1168),Float4(f.primitive_start_1264),Float4(f.primitive_end_1280),
            metadata,Float4(f.upmost_normal_1408),Float4(f.high_side_1440),f.geometry_kind_1464,f.geometry_flags_1476,f.impact_speed_1492},
        {f.audio_surface_1468,f.physics_surface_1472,f.friction_1496,f.exit_lean_1500,f.gravity_relief_1512},
        {PlayerGrindFamily(f.family_1248),f.flags_1516,p.flags_2468,p.flags_2488,c.translation_2796,c.stability_nudge_2800,f.exit_lean_1500},
        {Float4(f.entry_velocity_1184),f.family_1248},
        {j.geometry.geometry_kind,PlayerGrindFamily(j.family),j.energy,j.geometry.high_side,j.geometry.normal,j.geometry.direction,j.geometry.upmost,j.geometry.point}};
    return true;
}
}
