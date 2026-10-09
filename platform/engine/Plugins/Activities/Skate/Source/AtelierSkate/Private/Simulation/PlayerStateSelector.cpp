#include "PlayerStateSelector.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
using S=PhysicalStateId;
float Float(std::uint32_t w) {float f;std::memcpy(&f,&w,4);return f;}
std::int32_t Increment(std::int32_t v) {std::uint32_t w;std::memcpy(&w,&v,4);++w;std::memcpy(&v,&w,4);return v;}
std::optional<S> CheckGrind(ProcessedStateInput p)
{
    if (!p.grind_candidate_1488||p.Has2480(0x20000)||p.Has2480(0x4000000)) return std::nullopt;
    constexpr std::array<S,6> states{S::GrindFiftyFifty,S::GrindBoardslide,S::GrindTipslide,S::GrindFiveO,S::GrindBackslash,S::GrindDarkslide};
    return p.grind_type_1248<6 ? std::optional<S>(states[p.grind_type_1248]) : std::nullopt;
}
}
bool StateConditionOffGroundSkitching(BoardBodyState b,TwoStageThresholds t) {return b.field_856>t.field_856_primary||(b.field_856>t.field_856_secondary&&b.field_7692>t.field_7692);}
bool StateConditionOffGround(BoardBodyState b,TwoStageThresholds t) {return b.field_856>t.field_856_primary||(b.field_856>t.field_856_secondary&&b.field_7692>t.field_7692);}
bool StateIsSkateboardAnimated(SkeletonAnimationState s)
{
    if (s.mode_16420==2) return true;
    std::uint32_t bits;std::memcpy(&bits,&s.back_chain_lane_12656,4);const float magnitude=Float(bits&0x7fffffff);
    return magnitude<=s.threshold_800 ? false : s.mode_16420!=1;
}
bool StateSelector::Calculate(S current,const StateSelectionInput& input,S& result,std::string& error)
{
    if (!ParsePhysicalStateId(std::uint32_t(current))) {error="Unknown physical selector state "+std::to_string(std::uint32_t(current));return false;}
    result=CalculateValid(current,input);error.clear();return true;
}
S StateSelector::CalculateValid(S current,const StateSelectionInput& input)
{
    const auto p=input.processed;if (teleport_countdown>0) --teleport_countdown;
    current_state=current;revert_exited_normally=false;request_teleport=false;
    const bool colliding=p.wheel_contact_count_2556>0||p.Has2468(0x10000)||p.Has2468(0x20000);
    nonspecific_collision_free_frames=current==S::Nonspecific&&!colliding ? Increment(nonspecific_collision_free_frames) : 0;
    nonspecific_collision_frames=current==S::Nonspecific&&colliding ? Increment(nonspecific_collision_frames) : 0;
    two_wheel_counter=input.skateboard_contact_count_869>1 ? Increment(two_wheel_counter) : 0;
    three_wheel_counter=input.skateboard_contact_count_869>2 ? Increment(three_wheel_counter) : 0;
    something_colliding_frames=colliding ? Increment(something_colliding_frames) : 0;
    const bool special_grind=p.category_2512==400&&p.Has2468(0x400000);post_grind_jump_counter=special_grind ? 0 : Increment(post_grind_jump_counter);
    air_frames=p.category_2512==200 ? (p.Has2468(8) ? air_frames : Increment(air_frames)) : 0;
    skitch_exit_countdown=current==S::Skitching ? 10 : skitch_exit_countdown>0 ? skitch_exit_countdown-1 : 0;
    if (p.Has2468(2)||p.Has2472(0x40000)) return S::Teleporting;
    if (air_frames>300) {request_teleport=true;return current;}
    if (p.field_1776<0&&(std::uint32_t(p.field_1776)&0x2000000)==0&&teleport_countdown==0) return S::FollowPath;
    const Facts facts{colliding,p.Has2468(0x40000),p.Has2472(0x40),StateIsSkateboardAnimated(input.skeleton),StateConditionOffGround(input.board_body,input.normal_off_ground),StateConditionOffGroundSkitching(input.board_body,input.skitching_off_ground),CheckGrind(p)};
    switch (current)
    {
    case S::PhysicsGround:case S::SlideGround:case S::RevertGround:case S::GroundAnimation:case S::Skitching:case S::FollowPath:return SelectGround(current,input,facts);
    case S::PhysicsAir:return SelectPhysicsAir(current,input,facts);
    case S::KnownAir:return SelectKnownAir(current,input,facts);
    case S::PhysicsAirSecondary:return facts.wipeout ? S::WipeoutGround : !p.Has2484(0x100000) ? S::PhysicsAir : current;
    case S::WipeoutGround:case S::Sleeping:case S::Teleporting:return current;
    case S::GrindBoardslide:case S::GrindFiftyFifty:case S::GrindTipslide:case S::GrindFiveO:case S::GrindBackslash:case S::GrindDarkslide:return SelectGrind(input,facts);
    case S::BipedGround:case S::BipedAir:case S::OffBoardPushing:case S::LandingOnDeck:case S::HandPlant:case S::FootPlant:case S::Boneless:return SelectBipedPlant(current,input,facts);
    case S::Nonspecific:return SelectNonspecific(current,input,facts);
    }
    std::abort(); // Typed source enum is exhaustive; public entry validates it.
}
S StateSelector::SelectGround(S current,const StateSelectionInput& input,Facts f)
{
    const auto p=input.processed;
    switch (current)
    {
    case S::PhysicsGround:
        if (p.Has2480(0x1000)&&(!p.Has2480(0x400)||!p.Has2480(0x200))) return S::LandingOnDeck;
        if (p.Has2476(1)&&((p.Has2480(0x40000000)&&input.skateboard_contact_count_869<=2)||input.skateboard_contact_count_869==0)) return S::HandPlant;
        if (p.Has2476(0x8000)) return S::BipedGround;if (p.Has2476(0x80)) return S::BipedAir;if (f.wipeout) return S::WipeoutGround;
        if (p.field_2572==1) return p.AirVariant();if (p.field_2744!=0.0f) return S::RevertGround;if (f.grind) return *f.grind;
        if (!f.colliding&&f.off_ground&&teleport_countdown==0) return S::PhysicsAir;
        if (f.skateboard_animated&&teleport_countdown==0) return S::GroundAnimation;
        if (p.Has2476(0x200000)&&p.Has2480(0x400000)&&skitch_exit_countdown==0) return S::Skitching;
        return p.field_2732!=0.0f ? S::SlideGround : current;
    case S::SlideGround:
        if (f.wipeout) return S::WipeoutGround;if (p.field_2744!=0.0f) return S::RevertGround;if (f.grind) return *f.grind;
        if (!f.colliding&&f.off_ground) return S::PhysicsAir;return p.field_2732==0.0f ? S::PhysicsGround : current;
    case S::RevertGround:
        if (!f.colliding&&f.off_ground) return S::PhysicsAir;if (p.Has2468(0x10000)||p.Has2472(0x20000)) return S::PhysicsGround;
        if (!p.Has2472(0x200000)) {revert_exited_normally=true;return S::PhysicsGround;}return f.wipeout ? S::WipeoutGround : current;
    case S::GroundAnimation:
        if (f.wipeout) return S::WipeoutGround;if (p.Has2480(0x4000)) return S::Boneless;if (p.Has2476(0x8000)) return S::BipedGround;if (p.Has2476(0x80)) return S::BipedAir;if (p.field_2572==1) return p.AirVariant();
        if (!f.colliding&&f.off_ground) return S::PhysicsAir;return f.skateboard_animated ? current : S::PhysicsGround;
    case S::Skitching:
        if (!p.Has2476(0x200000)) return S::PhysicsGround;if (f.wipeout) return S::WipeoutGround;return f.off_ground_skitching&&teleport_countdown==0 ? S::PhysicsGround : current;
    case S::FollowPath:return (std::uint32_t(p.field_1776)&0x2000000)!=0 ? S::PhysicsGround : current;
    default:std::abort();
    }
}
S StateSelector::SelectPhysicsAir(S current,const StateSelectionInput& input,Facts f) const
{
    const auto p=input.processed;if (f.wipeout) return S::WipeoutGround;if (p.Has2476(0x8000)) return S::BipedGround;if (p.Has2476(0x80)&&!p.Has2484(0x01000000)) return S::BipedAir;
    if (f.force_known_air) {if (f.colliding||p.Has2468(0x8000)) return S::WipeoutGround;return p.Has2468(0x400) ? S::KnownAir : current;}
    if (p.state_timer_2664>Float(0x3da3d70a))
    {if (f.colliding) {if (p.Has2472(4)) return S::PhysicsAir;return f.skateboard_animated ? S::GroundAnimation : S::PhysicsGround;}if (post_grind_jump_counter>10&&f.grind) return *f.grind;}
    return p.Has2468(0x400) ? S::KnownAir : current;
}
S StateSelector::SelectKnownAir(S current,const StateSelectionInput& input,Facts f) const
{
    const auto p=input.processed;if (p.Has2480(0x2000000)) return S::FootPlant;
    if (p.trajectory_collision_time_2772<Float(0x3d4ccccd)&&(p.Has2476(0x80)||p.Has2476(0x8000))) return S::WipeoutGround;
    if (p.Has2476(0x80)&&!p.Has2484(0x01000000)) return S::BipedAir;if (p.Has2476(0x8000)) return S::BipedGround;if (f.wipeout) return S::WipeoutGround;
    if (f.force_known_air) return f.colliding||p.Has2468(0x8000) ? S::WipeoutGround : current;
    if (p.state_timer_2664>Float(0x3da3d70a)&&post_grind_jump_counter>10&&f.grind) return *f.grind;
    if (!f.colliding||p.state_timer_2664<Float(0x3d23d70a))
    {if (p.trajectory_collision_time_2772<Float(0xbe4ccccd)) return p.Has2476(0x4000000) ? S::KnownAir : S::PhysicsAir;if (p.Has2468(0x8000)) return p.Has2476(0x4000000) ? S::WipeoutGround : S::PhysicsAir;return current;}
    if (p.Has2472(4)) return S::PhysicsAir;if (p.Has2480(0x40000)||p.Has2480(0x20000)||p.Has2480(0x10000)) return S::WipeoutGround;
    return !p.Has2472(0x8000)&&!p.Has2472(0x4000) ? S::PhysicsGround : S::GroundAnimation;
}
S StateSelector::SelectGrind(const StateSelectionInput& input,Facts f) const
{
    const auto p=input.processed;if (f.wipeout) return S::WipeoutGround;if (p.Has2484(0x100000)) return S::PhysicsAirSecondary;if (p.Has2476(0x80)) return S::BipedAir;if (p.Has2476(0x8000)) return S::BipedGround;if (p.Has2468(0x100)) return p.AirVariant();return f.grind.value_or(S::Nonspecific);
}
S StateSelector::SelectBipedPlant(S current,const StateSelectionInput& input,Facts f) const
{
    const auto p=input.processed;
    switch (current)
    {
    case S::BipedGround:
        if (f.wipeout) return S::WipeoutGround;if (p.Has2484(0x10000)) return S::BipedAir;if (p.Has2476(0x200000)) return S::OffBoardPushing;if (p.Has2476(0x8000)||p.Has2480(0x40000)) return current;
        return !p.Has2484(1)&&!p.Has2488(0x10000000)&&!p.Has2488(0x80000000) ? S::PhysicsAir : S::PhysicsGround;
    case S::BipedAir:
        if (f.wipeout) return S::WipeoutGround;if (!p.Has2480(0x10)) {if (p.Has2484(0x10000)) return p.Has2476(0x8000)||p.Has2476(0x80) ? current : S::PhysicsAir;return S::BipedGround;}return S::LandingOnDeck;
    case S::OffBoardPushing:return f.wipeout ? S::WipeoutGround : !p.Has2476(0x200000) ? S::BipedGround : current;
    case S::LandingOnDeck:return f.wipeout ? S::WipeoutGround : p.Has2476(0x10000) ? S::PhysicsGround : p.Has2476(0x80) ? S::BipedAir : current;
    case S::HandPlant:return f.wipeout ? S::WipeoutGround : (f.colliding&&p.state_timer_2664>Float(0x3e4ccccd))||std::int32_t(p.flags_2480)>=0 ? S::PhysicsGround : current;
    case S::FootPlant:return f.wipeout ? S::WipeoutGround : !p.Has2480(0x01000000) ? p.AirVariant() : current;
    case S::Boneless:
        if (f.wipeout) return S::WipeoutGround;if (p.Has2468(0x400)) return S::KnownAir;if (p.Has2476(0x80)) return S::BipedAir;return !p.Has2480(0x4000)&&!p.Has2480(0x2000) ? S::PhysicsAir : current;
    default:std::abort();
    }
}
S StateSelector::SelectNonspecific(S current,const StateSelectionInput& input,Facts f) const
{
    const auto p=input.processed;if (p.Has2484(0x100000)) return S::PhysicsAirSecondary;if (f.wipeout) return S::WipeoutGround;if (p.Has2468(0x100)) return p.AirVariant();if (p.Has2468(0x400000)) return current;
    if (p.Has2472(8)) return p.Has2484(0x200000) ? S::WipeoutGround : S::PhysicsAir;if (p.Has2472(4)) return current;if (f.grind) return *f.grind;
    if ((p.grind_investigation_flags_1516&0x8000000)!=0) {if (three_wheel_counter>10) return S::PhysicsGround;}
    else if (two_wheel_counter>2) return f.skateboard_animated ? S::GroundAnimation : S::PhysicsGround;
    if (nonspecific_collision_free_frames>2) return S::PhysicsAir;
    return nonspecific_collision_frames>(p.Has2484(0x200000) ? 30 : 60) ? S::PhysicsGround : current;
}
}
