// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionFeedbackOperations.h"
#include "GraphMotionName.h"
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float f;std::memcpy(&f,&word,4);return f;}
constexpr std::array<std::string_view,5> PumpNames{"PUMP0","PUMP1","PUMP2","PUMP3","PUMP4"};
}
bool ParseGraphMotionFeedbackOperation(const GraphAttributes& attributes,GraphMotionFeedbackOperation& output,bool& recognized,std::string& error)
{
    recognized=false;const auto raw=attributes.Text("name");if (!raw) {error="MotionGraph operation has no name";return false;}const auto name=TrimMotionGraphName(*raw);GraphMotionFeedbackOperation op;using K=GraphMotionFeedbackOperation::Kind;
    const auto key=[&](std::string_view field,std::string_view fallback){return EncodeAnimationName(attributes.Text(field).value_or(fallback));};
    if (name=="SetTurning") {op.kind=K::Turning;op.names={key("angleName","angle"),key("dirName","dir"),key("quicknessName","quickness"),key("speedName","speedtuck"),key("holdingName","holding")};}
    else if (name=="Crouching") {op.kind=K::Crouching;op.names[0]=key("crouchName","");}
    else if (name=="SettingBodyTilt") {op.kind=K::BodyTilt;op.names[0]=key("tilt_x","tilt_x");}
    else if (name=="UpdateRidingFakie") {op.kind=K::Fakie;op.fakie={Float(attributes.FloatBits("highSpeedThreshold",0x3f800000)),Float(attributes.FloatBits("lowSpeedThreshold",0x3f000000)),Float(attributes.FloatBits("timeSlowlyRollingBackwardsThreshold",0x3e4ccccd)),Float(attributes.FloatBits("timeFromTeleportThreshold",0x40400000))};}
    else if (name=="Pumping") op.kind=K::Pumping;
    else if (name=="DisallowPumping") op.kind=K::DisallowPumping;
    else if (name=="SetDeckPitchAndYaw") {op.kind=K::DeckPitchYaw;op.names[0]=key("skateyaw","skateyaw");op.names[1]=key("skatepitch","skatepitch");}
    else {error.clear();return true;}
    output=std::move(op);recognized=true;error.clear();return true;
}
GraphMotionFeedbackInstance CreateGraphMotionFeedbackInstance(const GraphMotionFeedbackOperation& op)
{
    using K=GraphMotionFeedbackOperation::Kind;switch (op.kind) {case K::Turning:return SetTurningState{};case K::Crouching:return std::optional<AnimationCrouchingState>{};case K::BodyTilt:return AnimationBodyTiltState{};case K::Fakie:return AnimationFakieState{};case K::Pumping:return AnimationPumpState{};default:return std::monostate{};}
}
bool LoadGraphMotionFeedbackSettings(const SettingsDatabase& data,GraphMotionFeedbackSettings& output,std::string& error)
{
    GraphMotionFeedbackSettings settings;if (!LoadAnimationTurningSettings(data,settings.turning,error)||!LoadAnimationCrouchingSettings(data,settings.crouching,error)||!LoadAnimationBodyTiltSettings(data,settings.body_tilt,error)||!LoadAnimationPumpSettings(data,settings.pumping,error)) return false;output=std::move(settings);error.clear();return true;
}
bool ExecuteGraphMotionFeedbackOperation(const GraphMotionFeedbackOperation& op,GraphMotionFeedbackInstance& instance,std::uint8_t phase,const graph::Frame& frame,GraphMotionFeedbackContext& context,std::string& error)
{
    const auto set=[&](AttributeName name,float value){context.animation.SetAttribute({name,value,false,-1});};
    using K=GraphMotionFeedbackOperation::Kind;switch (op.kind)
    {
    case K::Turning:
    {
        auto* state=std::get_if<SetTurningState>(&instance);if (!state) {error="SetTurning instance was not allocated";return false;}
        if (phase==0) state->Enter();
        else if (phase==1)
        {
            if (!context.turning) {error="SetTurning requires actual PhysOutAnimation and stance outputs";return false;}
            const auto flags=context.animation.tree.skater_animation_flags;if (!flags) {error="SetTurning requires actual animation stance flags";return false;}
            UpdateSetTurning(*state,context.slide_latch,*context.turning,{(*flags&0x20000000)!=0,(*flags&0x40000000)!=0},frame.dt,context.settings.turning,
                {context.animation.MotionIntent("FakieTurn"),context.animation.MotionIntent("LeftSlide"),context.animation.MotionIntent("RightSlide")},
                [&](TurningAttribute attribute,float value)
                {
                    const auto ordinal=std::uint32_t(attribute);if (ordinal<5) set(op.names[ordinal],value);else context.animation.EmitPacket(EncodeAnimationName(attribute==TurningAttribute::Turn?"Turn":"Slide"),value);
                });
        }break;
    }
    case K::Crouching:
    {
        auto* state=std::get_if<std::optional<AnimationCrouchingState>>(&instance);if (!state) {error="Crouching instance was not allocated";return false;}
        if (phase==0) {if (!context.crouching) {error="Crouching Begin requires real physical height and speed";return false;}*state=AnimationCrouchingState::Begin(*context.crouching,context.settings.crouching);}
        else if (phase==1)
        {
            if (!*state) {error="Crouching updated before Begin";return false;}if (!context.crouching) {error="Crouching requires actual physical outputs";return false;}
            const AnimationCrouchingIntents intents{context.animation.MotionIntent("AutoPumpAngle"),context.animation.MotionIntent("AutoPumpMag"),context.animation.MotionIntent("Crouch"),context.animation.MotionIntent("HardTurnCrouch"),context.animation.MotionIntent("Manual"),context.is_power_sliding};
            const auto result=state->value().Update(*context.crouching,intents,frame.dt,context.settings.crouching);if (result.new_auto_pump) context.animation.EmitPacket(EncodeAnimationName("NewAutoPump"),1);if (result.player_controlled_pump) context.animation.EmitPacket(EncodeAnimationName("PlayerControlledPump"),1);set(op.names[0],result.height);
        }break;
    }
    case K::BodyTilt:
    {
        auto* state=std::get_if<AnimationBodyTiltState>(&instance);if (!state) {error="SettingBodyTilt instance was not allocated";return false;}
        if (phase==1&&context.applying_body_tilt)
        {
            if (!context.mirrored) {error="SettingBodyTilt needs actual mirrored stance";return false;}if (!context.body_tilt) {error="SettingBodyTilt needs actual PhysOut tilt and spin";return false;}
            if (const auto value=state->Update(true,*context.mirrored,*context.body_tilt,context.settings.body_tilt)) set(op.names[0],*value);
        }else if (phase==1) state->Disable();break;
    }
    case K::Fakie:
    {
        auto* state=std::get_if<AnimationFakieState>(&instance);if (!state) {error="UpdateRidingFakie instance was not allocated";return false;}
        if (phase==1)
        {
            if (!context.fakie) {error="UpdateRidingFakie requires actual physical outputs";return false;}auto physical=*context.fakie;physical.doing_trick=context.doing_trick;
            if (const auto fakie=state->Update(physical,frame.dt,op.fakie)) {auto& flags=context.animation.tree.skater_animation_flags;if (!flags) {error="UpdateRidingFakie requires actual animation flags";return false;}*flags=(*flags&~std::uint32_t(0x20000000))|(*fakie?0x20000000:0);}
        }break;
    }
    case K::Pumping:
    {
        auto* state=std::get_if<AnimationPumpState>(&instance);if (!state) {error="Pumping instance was not allocated";return false;}
        if (phase==2) {for (const auto name:PumpNames) context.animation.channels.End(name);}
        else if (phase==1&&context.owner.allow_pumping)
        {
            if (!context.pumping_acceleration) {error="Pumping requires actual ground pumping acceleration";return false;}std::array<bool,5> occupied;for (std::size_t i=0;i<PumpNames.size();++i) occupied[i]=context.animation.channels.Has(PumpNames[i]);
            const auto update=state->Update(*context.pumping_acceleration,occupied,context.settings.pumping);
            if (update.start) {bool created;const ChannelSettings settings{0,false,false,1,context.settings.pumping.blend_in,false,context.settings.pumping.blend_out,true,false};if (!context.animation.NewChannel(PumpNames[*update.start],"B_PUMP",settings,created,error)) return false;}
            if (update.influence) context.animation.channels.Influence(PumpNames[update.influence->first],update.influence->second);
        }break;
    }
    case K::DisallowPumping:
        if (phase==0) {for (const auto name:PumpNames) context.animation.channels.EndWith(name,Float(0x3dcccccd),false);context.owner.allow_pumping=false;}else if (phase==2) context.owner.allow_pumping=true;break;
    case K::DeckPitchYaw:
        if (phase==0) {if (!context.deck_yaw_pitch) {error="SetDeckPitchAndYaw requires completed Skeleton output";return false;}set(op.names[0],(*context.deck_yaw_pitch)[0]);set(op.names[1],(*context.deck_yaw_pitch)[1]);}break;
    case K::Unsupported:error="Unsupported MotionGraph feedback operation";return false;
    }
    error.clear();return true;
}
}
