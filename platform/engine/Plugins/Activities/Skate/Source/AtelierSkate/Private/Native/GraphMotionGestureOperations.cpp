// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionGestureOperations.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
constexpr std::array<std::string_view,3> Channels{{"GestureBoth","GestureRight","GestureLeft"}};
constexpr std::array<std::string_view,37> Catalog{{
    "B_GSTR_AIRGUITAR","B_GSTR_AIRPLANE","B_GSTR_BOXING","B_GSTR_BRUCE_LEE","B_GSTR_CHECKTIME","B_GSTR_DEVIL",
    "B_GSTR_DBLE_GUN","B_GSTR_DUNNO","B_GSTR_FINGERWAG","B_GSTR_FISTS","B_GSTR_BICEPFLEX","B_GSTR_FLIPTABLE",
    "B_GSTR_FONZ_EH","B_GSTR_FREEDOM","B_GSTR_FU_FIST","B_GSTR_GETAWAY","B_GSTR_GETOUTTAHERE","B_GSTR_HANDCUFFS",
    "B_GSTR_HIGHPUMP","B_GSTR_LOWPUMP","B_GSTR_PREWIND","B_GSTR_PEACE","B_GSTR_POINT","B_GSTR_RAISEROOF",
    "B_GSTR_SHAKA","B_GSTR_SHRUG","B_GSTR_POINT_SKY","B_GSTR_SNAP","B_GSTR_SOULARCH","B_GSTR_SPOCK",
    "B_GSTR_SURFSUP","B_GSTR_SWINGHIGH","B_GSTR_SWINGLOW","B_GSTR_THROWARMS","B_GSTR_THMB_DWN","B_GSTR_WINGS","B_GSTR_YARDSALE"}};
