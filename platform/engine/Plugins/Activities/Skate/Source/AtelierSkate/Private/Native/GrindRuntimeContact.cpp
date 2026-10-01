// SPDX-License-Identifier: Apache-2.0
#include "GrindRuntimeInternal.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace grind_detail;
namespace
{
enum class Kind{Orient,Translate,Pin,Friction,Coping,ExitLean,Wheels,Align,TipStability};
struct Op{Kind kind;std::array<float,3> values{};};
}
bool GrindRuntime::Contact(GrindRuntimeOwners o,const PlayerGrindObservation& manager,std::string& error)
{
    if(!active){error="Grind contact requires active family";return false;}
    if(!o.input.toolkit){error="Grind contact requires board toolkit";return false;}
    const auto family=*active;const auto toolkit=*o.input.toolkit;const auto board_frame=toolkit.deck;const auto& p=o.input.processed;
    const auto velocity=FloatVector(p.vectors_400_416[0]);auto state=states[std::size_t(family)];
    const auto position=board_frame[3],normal=state.normal,across=state.across,direction=state.direction;
    auto& board=o.physical.board;std::vector<Op> operations;
    using K=Kind;
    switch(family){
    case PlayerGrindFamily::Darkslide:case PlayerGrindFamily::Boardslide:
        operations={{K::Orient},{K::Translate},{K::Pin},{K::Friction,{55,55,60}},{K::Coping},{K::ExitLean},{K::Wheels}};break;
    case PlayerGrindFamily::FiftyFifty:
        operations={{K::Friction,{50,40,40}},{K::Align,{800,0,0.07f}},{K::Coping},{K::Pin},{K::ExitLean},{K::Orient}};break;
    case PlayerGrindFamily::Tipslide:
        operations={{K::Orient},{K::TipStability},{K::Friction,{60,60,60}},{K::Coping},{K::Pin},{K::ExitLean},{K::Wheels}};break;
    case PlayerGrindFamily::FiveO:
        operations={{K::Orient},{K::Align,{3000,0.234f,0.07f}},{K::Pin},{K::Friction,{50,40,40}},{K::Coping},{K::ExitLean}};break;
    case PlayerGrindFamily::Backslash:
        operations={{K::Orient},{K::Align,{3000,0.39f,0.025f}},{K::Friction,{70,80,80}},{K::Coping},{K::Pin},{K::ExitLean},{K::Wheels}};break;
    }
    for(const auto operation:operations){switch(operation.kind){
    case K::Orient:{
        GrindOrientationTarget target;if(!GrindTargetOrientation(std::uint32_t(family),{board_frame,direction,normal,manager.geometry.point_1120,p.grind.yaw_1504,p.grind.pitch_1508,(p.flags_2468&0x00100000)!=0},target,error))return false;
        auto target_frame=GrindBlendOrientation(board_frame,target.frame);
        if(target.noise_amount>0){const std::array<std::uint32_t,3> draws{orientation_random.Next(),orientation_random.Next(),orientation_random.Next()};
            target_frame=ApplyGrindOrientationNoise(target_frame,p.scalar_2652,target.noise_amount,draws);}
        state.frame=target_frame;board.SetHookTransform(Transform(state.frame));board.HookMut().drive.EnableAngularOnly(o.life.board_animated_290);
        if(family==PlayerGrindFamily::FiveO||family==PlayerGrindFamily::FiftyFifty)ApplyGrindWorldForce(board,GrindTruckCompensation(normal,p.grind.pitch_1508),position);
        break;}
    case K::Friction:{
        const auto force=GrindFriction(velocity,normal,manager.geometry.upmost_normal_1408,manager.surface.friction_vs_time_1496,(manager.geometry.flags_1476&0x40000000)!=0,
            GrindMaterialMultiplier(manager.surface.material_1472),manager.geometry.kind_1464,operation.values);
        if(GrindFrictionApplies(velocity,normal))ApplyGrindWorldForce(board,force,position);break;}
    case K::Align:{
        const float slope=GrindPinSlope(normal,manager.geometry.upmost_normal_1408,manager.surface.gravity_relief_1512,settings.pin_vs_slope);
        const auto force=GrindLateralPin(board_frame,manager.geometry.point_1120,across,velocity,operation.values[0],operation.values[1],operation.values[2],(manager.control.flags_1516&0x20000000)!=0,slope);
        if(force)ApplyGrindWorldForce(board,*force,board_frame[3]);break;}
    case K::Pin:{const auto force=GrindSupportPin(normal,manager.surface.gravity_relief_1512);if(force)ApplyGrindWorldForce(board,*force,position);break;}
    case K::Coping:{const auto force=GrindSupportCoping(manager.geometry.upmost_normal_1408,velocity,manager.surface.gravity_relief_1512);if(force)ApplyGrindWorldForce(board,*force,position);break;}
    case K::ExitLean:{const auto force=GrindSupportExitLean(manager.geometry.high_side_1440,manager.surface.reckon_blend_selector_1500,settings.exit_assist);if(force)ApplyGrindWorldForce(board,*force,position);break;}
    case K::Wheels:{std::array<bool,4> contact;for(std::size_t i=0;i<4;++i)contact[i]=o.physical.riding.ground.parts[i].in_contact;GrindManageWheelSpin(board,contact);break;}
    case K::Translate:{
        state.preparing_jump|=(p.flags_2468&0x00200000)!=0;
        const auto forces=GrindSlideControl(family==PlayerGrindFamily::Darkslide,{position,manager.geometry.point_1120,direction,across,velocity,manager.control.translation_2796,
            toolkit.total_mass,o.physical.settings.board.step.simulation.frequency,state.preparing_jump,manager.geometry.kind_1464});
        for(const auto force:forces)ApplyGrindWorldForce(board,force,position);break;}
    case K::TipStability:{
        const auto offset=Sub(position,manager.geometry.point_1120);const auto inward=Scale(across,Dot3(across,offset)>0?-1.0f:1.0f);
        const float amount=(manager.control.flags_1516&0x02000000)?39.0f:(Dot3(normal,Cross(direction,offset))>0?manager.control.balance_2800:-manager.control.balance_2800)*37.0f;
        ApplyGrindWorldForce(board,Scale(inward,amount),position);break;}
    }}
    if(family==PlayerGrindFamily::Darkslide){
        if(manager.geometry.kind_1464==2)state.classification_104=Dot3(manager.geometry.high_side_1440,toolkit.effective[2])>0?2:1;
        else{const auto perpendicular=Scale(across,Dot3(Sub(position,manager.geometry.point_1120),across));state.classification_104=Dot3(perpendicular,toolkit.effective[2])>0?1:2;}
    }
    states[std::size_t(family)]=state;return true;
}
bool GrindRuntime::Involuntary(GrindRuntimeOwners o,const PlayerGrindObservation& manager,std::string& error)
{
    if(!active){error="Grind exit requires active family";return false;}
    if(!o.input.toolkit){error="Grind exit requires BoardToolkit";return false;}
    const auto family=*active;const auto frame=o.input.toolkit->deck;auto& state=states[std::size_t(family)];const auto kind=manager.geometry.kind_1464;auto& board=o.physical.board;
    GrindReleaseInput input{frame[3],manager.geometry.point_1120,state.across,state.normal,FloatVector(o.input.processed.vectors_400_416[0]),kind,manager.geometry.high_side_1440,false,true,100,1,125};
    const auto release=[&](){const auto force=GrindReleaseForce(input);if(force)ApplyGrindWorldForce(board,*force,input.position);};
    switch(family){
    case PlayerGrindFamily::Boardslide:case PlayerGrindFamily::Darkslide:
        if(kind==2){input.strength=90;input.speed_limit=0.75f;input.enable_lift=false;release();}
        else{state.slide_wipeout=true;state.slide_impulse=Scale(manager.geometry.direction_1136,136);o.wipeout.Request(10,0);}
        GrindClearWheelSpin(board);break;
    case PlayerGrindFamily::FiftyFifty:if(kind>=2){input.strength=10;input.lift=0;}release();break;
    case PlayerGrindFamily::FiveO:
        input.strength=kind<2?120.0f:10.0f;input.lift=kind<2?125.0f:0.0f;input.speed_limit=0.9f;input.force_across=kind==1&&std::fabs(Dot3(frame[2],input.across))>0.23f;release();break;
    case PlayerGrindFamily::Backslash:
        input.speed_limit=0.75f;input.force_across=kind==1;input.enable_lift=kind==1;release();GrindClearWheelSpin(board);break;
    case PlayerGrindFamily::Tipslide:
        GrindClearWheelSpin(board);
        if((manager.geometry.flags_1476&0x08000000)||state.tipslide_97_98_99[0]){
            if(!state.tipslide_97_98_99[0]){board.HookMut().drive.DisableAnimation(o.life.board_animated_290);state.tipslide_97_98_99[0]=true;state.tipslide_97_98_99[2]=true;}
            const auto offset=Sub(input.position,input.point);const auto inward=Scale(input.across,Dot3(input.across,offset)>0?-1.0f:1.0f);
            const float angle=45.0f*Float(0x3c8efa35);const auto sincos=SinCos(angle);Vec4 force;
            for(std::size_t i=0;i<4;++i)force[i]=(inward[i]*100.0f)*sincos.second;force[1]-=sincos.first;ApplyGrindWorldForce(board,force,input.position);
        }else{
            board.HookMut().drive.EnableAngularOnly(o.life.board_animated_290);input.speed_limit=1.5f;input.force_across=true;input.enable_lift=false;release();
            state.tipslide_97_98_99[1]=true;if(manager.control.flags_2488&0x10000000)state.tipslide_97_98_99[2]=true;
        }break;
    }
    return true;
}
}
