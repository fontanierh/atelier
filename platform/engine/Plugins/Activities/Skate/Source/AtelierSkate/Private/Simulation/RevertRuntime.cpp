#include "RevertRuntime.h"
#include "RidingAngles.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Raw(const RawVector& words) {Vec4 value;std::memcpy(value.data(),words.data(),sizeof(value));return value;}
Vec3 Xyz(Vec4 v) {return {v[0],v[1],v[2]};}
float Dot(Vec4 a,Vec4 b) {return std::fma(a[2],b[2],std::fma(a[1],b[1],a[0]*b[0]));}
class Angle final:public ManualAngleMeasurement
{
    bool AngleBetween(Vec4 a,Vec4 b,Vec4 axis,float& output,std::string&) override
    {output=RidingSignedAngle(Xyz(a),Xyz(b),Xyz(axis));return true;}
};
}
void RevertRuntime::Enter(GroundPhaseOwners o)
{
    o.life.skeleton_elapsed_16505=true;
    o.physical.board.HookMut().drive.DisableAnimation(o.life.board_animated_290);
    direction=o.animation_input.extra.revert_direction;
    velocity={};elapsed=0;captured=false;active=true;
    o.wipeout.EnterGround();
}
bool RevertRuntime::Update(RevertOwners owners,const GroundSettings& settings,std::string& error)
{
    auto o=owners.ground;auto& physical=o.physical;auto& p=o.processed;
    if(!o.toolkit){error="Revert requires current BoardToolkit";return false;}
    if(!captured&&elapsed>=delay)
    {
        captured=true;velocity=Raw(p.vectors_400_416[0]);
        travel_sign=Dot(velocity,o.toolkit->deck[2])>0?-1.0f:1.0f;
    }
    std::int32_t wheel_count;std::memcpy(&wheel_count,&p.wheel_count_2556,4);
    physical.riding.UpdateSlideReckoning(*o.toolkit,
        {Xyz(Raw(p.animation_com_to_deck_752)),o.animation_input.extra.physical_body_spin},
        p.flags_2468,o.animation_input.fields.balance,(p.flags_2476&0x40000000)!=0,
        {Xyz(Raw(p.vectors_464_480_496_512_528[0])),Xyz(Raw(p.vectors_464_480_496_512_528[4])),
         p.scalar_2652,p.scalar_2616,wheel_count});
    if(!UpdateGroundSkeletonInput(o,owners.skeleton_input,owners.skeleton_air,owners.hierarchy,error))return false;
    // UpdateGround may modify processed fields; read the same current owners
    // again before pumping, input preparation and the captured-heading force.
    if(!o.toolkit){error="Revert requires current BoardToolkit";return false;}
    const auto& toolkit=*o.toolkit;
    if(!UpdatePhysicalRevertPumping(o.ground.pumping,o.ground.pumping_settings,toolkit,
        physical.riding,physical.animation_record,p,o.animation_input.fields.balance,error))return false;
    GroundPumpingMode mode;if(!o.ground.pumping_settings.Mode(p.state_variant_index_2528,mode,error))return false;
    const auto input=PrepareGroundBoardInput(settings,toolkit,p,o.animation_input.fields,o.animation_input.contacts,
        o.ground.pumping,mode.unintentional_scalar,physical.riding,o.animated.board_at_y_delta,
        physical.settings.board.step.base_truck_transforms,
        {o.life.manual_drag_2724,p.external_physics_1616.flags,0,{}});
    const auto board_settings=settings.Board();
    const auto correction=Correction(toolkit.deck[2],Raw(p.vectors_464_480_496_512_528[0]),
        Raw(p.vectors_720_784_800_816_832_864[0]));
    for(auto& body:physical.board.BodiesMut())body.inertia.linear_drag=0;
    const auto anti_flip=CalculateAntiFlip(board_settings.anti_flip,input.anti_flip);
    const auto pump=CalculatePumpForce(input.pump_force);
    Angle geometry;ManualError detail;
    const auto manual=CalculateManual(o.ground.manual,board_settings.manual,board_settings.manual_mode,
        input.manual,geometry,detail);
    if(!manual)
    {
        error=detail.kind==ManualError::Kind::Angle?"Revert manual: Angle(IntegerConversionUnavailable)"
            :"Revert manual: unexpected measurement failure";
        return false;
    }
    for(const auto value:{correction,manual->angular_displacement,anti_flip})
        o.runtime.ApplyAngularDisplacement(physical.board,value);
    physical.board.ForcesMut().Append({8,{pump[0],pump[1],pump[2]},{pump[4],pump[5],pump[6]}});
    elapsed+=p.timestep_2604;if(elapsed>duration)active=false;
    error.clear();return true;
}
}
