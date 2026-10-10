#include "SkeletonAttributeDispatch.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
void Replace(std::uint32_t& flags,unsigned bit,bool set) {flags=(flags&~(1u<<bit))|(std::uint32_t(set)<<bit);}
float ClampControl(float v) {const float lower=-1-v>=0?-1:v;return 1-lower>=0?lower:1;}
std::string DebugDescriptor(const SkeletonAttributeDescriptor& a)
{
    std::string s="ScalarAttribute { name: \""+std::string(a.name)+"\", encoded_name: AttributeName([";
    for (std::size_t i=0;i<5;++i) {if (i) s+=", ";s+=std::to_string(a.encoded_name[i]);}
    return s+"]), comparison_site: "+std::to_string(a.comparison_site)+" }";
}
const std::array<SkeletonAttributeDescriptor,151> Catalog{{
    {"SlideBoard",EncodeAnimationName("SlideBoard"),0x82bdacf8},
    {"SlideNose",EncodeAnimationName("SlideNose"),0x82bdad10},
    {"SlideTail",EncodeAnimationName("SlideTail"),0x82bdad28},
    {"Grind5050",EncodeAnimationName("Grind5050"),0x82bdad40},
    {"Grind5_O",EncodeAnimationName("Grind5_O"),0x82bdad58},
    {"GrindNose",EncodeAnimationName("GrindNose"),0x82bdad70},
    {"GrabWorld",EncodeAnimationName("GrabWorld"),0x82bdad88},
    {"BoardAdjustLeft",EncodeAnimationName("BoardAdjustLeft"),0x82bdadb0},
    {"BoardAdjustRight",EncodeAnimationName("BoardAdjustRight"),0x82bdadd4},
    {"BoardAdjustUp",EncodeAnimationName("BoardAdjustUp"),0x82bdadf8},
    {"BoardAdjustDown",EncodeAnimationName("BoardAdjustDown"),0x82bdae1c},
    {"GrindFacingForwards",EncodeAnimationName("GrindFacingForwards"),0x82bdae40},
    {"GrindFacingBackwards",EncodeAnimationName("GrindFacingBackwards"),0x82bdae6c},
    {"NoInput",EncodeAnimationName("NoInput"),0x82bdae98},
    {"ExitGrind",EncodeAnimationName("ExitGrind"),0x82bdaed0},
    {"NewAutoPump",EncodeAnimationName("NewAutoPump"),0x82bdaef8},
    {"EnteringCoffin",EncodeAnimationName("EnteringCoffin"),0x82bdaf24},
    {"InCoffin",EncodeAnimationName("InCoffin"),0x82bdaf58},
    {"LeavingCoffin",EncodeAnimationName("LeavingCoffin"),0x82bdaf8c},
    {"PlayingLanding",EncodeAnimationName("PlayingLanding"),0x82bdafb4},
    {"Balance",EncodeAnimationName("Balance"),0x82bdafdc},
    {"Spin",EncodeAnimationName("Spin"),0x82bdb004},
    {"KickTurn",EncodeAnimationName("KickTurn"),0x82bdb02c},
    {"Anticipating",EncodeAnimationName("Anticipating"),0x82bdb058},
    {"BodySpin",EncodeAnimationName("BodySpin"),0x82bdb084},
    {"ManualBrake",EncodeAnimationName("ManualBrake"),0x82bdb0ac},
    {"Brake",EncodeAnimationName("Brake"),0x82bdb0d4},
    {"Turn",EncodeAnimationName("Turn"),0x82bdb0f8},
    {"IsStumbling",EncodeAnimationName("IsStumbling"),0x82bdb120},
    {"IsWipeoutPushOffImpulse",EncodeAnimationName("IsWipeoutPushOffImpulse"),0x82bdb148},
    {"IsWipeoutPushOff",EncodeAnimationName("IsWipeoutPushOff"),0x82bdb170},
    {"IsMuteRFoot",EncodeAnimationName("IsMuteRFoot"),0x82bdb198},
    {"IsMuteLFoot",EncodeAnimationName("IsMuteLFoot"),0x82bdb1c0},
    {"IsForceDownRFoot",EncodeAnimationName("IsForceDownRFoot"),0x82bdb1e8},
    {"IsForceDownLFoot",EncodeAnimationName("IsForceDownLFoot"),0x82bdb210},
    {"TurnScale",EncodeAnimationName("TurnScale"),0x82bdb238},
    {"MagScale",EncodeAnimationName("MagScale"),0x82bdb25c},
    {"AnimEndCOMX",EncodeAnimationName("AnimEndCOMX"),0x82bdb280},
    {"AnimEndCOMY",EncodeAnimationName("AnimEndCOMY"),0x82bdb2c0},
    {"AnimEndCOMZ",EncodeAnimationName("AnimEndCOMZ"),0x82bdb300},
    {"AnimTransX",EncodeAnimationName("AnimTransX"),0x82bdb340},
    {"AnimTransY",EncodeAnimationName("AnimTransY"),0x82bdb380},
    {"AnimTransZ",EncodeAnimationName("AnimTransZ"),0x82bdb3c0},
    {"AnimTime",EncodeAnimationName("AnimTime"),0x82bdb400},
    {"AnimPhysBlendSec",EncodeAnimationName("AnimPhysBlendSec"),0x82bdb424},
    {"IsAnimInterpToEdge",EncodeAnimationName("IsAnimInterpToEdge"),0x82bdb448},
    {"CadenceEndPercent",EncodeAnimationName("CadenceEndPercent"),0x82bdb470},
    {"OB_Traj",EncodeAnimationName("OB_Traj"),0x82bdb494},
    {"OB_Air",EncodeAnimationName("OB_Air"),0x82bdb4bc},
    {"Carving",EncodeAnimationName("Carving"),0x82bdb4e4},
    {"RawTurn",EncodeAnimationName("RawTurn"),0x82bdb50c},
    {"HardTurn",EncodeAnimationName("HardTurn"),0x82bdb534},
    {"Slide",EncodeAnimationName("Slide"),0x82bdb55c},
    {"FrontFlip",EncodeAnimationName("FrontFlip"),0x82bdb584},
    {"BackFlip",EncodeAnimationName("BackFlip"),0x82bdb5ac},
    {"Grabbing",EncodeAnimationName("Grabbing"),0x82bdb5d4},
    {"WantsLeftAirGrab",EncodeAnimationName("WantsLeftAirGrab"),0x82bdb5fc},
    {"WantsRightAirGrab",EncodeAnimationName("WantsRightAirGrab"),0x82bdb614},
    {"FlipTrick",EncodeAnimationName("FlipTrick"),0x82bdb62c},
    {"WipeOutRecover",EncodeAnimationName("WipeOutRecover"),0x82bdb654},
    {"ControlledWipeout",EncodeAnimationName("ControlledWipeout"),0x82bdb67c},
    {"Revert",EncodeAnimationName("Revert"),0x82bdb6a4},
    {"RevertDir",EncodeAnimationName("RevertDir"),0x82bdb6c8},
    {"Wipeout",EncodeAnimationName("Wipeout"),0x82bdb6f4},
    {"MinJump",EncodeAnimationName("MinJump"),0x82bdb71c},
    {"TrickHeight",EncodeAnimationName("TrickHeight"),0x82bdb73c},
    {"PrepareJump",EncodeAnimationName("PrepareJump"),0x82bdb764},
    {"jump",EncodeAnimationName("jump"),0x82bdb7e8},
    {"DangerZone",EncodeAnimationName("DangerZone"),0x82bdb810},
    {"LateTrick",EncodeAnimationName("LateTrick"),0x82bdb838},
    {"NoDangerZone",EncodeAnimationName("NoDangerZone"),0x82bdb860},
    {"ChristAir",EncodeAnimationName("ChristAir"),0x82bdb888},
    {"PhysGrindTranslation",EncodeAnimationName("PhysGrindTranslation"),0x82bdb8e0},
    {"PhysGrindStabilityNudge",EncodeAnimationName("PhysGrindStabilityNudge"),0x82bdb904},
    {"PhysGrindUpDown",EncodeAnimationName("PhysGrindUpDown"),0x82bdb928},
    {"PhysGrindGrabMinHeight",EncodeAnimationName("PhysGrindGrabMinHeight"),0x82bdb94c},
    {"PhysBodySpin",EncodeAnimationName("PhysBodySpin"),0x82bdb970},
    {"world_grab_y",EncodeAnimationName("world_grab_y"),0x82bdb994},
    {"world_grab_z",EncodeAnimationName("world_grab_z"),0x82bdb9b8},
    {"PushContact",EncodeAnimationName("PushContact"),0x82bdb9dc},
    {"NewHandPlant",EncodeAnimationName("NewHandPlant"),0x82bdba04},
    {"AnimCommittedHandPlant",EncodeAnimationName("AnimCommittedHandPlant"),0x82bdba28},
    {"DisableFeetTargetIK",EncodeAnimationName("DisableFeetTargetIK"),0x82bdba4c},
    {"OB_Jump",EncodeAnimationName("OB_Jump"),0x82bdba70},
    {"OB_StandingJump",EncodeAnimationName("OB_StandingJump"),0x82bdba98},
    {"OB_Sprint",EncodeAnimationName("OB_Sprint"),0x82bdbac0},
    {"OB_Turn",EncodeAnimationName("OB_Turn"),0x82bdbae8},
    {"OB_Mag",EncodeAnimationName("OB_Mag"),0x82bdbb10},
    {"OB_BipedWorldX",EncodeAnimationName("OB_BipedWorldX"),0x82bdbb34},
    {"OB_BipedWorldZ",EncodeAnimationName("OB_BipedWorldZ"),0x82bdbb58},
    {"OB_LookAtX",EncodeAnimationName("OB_LookAtX"),0x82bdbb7c},
    {"OB_LookAtY",EncodeAnimationName("OB_LookAtY"),0x82bdbba0},
    {"OB_ObjectMvZ",EncodeAnimationName("OB_ObjectMvZ"),0x82bdbbc4},
    {"OB_ObjectMvX",EncodeAnimationName("OB_ObjectMvX"),0x82bdbbe8},
    {"OB_ObjectMvRot",EncodeAnimationName("OB_ObjectMvRot"),0x82bdbc0c},
    {"PlayerControlledPump",EncodeAnimationName("PlayerControlledPump"),0x82bdbc30},
    {"OneFootAir",EncodeAnimationName("OneFootAir"),0x82bdbc58},
    {"WipeoutControlX",EncodeAnimationName("WipeoutControlX"),0x82bdbc7c},
    {"WipeoutControlY",EncodeAnimationName("WipeoutControlY"),0x82bdbca0},
    {"OB_Mounting",EncodeAnimationName("OB_Mounting"),0x82bdbcc4},
    {"OB_Unmounting",EncodeAnimationName("OB_Unmounting"),0x82bdbce8},
    {"OB_Dismount",EncodeAnimationName("OB_Dismount"),0x82bdbd0c},
    {"OB_HoldBoard",EncodeAnimationName("OB_HoldBoard"),0x82bdbd30},
    {"OB_ReleaseBoard",EncodeAnimationName("OB_ReleaseBoard"),0x82bdbd58},
    {"OB_ThrowBoard",EncodeAnimationName("OB_ThrowBoard"),0x82bdbd84},
    {"OB_RetrieveBoard",EncodeAnimationName("OB_RetrieveBoard"),0x82bdbdac},
    {"OB_RetrievingBoard",EncodeAnimationName("OB_RetrievingBoard"),0x82bdbdd4},
    {"OB_DroppingBoard",EncodeAnimationName("OB_DroppingBoard"),0x82bdbdfc},
    {"BipedBoardOnGround",EncodeAnimationName("BipedBoardOnGround"),0x82bdbe24},
    {"IsGroundMount",EncodeAnimationName("IsGroundMount"),0x82bdbe4c},
    {"FootJump",EncodeAnimationName("FootJump"),0x82bdbe74},
    {"AnimSkateboard",EncodeAnimationName("AnimSkateboard"),0x82bdbe98},
    {"HippyJumping",EncodeAnimationName("HippyJumping"),0x82bdbebc},
    {"PushTricking",EncodeAnimationName("PushTricking"),0x82bdbee0},
    {"KickoutDismount",EncodeAnimationName("KickoutDismount"),0x82bdbf04},
    {"RunoutDismount",EncodeAnimationName("RunoutDismount"),0x82bdbf28},
    {"FixLeftFoot",EncodeAnimationName("FixLeftFoot"),0x82bdbf4c},
    {"FixRightFoot",EncodeAnimationName("FixRightFoot"),0x82bdbf70},
    {"DoLandOnBoard",EncodeAnimationName("DoLandOnBoard"),0x82bdbf94},
    {"TransitioningOnOffBoard",EncodeAnimationName("TransitioningOnOffBoard"),0x82bdbfb8},
    {"JumpAboutToTakeOff",EncodeAnimationName("JumpAboutToTakeOff"),0x82bdbfdc},
    {"JumpInProgress",EncodeAnimationName("JumpInProgress"),0x82bdc004},
    {"OB_JumpX",EncodeAnimationName("OB_JumpX"),0x82bdc02c},
    {"OB_JumpZ",EncodeAnimationName("OB_JumpZ"),0x82bdc054},
    {"SkaterOffBoard",EncodeAnimationName("SkaterOffBoard"),0x82bdc078},
    {"JumpHeightOverride",EncodeAnimationName("JumpHeightOverride"),0x82bdc0a0},
    {"IsDark",EncodeAnimationName("IsDark"),0x82bdc0d0},
    {"GrindTrick",EncodeAnimationName("GrindTrick"),0x82bdc0f8},
    {"Shoving",EncodeAnimationName("Shoving"),0x82bdc120},
    {"ShoveDirection",EncodeAnimationName("ShoveDirection"),0x82bdc148},
    {"BipedStartAngle",EncodeAnimationName("BipedStartAngle"),0x82bdc170},
    {"BipedSpinAngle",EncodeAnimationName("BipedSpinAngle"),0x82bdc1a0},
    {"BipedAnimTime",EncodeAnimationName("BipedAnimTime"),0x82bdc1c4},
    {"InManualZone",EncodeAnimationName("InManualZone"),0x82bdc1e8},
    {"OB_Toggle",EncodeAnimationName("OB_Toggle"),0x82bdc210},
    {"TrickFromManual",EncodeAnimationName("TrickFromManual"),0x82bdc238},
    {"WipeoutGestureStickX",EncodeAnimationName("WipeoutGestureStickX"),0x82bdc260},
    {"WipeoutGestureStickY",EncodeAnimationName("WipeoutGestureStickY"),0x82bdc284},
    {"StrongWipeoutArms",EncodeAnimationName("StrongWipeoutArms"),0x82bdc2a8},
    {"StrongWipeoutLegs",EncodeAnimationName("StrongWipeoutLegs"),0x82bdc2d0},
    {"UnderflipBoardContact",EncodeAnimationName("UnderflipBoardContact"),0x82bdc2f8},
    {"AudibleFootStepStrength",EncodeAnimationName("AudibleFootStepStrength"),0x82bdc324},
    {"IsTakeDownByBoard",EncodeAnimationName("IsTakeDownByBoard"),0x82bdc34c},
    {"DropInLock",EncodeAnimationName("DropInLock"),0x82bdc378},
    {"DropInRelease",EncodeAnimationName("DropInRelease"),0x82bdc3a4},
    {"OB_DropIn",EncodeAnimationName("OB_DropIn"),0x82bdc3d0},
    {"BodyAdjustZ",EncodeAnimationName("BodyAdjustZ"),0x82bdc408},
    {"BodyAdjustX",EncodeAnimationName("BodyAdjustX"),0x82bdc42c},
    {"OneFootIntent",EncodeAnimationName("OneFootIntent"),0x82bdc450},
    {"PushSpeed",EncodeAnimationName("PushSpeed"),0x82bdc478},
    {"FootPlanting",EncodeAnimationName("FootPlanting"),0x82bdc4a0},
}};
}
ScalarAttributeInputs ScalarAttributeInputs::Reset(std::uint32_t previous,std::uint32_t previous2488)
{
    ScalarAttributeInputs s{};s.flags2468=(previous&8)|0x2000;s.flags2488=previous2488&0x1fffff;
    s.turn_scale=s.magnitude_scale=1;s.cadence_end_percent=-1;return s;
}
ExtendedAttributes ExtendedAttributes::Reset(float footstep)
{ExtendedAttributes s{};s.footstep_strength=footstep;return s;}
const std::array<SkeletonAttributeDescriptor,151>& SkeletonAttributeCatalog() {return Catalog;}
const SkeletonAttributeDescriptor* LookupSkeletonAttribute(AttributeName name)
{for (const auto& a:Catalog) if (a.encoded_name==name) return &a;return nullptr;}
bool DispatchContactEvent(const AnimationAttribute& a,const ContactEventPose& pose,ScalarAttributeInputs& fields,ContactEventState& state,std::string& error)
{
    if (a.kind!=3||(a.status&12)==0) {error.clear();return true;}
    std::array<std::uint32_t,6> words;
    for (std::size_t i=0;i<6;++i) {if (!a.payload[i]) {error="Active animation bone event has incomplete payload";return false;}words[i]=*a.payload[i];}
    const AttributeName name{words[0],words[1],words[2],words[3],words[4]};const float strength=Float(words[5]);state.bone=-1;
    for (std::size_t i=0;i<pose.bone_names.size();++i) if (pose.bone_names[i]==name) {state.bone=std::int32_t(i);break;}
    if (a.name==EncodeAnimationName("push_contact"))
    {
        fields.flags2468|=1u<<27;Replace(fields.flags2468,26,state.bone==pose.right_toe_bone);Replace(fields.flags2468,25,strength==1);Replace(fields.flags2468,24,strength==-1);
        if (pose.trajectory_bone>=pose.hierarchy.size()) {error="Push contact requires the actual animation trajectory bone";return false;}
        const auto translation=pose.hierarchy[pose.trajectory_bone][3];const float squared=Dot3(translation,translation);float inverse=ReciprocalSquareRootEstimate(squared);
        for (unsigned i=0;i<2;++i) inverse=std::fma(inverse*.5f,std::fma(-squared,inverse*inverse,1.f),inverse);
        const float length=squared==0?0:squared*inverse;const float speed=length*(1.f/pose.timestep);state.push_speed=strength==1?speed:0;
    }
    else if (a.name==EncodeAnimationName("brake_contact")) {fields.flags2468|=1u<<28;Replace(fields.flags2468,30,strength==1);Replace(fields.flags2468,23,strength==-1);}
    else if (a.name==EncodeAnimationName("right_hand_grab")||a.name==EncodeAnimationName("left_hand_grab")) fields.flags2472|=name==EncodeAnimationName("righthand")?0x100u:0x80u;
    error.clear();return true;
}
bool DispatchScalarSkeletonAttribute(const AnimationAttribute& a,ScalarAttributeInputs& input,AnimationControlOutput& output,SkeletonScalarDispatchError& error)
{
    if (a.kind!=0)
    {
        if (a.kind==3&&(a.status&12)!=0) {error={SkeletonScalarDispatchError::Kind::EventConsumerUnavailable,a.name,nullptr};return false;}
        return true;
    }
    const auto* entry=LookupSkeletonAttribute(a.name);if (!entry) return true;const auto name=entry->name;
    const auto scalar=[&](float& value,bool negate=false)
    {if (!a.payload[0]) {error={SkeletonScalarDispatchError::Kind::UninitializedScalar,a.name,entry};return false;}value=Float(*a.payload[0]);if (negate) value=-value;return true;};
    if (name=="SlideBoard"||name=="SlideNose"||name=="SlideTail"||name=="Grind5050"||name=="Grind5_O"||name=="GrindNose") output.grind_name=a.name;
    else if (name=="GrabWorld") input.flags2476|=1u<<22;
    else if (name=="BoardAdjustLeft") input.board_adjust=1;
    else if (name=="BoardAdjustRight") input.board_adjust=2;
    else if (name=="BoardAdjustUp") input.board_adjust=3;
    else if (name=="BoardAdjustDown") input.board_adjust=4;
    else if (name=="GrindFacingForwards") output.flags|=1u<<31;
    else if (name=="GrindFacingBackwards") output.flags&=~(1u<<31);
    else if (name=="NoInput") {output.flags|=1u<<30;input.flags2472|=1u<<23;}
    else if (name=="ExitGrind") input.flags2476|=1u<<29;
    else if (name=="NewAutoPump") output.flags|=1u<<29;
    else if (name=="PlayerControlledPump") input.flags2476|=2;
    else if (name=="EnteringCoffin") {input.flags2472|=2;input.flags2476|=1u<<30;}
    else if (name=="InCoffin") {input.flags2472|=1;input.flags2476|=1u<<30;}
    else if (name=="LeavingCoffin") input.flags2476|=0xc0000000;
    else if (name=="PlayingLanding") input.flags2476|=1u<<28;
    else if (name=="Balance") return scalar(input.balance,true);
    else if (name=="Spin") return scalar(input.spin,true);
    else if (name=="KickTurn") output.flags|=1u<<28;
    else if (name=="Anticipating") output.flags|=1u<<27;
    else if (name=="BodySpin") return scalar(input.body_spin,true);
    else if (name=="ManualBrake") input.flags2468|=1u<<29;
    else if (name=="Brake") return scalar(input.brake);
    else if (name=="Turn") return scalar(input.turn,true);
    else if (name=="IsStumbling") input.flags2484|=1u<<10;
    else if (name=="IsWipeoutPushOffImpulse") input.flags2484|=1u<<8;
    else if (name=="IsWipeoutPushOff") input.flags2484|=1u<<9;
    else if (name=="IsMuteRFoot") input.flags2484|=1u<<7;
    else if (name=="IsMuteLFoot") input.flags2484|=1u<<6;
    else if (name=="IsForceDownRFoot") input.flags2484|=1u<<3;
    else if (name=="IsForceDownLFoot") input.flags2484|=1u<<2;
    else if (name=="TurnScale") return scalar(input.turn_scale);
    else if (name=="MagScale") return scalar(input.magnitude_scale);
    else if (name=="AnimEndCOMX") return scalar(input.animation_end_com[0]);
    else if (name=="AnimEndCOMY") return scalar(input.animation_end_com[1]);
    else if (name=="AnimEndCOMZ") return scalar(input.animation_end_com[2]);
    else if (name=="AnimTransX") return scalar(input.animation_translation[0]);
    else if (name=="AnimTransY") return scalar(input.animation_translation[1]);
    else if (name=="AnimTransZ") return scalar(input.animation_translation[2]);
    else if (name=="AnimTime") return scalar(input.animation_time);
    else if (name=="AnimPhysBlendSec") return scalar(input.animation_physics_blend_seconds);
    else if (name=="IsAnimInterpToEdge") input.flags2488|=1u<<27;
    else if (name=="CadenceEndPercent") return scalar(input.cadence_end_percent);
    else if (name=="OB_Traj") input.flags2476|=1u<<15;
    else if (name=="OB_Air") input.flags2476|=1u<<7;
    else if (name=="Carving") input.flags2468|=1u<<31;
    else if (name=="RawTurn") return scalar(input.raw_turn,true);
    else if (name=="HardTurn") return scalar(input.hard_turn,true);
    else if (name=="Slide") return scalar(input.slide,true);
    else if (name=="FrontFlip") input.flags2468|=1u<<7;
    else if (name=="BackFlip") input.flags2468|=1u<<6;
    else if (name=="Grabbing") input.flags2468|=1u<<5;
    else if (name=="WantsLeftAirGrab"||name=="WantsRightAirGrab") input.flags2468|=1u<<4;
    else if (name=="FlipTrick") input.flags2472|=1u<<22;
    else if (name=="WipeOutRecover") input.flags2472|=1u<<20;
    else if (name=="ControlledWipeout") input.flags2472|=1u<<19;
    else if (name=="PushContact") input.flags2488|=1u<<29;
    else if (name=="PushSpeed") input.flags2488|=1u<<23;
    else {error={SkeletonScalarDispatchError::Kind::KnownScalarUnavailable,a.name,entry};return false;}
    return true;
}
namespace
{
bool Extended(std::string_view name,const AnimationAttribute& a,ScalarAttributeInputs& input,
    ExtendedAttributes& extra,AnimationControlOutput& output,bool& handled,std::string& error)
{
    handled=true;
    const auto scalar=[&](float& value,bool negate=false)
    {if (!a.payload[0]) {error=std::string(name)+": scalar payload absent";return false;}value=Float(*a.payload[0]);if (negate) value=-value;return true;};
    if (name=="Wipeout") input.flags2468|=0x40000;
    else if (name=="jump") input.flags2468|=0x400000;
    else if (name=="DangerZone") input.flags2472|=0x8000;
    else if (name=="LateTrick") input.flags2472|=0x20;
    else if (name=="NoDangerZone") input.flags2472|=0x10;
    else if (name=="ChristAir") input.flags2472|=0x40;
    else if (name=="PhysGrindTranslation") return scalar(extra.grind_translation);
    else if (name=="PhysGrindStabilityNudge") return scalar(extra.grind_stability_nudge);
    else if (name=="PhysGrindUpDown") return scalar(extra.grind_up_down);
    else if (name=="PhysGrindGrabMinHeight") return scalar(extra.grind_grab_min_height);
    else if (name=="PhysBodySpin") return scalar(extra.physical_body_spin);
    else if (name=="world_grab_y") return scalar(extra.world_grab_y);
    else if (name=="world_grab_z") return scalar(extra.world_grab_z);
    else if (name=="NewHandPlant") extra.flags2480|=0x20000000;
    else if (name=="AnimCommittedHandPlant") extra.flags2480|=0x10000000;
    else if (name=="DisableFeetTargetIK") extra.flags2480|=0x08000000;
    else if (name=="OB_Jump") input.flags2476|=0x80000;
    else if (name=="OB_StandingJump") input.flags2476|=0x40000;
    else if (name=="OB_Sprint") input.flags2484|=0x20000;
    else if (name=="OB_Turn") return scalar(extra.offboard_turn,true);
    else if (name=="OB_Mag") return scalar(extra.offboard_magnitude);
    else if (name=="OB_BipedWorldX") return scalar(extra.biped_world_x);
    else if (name=="OB_BipedWorldZ") return scalar(extra.biped_world_z);
    else if (name=="OB_LookAtX") return scalar(extra.look_x);
    else if (name=="OB_LookAtY") return scalar(extra.look_y);
    else if (name=="OB_ObjectMvZ") return scalar(extra.object_move_z);
    else if (name=="OB_ObjectMvX") return scalar(extra.object_move_x);
    else if (name=="OB_ObjectMvRot") return scalar(extra.object_move_rotation);
    else if (name=="OneFootAir") extra.flags2480|=0x04000000;
    else if (name=="WipeoutControlX") return scalar(extra.wipeout_control[0]);
    else if (name=="WipeoutControlY") return scalar(extra.wipeout_control[1]);
    else if (name=="OB_Mounting") extra.flags2480|=0x80000;
    else if (name=="OB_Unmounting") extra.flags2480|=0x40000;
    else if (name=="OB_Dismount") extra.flags2480|=0x20000;
    else if (name=="OB_HoldBoard") input.flags2476|=0x4000;
    else if (name=="OB_ReleaseBoard") input.flags2476=(input.flags2476&~0x3000u)|0x2000;
    else if (name=="OB_ThrowBoard") input.flags2476|=0x3000;
    else if (name=="OB_RetrieveBoard") input.flags2476|=0x800;
    else if (name=="OB_RetrievingBoard") input.flags2476|=0x400;
    else if (name=="OB_DroppingBoard") input.flags2476|=0x200;
    else if (name=="BipedBoardOnGround") input.flags2484|=1;
    else if (name=="IsGroundMount") input.flags2488|=0x80000000;
    else if (name=="FootJump") extra.flags2480|=0x2000;
    else if (name=="AnimSkateboard") extra.flags2480|=0x4000;
    else if (name=="HippyJumping") extra.flags2480|=0x1000;
    else if (name=="PushTricking") extra.flags2480|=0x800;
    else if (name=="KickoutDismount") extra.flags2480|=0x100;
    else if (name=="RunoutDismount") extra.flags2480|=0x80;
    else if (name=="FixLeftFoot") extra.flags2480|=0x40;
    else if (name=="FixRightFoot") extra.flags2480|=0x20;
    else if (name=="DoLandOnBoard") extra.flags2480|=0x10;
    else if (name=="TransitioningOnOffBoard") extra.flags2480|=4;
    else if (name=="JumpAboutToTakeOff") input.flags2484|=0x40000000;
    else if (name=="JumpInProgress") input.flags2484|=0x20000000;
    else if (name=="OB_JumpX") return scalar(extra.offboard_jump[0],true);
    else if (name=="OB_JumpZ") return scalar(extra.offboard_jump[1]);
    else if (name=="SkaterOffBoard") input.flags2484|=0x08000000;
    else if (name=="IsDark") input.flags2484|=0x200000;
    else if (name=="GrindTrick") input.flags2484|=0x100000;
    else if (name=="Shoving") input.flags2484|=0x80000;
    else if (name=="ShoveDirection") input.flags2484|=0x40000;
    else if (name=="BipedStartAngle") {input.flags2484|=0x4000;return scalar(extra.biped_start_angle);}
    else if (name=="BipedSpinAngle") return scalar(extra.biped_spin_angle);
    else if (name=="BipedAnimTime") return scalar(extra.biped_animation_time);
    else if (name=="InManualZone") input.flags2484|=0x2000;
    else if (name=="OB_Toggle") input.flags2484|=0x1000;
    else if (name=="TrickFromManual") input.flags2484|=0x800;
    else if (name=="WipeoutGestureStickX") return scalar(extra.wipeout_gesture[0]);
    else if (name=="WipeoutGestureStickY") return scalar(extra.wipeout_gesture[1]);
    else if (name=="StrongWipeoutArms") input.flags2484|=0x20;
    else if (name=="StrongWipeoutLegs") input.flags2484|=0x10;
    else if (name=="UnderflipBoardContact") output.flags|=0x04000000;
    else if (name=="AudibleFootStepStrength") return scalar(extra.footstep_strength);
    else if (name=="IsTakeDownByBoard") output.flags|=0x02000000;
    else if (name=="DropInLock") output.flags|=0x01000000;
    else if (name=="DropInRelease") output.flags|=0x00800000;
    else if (name=="OB_DropIn") {output.flags|=0x00400000;input.flags2488|=0x10000000;}
    else if (name=="BodyAdjustZ") return scalar(extra.body_adjust[1]);
    else if (name=="BodyAdjustX") return scalar(extra.body_adjust[0]);
    else if (name=="OneFootIntent") input.flags2488|=0x02000000;
    else if (name=="FootPlanting") extra.flags2480|=0x00800000;
    else handled=false;
    return true;
}
struct Accumulator
{
    bool revert=false;
    float revert_direction=1,minimum_jump=0,trick_height=0;
    bool has_trick_height=false;
    bool Dispatch(std::string_view name,const AnimationAttribute& a,ScalarAttributeInputs& fields,
        JumpAttributeState& cached,ActionMap* map,bool& handled,std::string& error)
    {
        handled=true;
        const auto scalar=[&](float& value)
        {if (!a.payload[0]) {error=std::string(name)+": scalar payload absent";return false;}value=Float(*a.payload[0]);return true;};
        if (name=="Revert") revert=true;
        else if (name=="RevertDir") {if (!scalar(revert_direction)) return false;fields.flags2472|=0x200000;}
        else if (name=="MinJump") return scalar(minimum_jump);
        else if (name=="TrickHeight") {if (!scalar(trick_height)) return false;has_trick_height=true;}
        else if (name=="PrepareJump") {fields.flags2468|=0x200000;if (map) cached.prepared_controls={ClampControl(map->Value(64)),ClampControl(map->Value(65))};}
        else if (name=="JumpHeightOverride") {if (!scalar(cached.height_override)) return false;cached.height_override_active=true;}
        else handled=false;
        return true;
    }
    void Finish(ScalarAttributeInputs& fields,ExtendedAttributes& extra,JumpAttributeState& cached,FinalizationInput input,ActionMap* map) const
    {
        if (revert) extra.revert_direction=revert_direction;
        if (fields.flags2468&0x400000) extra.jump_strength=input.select_jump_extremes&&trick_height<=input.low_jump_threshold?minimum_jump:input.select_jump_extremes&&trick_height>=input.high_jump_threshold?1:trick_height;
        if (has_trick_height&&input.allow_height_override)
        {if (cached.height_override_active) {const float difference=cached.height_override-extra.jump_strength;if (difference>=0) extra.jump_strength=cached.height_override;}}
        else {cached.height_override=0;cached.height_override_active=false;}
        if (extra.flags2480&0x1000) extra.jump_strength=trick_height;
        if (input.use_prepared_controls) extra.jump_controls=cached.prepared_controls;
        else if (map) extra.jump_controls={ClampControl(map->Value(64)),ClampControl(map->Value(68))};
        if (input.external_impulse_active) fields.flags2468|=0x40000;
        extra.flags2480=(extra.flags2480&~8u)|((input.animation_flags>>24)&8);
        fields.flags2484=(fields.flags2484&~2u)|((input.animation_flags>>22)&2);
        fields.flags2484=(fields.flags2484&0x7fffffff)|((input.animation_flags<<6)&0x80000000);
        fields.flags2484=(fields.flags2484&~0x01000000u)|((input.animation_flags>>4)&0x01000000);
        if (fields.flags2476&0x600) fields.flags2476&=~0x400000u;
    }
};
}
bool ProcessSkeletonAttributes(const std::vector<AnimationAttribute>& attributes,const ContactEventPose& pose,
    ScalarAttributeInputs& fields,ExtendedAttributes& extra,ContactEventState& contacts,
    JumpAttributeState& cached,AnimationControlOutput& output,FinalizationInput finalization,
    ActionMap* map,std::string& error)
{
    Accumulator accumulator;
    for (std::size_t i=0;i<attributes.size();++i)
    {
        const auto& a=attributes[i];std::string detail;bool ok=true;
        if (a.kind==3) ok=DispatchContactEvent(a,pose,fields,contacts,detail);
        else
        {
            SkeletonScalarDispatchError scalar_error{};
            if (!DispatchScalarSkeletonAttribute(a,fields,output,scalar_error))
            {
                if (scalar_error.kind!=SkeletonScalarDispatchError::Kind::KnownScalarUnavailable)
                {detail="Invalid scalar payload: UninitializedScalar { attribute: "+DebugDescriptor(*scalar_error.attribute)+" }";ok=false;}
                else
                {
                    const auto name=scalar_error.attribute->name;bool handled;
                    ok=accumulator.Dispatch(name,a,fields,cached,map,handled,detail);
                    if (ok&&!handled) ok=Extended(name,a,fields,extra,output,handled,detail);
                    if (ok&&!handled) {detail="Unimplemented known Skeleton attribute "+std::string(name);ok=false;}
                }
            }
        }
        if (!ok) {error="Skeleton attribute"+std::to_string(i)+": "+detail;return false;}
    }
    accumulator.Finish(fields,extra,cached,finalization,map);error.clear();return true;
}
}
