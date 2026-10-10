#include "GroundStateRuntime.h"
#include "StockSettingsReader.h"
#include "AirMath.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
Vec4 Vector(const RawVector& words)
{return {Float(words[0]),Float(words[1]),Float(words[2]),Float(words[3])};}
class ManualBodies final:public ManualGroundBodies
{
public:
    explicit ManualBodies(BoardRuntime& value):board(value){}
    BoardRuntime& board;
    Vec4 LinearVelocity(std::size_t i) override
    {const auto v=board.Bodies()[i].rates.linear_velocity;return {v.x,v.y,v.z,0};}
    void SetLinearVelocity(std::size_t i,Vec4 v) override
    {board.BodiesMut()[i].rates.linear_velocity={v[0],v[1],v[2]};}
};
class Projection final:public ManualGroundProjection
{
public:
    bool NormalSpeed(Vec4 n,Vec4 v,float& output,std::string&) override
    {output=Dot3(n,v);return true;}
};
}
bool GroundEntrySettings::Load(const SettingsDatabase& data,std::string& error)
{
    StockSettingsReader reader(data);GroundEntrySettings value{};
    if (!reader.Float("physicsdeck","default","DeckAngularDrag",value.deck_angular_drag,error)) return false;
    value.deck_angular_drag*=Float(0x426fffff);
    if (!reader.Float("physics_manual","default","PowerslideExitScalar",value.powerslide_exit,error)
        ||!reader.Float("physics_feet","default","LandingOnDeckEffectScalar",value.landing_strength,error)
        ||!reader.Float("physics_feet","default","LandingOnDeckOffset",value.landing_offset,error)) return false;
    *this=value;return true;
}
bool GroundStateRuntime::Load(const SettingsDatabase& data,bool human,std::string& error)
{
    GroundStateRuntime value{};value.state=PhysicsGroundState::BeforeFirstEnter(human);
    StockSettingsReader reader(data);
    if (!value.pumping_settings.Load(data,error)
        ||!reader.Float("physics_push","default","MaxPushableSpeed_CameraDelta",value.output_settings.pushable_speed_terms_4_8[0],error)
        ||!reader.Float("physics_push","default","MaxPushableSpeed",value.output_settings.pushable_speed_terms_4_8[1],error)
        ||!reader.Float("physics_push","default","Hash_501D5581043D7D3C",value.output_settings.mode_speed_threshold_0,error)
        ||!value.entry_settings.Load(data,error)) return false;
    constexpr std::array<std::string_view,5> modes{{"easy","normal","hardcore","motorized","test"}};
    for (std::size_t i=0;i<modes.size();++i)
        if (!reader.Boolean("physics_mode",modes[i],"AutoPushEnabled",value.auto_push_enabled[i],error)) return false;
    *this=std::move(value);return true;
}
GroundControllers GroundStateRuntime::Controllers()
{return {wobble,steering,speed,manual,heading_previous};}
PhysicsGroundOutput GroundStateRuntime::Output(const ProcessedPhysicsInput& p,const PhysicsAnimationInput& a,const BoardToolkit& t) const
{
    // Original indexing is a panic contract, not a profile fallback.
    if (p.state_variant_index_2528>=auto_push_enabled.size()) std::abort();
    return FillGroundPhysicsOutput(state,{Vector(p.vectors_464_480_496_512_528[0]),
        Vector(p.vectors_544_560_592_608[3]),t.absolute_speed,p.scalar_2652,p.state_timer_2664,
        a.fields.balance,p.flags_2476,p.flags_2484,auto_push_enabled[p.state_variant_index_2528]},output_settings);
}
bool GroundStateRuntime::Enter(BoardRuntime& board,const ProcessedPhysicsInput& p,const PhysicsAnimationInput& a,
    const BoardToolkit& toolkit,GroundEntryTargets targets,std::string& error)
{
    targets.board_flags_8384&=0x7f;
    board.BodiesMut()[6].inertia.angular_drag=entry_settings.deck_angular_drag;
    board.SetCollisionGroup(4);
    targets.foot_ik.EnableFeet(true);
    targets.skeleton_elapsed_16505=false;
    if (!targets.services.SetSkeletonCollisionState(6,error)) return false;
    state.BeginEntry();
    targets.reckoning_spin_angle=0;targets.reckoning_spin_speed=0;
    board.HookMut().drive.DisableAnimation(targets.board_animated_290);
    const auto normal=Vector(p.vectors_464_480_496_512_528[0]);
    board.BodiesMut()[6].rates.angular_velocity=GroundEntryAngularVelocity(normal,Vector(p.vectors_720_784_800_816_832_864[0]));
    speed.target_speed=GroundEntryTargetSpeed(board.Bodies()[6].rates.linear_velocity,normal,toolkit.forward);
    wobble.Reset();ManualBodies bodies(board);Projection projection;
    // The direct body projection service is infallible, as in the source.
    if (!EnterManualGround(manual,p.category_2516,entry_settings.powerslide_exit,
        {a.fields.balance,normal,p.flags_2468,p.flags_2472},bodies,projection,error)) return false;
    if (p.category_2516==200)
    {
        const bool stance=(((p.flags_2468>>20)^(p.flags_2476>>2))&1)!=0;
        if (!targets.services.EnterAirLandingModifier(stance,error)) return false;
    }
    if (p.state_2504==503)
        board.ForcesMut().Append(GroundLandingOnDeckForce(Vector(p.vectors_400_416[0]),
            Vector(p.vectors_544_560_592_608[3]),Vector(p.vectors_544_560_592_608[0]),
            toolkit.total_mass,entry_settings.landing_strength,entry_settings.landing_offset));
    state.straighten_scale_2672=p.state_2504==101?Float(0x3e23d70a):1.0f;
    pumping.Reset();
    if (targets.wipeout_mode!=1) {targets.wipeout_timer=0;targets.wipeout_mode=1;}
    state.FinishEntry(p.state_2504);entered=true;error.clear();return true;
}
void GroundStateRuntime::Exit(GroundRuntime& runtime,PhysicalSimulationRuntime& physical,const ProcessedPhysicsInput& p)
{
    state.steering_damped_turn_2644=0;state.steering_push_scalar_2640=1;pumping.Reset();
    for(auto& body:physical.board.BodiesMut())body.inertia.linear_drag=0;
    physical.settings.board.collision.wheel_material=physical.settings.board.standard_wheel_material;
    if(state.flag_2708)
    {
        const Vec4 gravity{0,p.gravity_2648,0,0};Vec4 reference;
        for(unsigned i=0;i<4;++i)reference[i]=std::fma(gravity[i],p.timestep_2604,state.vector_2688[i]);
        runtime.SetAnimatedVelocity(physical.board,ClampAirJumpVelocity(reference,Vector(p.vectors_400_416[0])));
    }
}
std::optional<GroundBoardOutcome> GroundStateRuntime::Update(GroundRuntime& runtime,BoardRuntime& board,
    const WorldGeometry& world,const GroundSettings& settings,GroundUpdateFrame frame,GroundPhysicalFrame physical,
    GroundUpdateTargets targets,GroundUpdateError& error)
{
    if (!entered)
    {error.stage=GroundUpdateError::Stage::BeforeEntry;error.source="Ground::Enter must finish before Ground::Update";return std::nullopt;}
    const auto& p=frame.processed;
    // Preserve the source's wrapping u32-to-i32 cast without implementation
    // defined signed conversion at out-of-range values.
    std::int32_t wheel_count;std::memcpy(&wheel_count,&p.wheel_count_2556,4);
    if (state.BeginUpdate(wheel_count,frame.toolkit.deck[3])) targets.skeleton_elapsed_16505=true;
    GroundPumpingMode mode;
    if (!pumping_settings.Mode(p.state_variant_index_2528,mode,error.source))
    {error.stage=GroundUpdateError::Stage::Pumping;return std::nullopt;}
    UpdatePhysicalGroundPumping(pumping,pumping_settings,mode,frame.toolkit,frame.riding,
        frame.skeleton_record,frame.board_frames,p.flags_2476);
    const auto input=PrepareGroundBoardInput(settings,frame.toolkit,p,frame.animation.fields,
        frame.animation.contacts,pumping,mode.unintentional_scalar,frame.riding,frame.skeleton.board_at_y_delta,
        frame.base_trucks,frame.extra);
    auto outcome=runtime.UpdateBoard(board,world,settings,state,Controllers(),input,physical,error.board);
    if (!outcome) {error.stage=GroundUpdateError::Stage::Board;return std::nullopt;}
    const auto delta=GroundFutureDeckDisplacement(board.Forces(),frame.toolkit.total_mass,p.timestep_2604,
        Vector(p.vectors_464_480_496_512_528[0]),state.flag_2720,state.manual_correction_2732);
    if (delta&&!targets.services.MoveFutureDeck(*delta,error.source))
    {error.stage=GroundUpdateError::Stage::MoveFutureDeck;return std::nullopt;}
    if (state.flag_2722) targets.foot_ik.contacts.support_failed_this_update=true;
    targets.board_correction_pending=true;
    state.FinishUpdate(p.timestep_2604);
    targets.services.InvalidateOffboardGrab();return outcome;
}
}
