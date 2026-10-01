// SPDX-License-Identifier: Apache-2.0
#include "SessionMarkerRuntime.h"
#include "ClimbingMath.h"
#include "StockSettingsReader.h"
#include <algorithm>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
Vec3 XYZ(Vec4 value){return {value[0],value[1],value[2]};}
Vec4 Packed(Vec3 value){return {value.x,value.y,value.z,0};}
float Duration(float distance)
{
    if(distance<=100)return 0.2f;
    if(distance>=1000)return 1.0f;
    return std::fma(distance,Scalar(0x3a690453),Scalar(0x3de38e39));
}
}
SessionMarkerHoldStep SessionMarkerHold::Update(bool held,bool usable,float distance,bool ready)
{
    SessionMarkerHoldStep out;
    if(!held){elapsed=0;fired=false;}
    else if(!fired&&usable)
    {
        elapsed+=Scalar(0x3c888889);
        if(distance>0.5f && std::isfinite(distance))
        {
            const float duration=Duration(distance);
            if(ready&&elapsed>duration){fired=true;tail=3;out.relocate=true;}
            out.progress=std::clamp(elapsed/duration,0.0f,1.0f);
        }
    }
    if(tail>0){out.progress=1;--tail;}
    return out;
}
bool SessionMarkerValidation::Load(const SettingsDatabase& data,std::string& error)
{
    StockSettingsReader read(data);
    return read.Float("Hash_12B64C0E804B0853","default","Hash_ADD032CACF6A1C15",slope,error)
        &&read.Float("Hash_12B64C0E804B0853","default","Hash_8ABE098D3806D273",max_drop,error)
        &&read.Float("Hash_12B64C0E804B0853","default","Hash_C0526C883AF0ECCA",clearance_length,error)
        &&read.Float("Hash_12B64C0E804B0853","default","Hash_CEB092E418A5B001",clearance_radius,error);
}
bool SessionMarkerValidation::Check(const WorldGeometry& world,Vec4 position) const
{
    for(float value:position)if(!std::isfinite(value))return false;
    const Vec3 start{position[0],position[1]+0.1f,position[2]},end{start.x,start.y-10.0f,start.z};
    const auto query=world.QueryThinLine(start,end);
    if(query.error||!query.hit)return false;
    const auto& hit=*query.hit;const auto surface=(hit.tag>>7)&31;
    if(hit.geometry.normal.y<slope || start.y-hit.geometry.position.y>max_drop
        ||surface==5||surface==6||surface==9||surface==12||surface==13)return false;
    const Vec3 lower{start.x,start.y+clearance_radius,start.z},upper{lower.x,lower.y+clearance_length,lower.z};
    const auto clearance=world.QuerySweptLine(lower,upper,clearance_radius);
    return !clearance.error&&!clearance.hit;
}
bool SessionMarkerRuntime::Load(const SettingsDatabase& data,std::string& error)
{return validation.Load(data,error);}
void SessionMarkerRuntime::Suspend()
{hold.Cancel();blocked_until_release=true;ui_time=0;}
void SessionMarkerRuntime::Advance(const ControllerInputRuntime& input,GameplayRuntime& runtime)
{
    const auto actions=input.SessionMarkerActions();
    const bool modifier=actions[0],set=actions[1],held=actions[2];
    if(blocked_until_release){if(!modifier)blocked_until_release=false;return;}
    const auto& p=runtime.input->physical;
    const bool on_board=p.state.category_12!=500;
    const auto parts=runtime.physical->board.PartTransforms();
    const auto& deck=parts[std::size_t(BoardBodyId::Deck)];
    auto transform=runtime.physical->roots.animation_to_world;
    if(on_board)
    {
        for(std::size_t i=0;i<3;++i)for(std::size_t j=0;j<3;++j)transform[i][j]=deck.basis.columns[i][j];
        transform[3]={deck.translation.x,deck.translation.y+0.2f,deck.translation.z,0};
        const Vec3 velocity{Scalar(p.skateboard.vector_80[0]),Scalar(p.skateboard.vector_80[1]),Scalar(p.skateboard.vector_80[2])};
        if(climbing_math::Dot(velocity,velocity)>0.25f)
        {
            const auto right=climbing_math::Cross({0,1,0},climbing_math::Normalize(velocity));
            const auto forward=climbing_math::Cross(right,{0,1,0});
            if(climbing_math::Dot(forward,forward)>0.9f)
            {transform[0]=Packed(right);transform[1]={0,1,0,0};transform[2]=Packed(forward);}
        }
    }
    const auto state=p.state.state_16;
    const bool allowed=(p.state.category_12==100 && p.collision.wheel_count_0>=2
        &&state!=104&&deck.basis.columns[1][1]>0.71f)
        ||(p.state.category_12==500&&state==500);
    can_place=modifier&&allowed&&p.surface_default_mode!=8&&validation.Check(runtime.physical->world,transform[3]);
    can_return=marker&&marker->generation==0&&state!=104&&state!=502;
    visible=modifier;
    if(set&&last_batch!=input.consumed_batches&&can_place)
        marker=Marker{transform,on_board,runtime.animation->FootForward(),0};
    last_batch=input.consumed_batches;
    const bool ready=p.state.flag_69==0&&state!=702
        &&!(runtime.physical->board_wiping_out&&p.skeleton.teleport_pending_604!=0)
        &&!runtime.input->PendingTeleport();
    const float distance=marker ? climbing_math::Distance(XYZ(runtime.physical->roots.animation_to_world[3]),XYZ(marker->transform[3])) : 0;
    while(ui_time>=1.0/60.0)
    {
        ui_time-=1.0/60.0;
        const auto step=hold.Update(held,can_return,distance,ready);progress=step.progress;
        if(step.relocate&&marker)
        {
            std::string error;
            if(runtime.input->RequestTeleport(marker->transform,error))
            {
                runtime.animation->RestoreFootForward(marker->foot_forward);
                runtime.teleport->RequestManual(marker->transform,marker->on_board);
            }
            else hold.Cancel();
        }
    }
}
}