float Float(std::uint32_t bits) {float v;std::memcpy(&v,&bits,4);return v;}
float Tenth() {return Float(0x3dcccccd);}
void EndAll(MotionAnimation& a) {for (auto i:{2,1,0}) a.channels.End(Channels[i]);}
ChannelSettings GestureSettings(bool keep,bool hold_in) {return {0,keep,false,1,Tenth(),hold_in,Tenth(),true,false};}
std::int32_t SelectStart(const IntentMap& intents)
{
    constexpr std::array<std::pair<std::int32_t,std::string_view>,4> names{{{3,"GestureDownStart"},{0,"GestureLeftStart"},{2,"GestureUpStart"},{1,"GestureRightStart"}}};
    for (auto [direction,name]:names) if (intents.Contains(name)) return direction;return -1;
}
std::int32_t SelectHands(const MotionAnimation& a,const MotionGraphCharacterGestureInputs& input)
{
    for (auto n:{"RetrieveBoard","Shove","WipeoutPushOff"}) if (a.channels.Has(n)) return -1;
    if (input.motion_intents.Contains("OB_Mount") || input.motion_intents.Contains("OB_Dismount")) return -1;
    if ((input.filtered_state==6 || input.filtered_state==7) && !input.ground321) return input.board_held311?2:0;
    const auto left=input.busy_hands[0]!=0,right=input.busy_hands[1]!=0;if (!left&&!right) return 0;if (!left&&right) return 1;if (left&&!right) return 2;return -1;
}
bool Selection(std::int32_t direction,std::optional<std::array<std::uint32_t,4>> selections,std::uint32_t& output,std::string& error)
{
    std::int32_t index;switch (direction) {case 0:index=2;break;case 1:index=3;break;case 2:index=0;break;case 3:index=1;break;default:output=37;return true;}
    if (!selections) {error="CharacterGesture needs the actual skater gesture selections";return false;}output=(*selections)[index];return true;
}
bool AnimationName(std::int32_t direction,std::int32_t hands,std::int32_t stage,std::optional<std::array<std::uint32_t,4>> selections,std::string& name,std::string& error)
{
    std::uint32_t id;if (!Selection(direction,selections,id,error)) return false;if (id>=Catalog.size()) {error="Invalid stock gesture selection "+std::to_string(id);return false;}
    constexpr std::array<std::string_view,3> hand_names{{"BOTH","RIGHT","LEFT"}},stage_names{{"INTO","CYC","OUT"}};
    name=std::string(Catalog[id])+"_"+std::string(hand_names[hands])+"_"+std::string(stage_names[stage]);return true;
}
void Set(MotionAnimation& a,std::string_view name,float value) {a.SetAttribute({EncodeAnimationName(name),value,false,-1});}
bool StartShoveChannel(MotionAnimation& a,std::string_view channel,std::string_view tree,bool anticipation,std::string& error)
{
    const auto seconds=Float(anticipation?0x3e4ccccd:0x3dcccccd);const ChannelSettings settings{0,anticipation,false,1,seconds,false,seconds,false,false};
    const TransitionSettings transition{2,Tenth(),0,0,true};bool transitioned;return a.TransitionChannel(channel,tree,settings,transition,true,true,transitioned,error);
}
}
std::string_view MotionGraphGestureCatalogName(std::uint32_t id) {return id<Catalog.size()?Catalog[id]:std::string_view{};}
bool ParseMotionGraphGestureOperation(const GraphAttributes& a,MotionGraphGestureOperation& output,bool& recognized,std::string& error)
{
    const auto name=TrimMotionGraphName(a.Text("name").value_or(""));recognized=true;error.clear();if (name=="CharacterGesture") output=MotionGraphGestureOperation::Character;else if (name=="EndGesture") output=MotionGraphGestureOperation::End;else recognized=false;return true;
}
void MotionGraphCharacterGestureState::End(MotionAnimation& a) {EndAll(a);ClearActive();stage_=-1;}
bool MotionGraphCharacterGestureState::NextStage(MotionAnimation& a,const MotionGraphCharacterGestureInputs& input,std::int32_t stage,std::string& error)
{
    std::string name;if (!AnimationName(direction_,hands_,stage,input.selections,name,error)) return false;stage_=stage;
    const TransitionSettings transition{4,0,0,0,false};bool transitioned;return a.TransitionChannel(Channels[hands_],name,GestureSettings(stage==1,false),transition,true,true,transitioned,error);
}
bool MotionGraphCharacterGestureState::Update(MotionAnimation& a,const MotionGraphCharacterGestureInputs& input,std::optional<MotionGraphGesturePublication>& output,std::string& error)
{
    output.reset();error.clear();bool any=false;for (auto name:Channels) any|=a.channels.Has(name);
    if (active_&&!any) {stage_=-1;ClearActive();}else if (!active_&&any) {EndAll(a);ClearActive();}
    std::array<bool,4> held;std::size_t i=0;for (auto name:{"GestureLeftHeld","GestureRightHeld","GestureUpHeld","GestureDownHeld"}) held[i++]=input.motion_intents.Contains(name);
    auto selected=SelectStart(input.motion_intents);const auto hands=SelectHands(a,input);
    if (selected==-1 && direction_!=-1 && !held[direction_]) for (auto d:{3,0,2,1}) if (held[d]) {selected=d;break;}
    const bool braking=input.motion_intents.Contains("ForceBrake")&&!input.force_brake_bypass;
    const bool start=selected!=-1&&hands!=-1&&!braking&&(!input.suppress_up||selected!=2)&&(direction_==-1||!held[direction_])&&(!active_||selected!=direction_);
    if (start)
    {
        std::string name;if (!AnimationName(selected,hands,0,input.selections,name,error)) return false;direction_=selected;stage_=0;
        const TransitionSettings transition{2,Float(0x3e4ccccd),0,0,false};bool transitioned;if (!a.TransitionChannel(Channels[hands],name,GestureSettings(false,true),transition,true,true,transitioned,error)) return false;
        if (hands==0) {a.channels.End(Channels[2]);a.channels.End(Channels[1]);}else if (hands==1) {a.channels.End(Channels[2]);a.channels.End(Channels[0]);}else {a.channels.End(Channels[0]);a.channels.End(Channels[1]);}
        hands_=hands;active_=true;
    }
    else if (active_)
    {
        if (hands_!=hands) {EndAll(a);ClearActive();}
        else if (!a.channels.InTransition(Channels[hands_]) && a.channels.Remaining(Channels[hands_])<Tenth())
        {
            if (stage_==0) {if (!NextStage(a,input,1,error)) return false;}
            else if (stage_==1 && !held[direction_]) {if (!NextStage(a,input,2,error)) return false;}
            else if (stage_==2) {stage_=-1;ClearActive();}
        }
    }
    if (!active_) return true;std::uint32_t gesture;if (!Selection(direction_,input.selections,gesture,error)) return false;
    Set(a,"GstrDistToCog",input.state_offboard75?1.0f:input.distance_to_cog);output=MotionGraphGesturePublication{gesture,direction_==3};return true;
}
bool ExecuteMotionGraphCharacterGesture(MotionGraphCharacterGestureState& state,MotionCharacterGestureContext c,std::uint8_t phase,std::string& error)
{
    error.clear();if (phase!=1) return true;
    if (!c.physical) {error="CharacterGesture requires original physical and hostgesture publication";return false;}
    if (!c.filtered_category) {error="CharacterGesture requires filteredcategory";return false;}
    if (!c.playback.board_available) {error="CharacterGesture requires boardheldbyte311";return false;}
    if (!c.animation_height) {error="CharacterGesture requires actualheight";return false;}
    const auto& p=*c.physical;std::optional<MotionGraphGesturePublication> output;
    if (!state.Update(c.animation,{c.animation.motion_intents,c.busy_hands,*c.filtered_category,p.ground321,*c.playback.board_available,p.state_offboard75,*c.animation_height,p.selections,p.suppress_up,p.force_brake_bypass},output,error)) return false;
    // Original None leaves the last graph publication intact until EndGesture.
    if (output) c.publication=output;return true;
}
bool ParseGraphMotionShoveOperation(const GraphAttributes& a,GraphMotionShoveOperation& output,bool& recognized,std::string& error)
{
    recognized=a.Text("name")=="Shove";error.clear();if (!recognized) return true;GraphMotionShoveOperation op;
    const auto selection=a.Text("Selection"),anticipation=a.Text("Antic");if (!selection) {error="Shove requires Selection";return false;}op.selection=*selection;op.selection_board=a.Text("SelectionBrd").value_or("");
    if (!anticipation) {error="Shove requires Antic";return false;}op.anticipation=*anticipation;op.anticipation_board=a.Text("AnticBrd").value_or("");output=std::move(op);return true;
}
float MotionGraphShoveDirectionAngle(Vec4 direction,bool mirrored)
{
    const auto x=direction[0],z=mirrored?-direction[2]:direction[2];auto reciprocal=1.0f/z;reciprocal=std::fma(reciprocal,std::fma(-reciprocal,z,1.0f),reciprocal);
    const auto basic=Atan(std::fma(x,reciprocal,0.0f));std::uint32_t bits;std::memcpy(&bits,&x,4);const auto sign=bits&0x80000000u;
    auto angle=z<0?basic+Float(0x40490fdbu|sign):basic;angle=z==0?Float(0x3fc90fdbu|sign):angle;const auto degrees=angle*Float(0x42652ee1);return degrees<0?degrees+Float(0x43b40000):degrees;
}
bool MotionGraphShoveState::Update(const GraphMotionShoveOperation& op,MotionAnimation& a,MotionGraphShovePhysical p,std::array<std::uint32_t,2> hands,bool mirrored,std::string& error)
{
    error.clear();const auto retrieving=a.channels.Has("RetrieveBoard"),board_variant=p.in_biped_category&&p.board_on_ground;
    if (a.MotionIntent("GrabWorld") && !retrieving && hands==std::array<std::uint32_t,2>{0,0})
    {if (!a.channels.Has("SkitchAntic") && !a.channels.Has("Shove")) {board_anticipation=board_variant;if (!StartShoveChannel(a,"SkitchAntic",board_variant?op.anticipation_board:op.anticipation,true,error)) return false;}}
    else if (a.channels.Has("SkitchAntic")) a.channels.End("SkitchAntic");
    auto shove=a.channels.Has("Shove");if (!p.interaction_trigger || retrieving)
    {if (shove) {if (retrieving) a.channels.End("Shove");else Set(a,"ShoveDirection",angle);}return true;}
    angle=MotionGraphShoveDirectionAngle(p.direction,mirrored);if (a.channels.Has("SkitchAntic")) a.channels.End("SkitchAntic");
    if (!shove) {if (!StartShoveChannel(a,"Shove",board_variant?op.selection_board:op.selection,false,error)) return false;shove=true;}
    if (shove) {Set(a,"GstrDistToCog",p.animation_height);Set(a,"ShoveDirection",angle);}return true;
}
void MotionGraphShoveState::End(MotionAnimation& a,bool keep) {if (!keep) for (auto n:{"SkitchAntic","Shove"}) if (a.channels.Has(n)) a.channels.End(n);}
bool ExecuteGraphMotionShoveOperation(const GraphMotionShoveOperation& op,MotionGraphShoveState& state,MotionShoveOperationContext c,std::uint8_t phase,std::string& error)
{
    error.clear();if (phase==0) state.Begin();else if (phase==1) {if (!c.physical) {error="Shove requires actual interaction output";return false;}if (!c.playback.is_mirrored) {error="Shove requires animation stance";return false;}return state.Update(op,c.animation,*c.physical,c.busy_hands,*c.playback.is_mirrored,error);}else state.End(c.animation,c.keep_channels);return true;
}
}
