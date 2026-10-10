#include "GrindRuntimeInternal.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace grind_detail;
bool GrindRuntime::Fill(GrindRuntimeOwners o,std::string& error)
{
    if(nonspecific_active){if(nonspecific_jumped){o.input.physical.air.launch_velocity_128=Raw(nonspecific_jump_velocity);o.input.physical.air.launched_442=1;}return true;}
    if(!manager){error="Grind Fill requires completed manager observation";return false;}
    if(!active){error="Grind Fill requires active state";return false;}
    const auto family=*active;const auto& state=states[std::size_t(family)];const auto& g=manager->geometry;
    auto& out=o.input.physical.grinds;
    out.direction_0=Raw(state.direction);out.point_16=Raw(g.point_1120);out.normal_32=Raw(state.normal);out.across_48=Raw(state.across);
    out.primitive_start_64=Raw(g.primitive_start_1264);out.primitive_end_80=Raw(g.primitive_end_1280);
    if(g.kind_1464==2)out.high_side_112=Raw(g.high_side_1440);
    if(g.spline_guids_1296)out.spline_guids_224_232=*g.spline_guids_1296;
    out.impact_speed_128=g.impact_speed_1492;out.crouch_132=state.crouch;out.words_136_140={std::uint32_t(family),state.substate};
    out.audio_surface_216=manager->surface.audio_surface_1468;out.trick_out_240=state.classification_104;out.leaving_317=state.leaving;
    out.is_ledge_320=g.kind_1464==2;out.curb_321=(g.flags_1476&0x40000000)!=0;
    if(family==PlayerGrindFamily::Tipslide||family==PlayerGrindFamily::FiveO||family==PlayerGrindFamily::Backslash)out.flag_318=(manager->control.flags_1516&0x20000000)!=0;
    if(family==PlayerGrindFamily::Tipslide){out.dropping_in_324=state.tipslide_97_98_99[0];out.tipslide_325=state.tipslide_97_98_99[1];out.tipslide_326=state.tipslide_97_98_99[2];}
    if(state.just_jumped){o.input.physical.air.launch_velocity_128=Raw(state.jump_velocity);o.input.physical.air.launched_442=1;}
    pending_wipeout_impulse=(state.slide_wipeout&&(family==PlayerGrindFamily::Boardslide||family==PlayerGrindFamily::Darkslide))?std::optional<Vec4>(state.slide_impulse):std::nullopt;
    if(pending_wipeout_impulse){o.input.physical.physics.vector_16=Raw(*pending_wipeout_impulse);o.input.physical.physics.flag_32=1;pending_wipeout_impulse.reset();}
    return true;
}
void ApplyGrindWorldForce(BoardRuntime& board,Vec4 force,Vec4 point)
{
    auto& deck=board.BodiesMut()[6];auto& r=deck.rates;
    const Vec3 arm{point[0]-r.position.x,point[1]-r.position.y,point[2]-r.position.z};
    Basis3 identity;identity.columns={{{1,0,0},{0,1,0},{0,0,1}}};
    const auto next=AccumulatePointForce({r.force_acceleration,r.torque_acceleration,r.cool_down},Xyz(force),arm,identity,deck.inertia.inverse_mass,r.world_inverse_inertia);
    r.force_acceleration=next.force_acceleration;r.torque_acceleration=next.torque_acceleration;r.cool_down=next.cool_down;
}
void GrindManageWheelSpin(BoardRuntime& board,std::array<bool,4> contact)
{
    for(std::size_t i=0;i<4;++i)board.BodiesMut()[i].inertia.angular_drag=(contact[i]?0.5f:0.0f)*Float(0x426fffff);
}
void GrindClearWheelSpin(BoardRuntime& board){for(std::size_t i=0;i<4;++i)board.BodiesMut()[i].inertia.angular_drag=0;}
}
