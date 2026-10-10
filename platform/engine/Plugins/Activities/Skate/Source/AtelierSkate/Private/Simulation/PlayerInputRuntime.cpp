#include "PlayerInputRuntime.h"
#include "PlayerGroundPosition.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
namespace
{
Mat4 DeckFrame(const BoardRuntime& board)
{
    const auto deck=board.PartTransforms()[6];Mat4 f{};
    for(std::size_t i=0;i<3;++i)for(std::size_t j=0;j<3;++j)f[i][j]=deck.basis.columns[i][j];
    f[3]={deck.translation.x,deck.translation.y,deck.translation.z,0};return f;
}
std::string DebugString(std::string_view v)
{
    std::string result="\"";constexpr char hex[]="0123456789abcdef";
    for(unsigned char c:v){switch(c){case 0:result+="\\0";break;case '\t':result+="\\t";break;case '\n':result+="\\n";break;
        case '\r':result+="\\r";break;case '"':result+="\\\"";break;case '\\':result+="\\\\";break;
        default:if(c<32||c==127){result+="\\u{";if(c>=16)result+=hex[c>>4];result+=hex[c&15];result+='}';}else result+=char(c);}}
    result+='"';return result;
}
class Services final:public InputPhaseServices
{
    PlayerInputRuntime& runtime;PlayerInputOwners owners;const Mat4& ground_frame;PlayerInputHostFrame host;
    PlayerInputAnimationFrame animation;PlayerInputTeleportServices& teleport;const PlayerGrindStaticProvider& provider;
    std::optional<Mat4>& pending;
public:
    Services(PlayerInputRuntime& r,PlayerInputOwners o,const Mat4& f,PlayerInputHostFrame h,PlayerInputAnimationFrame a,
        PlayerInputTeleportServices& t,const PlayerGrindStaticProvider& p,std::optional<Mat4>& request):runtime(r),owners(o),ground_frame(f),host(h),animation(a),teleport(t),provider(p),pending(request){}
    bool UpdatePreInputManager(PlayerInputState& p,PhysicalPlayerInput&,std::string& error) override
    {return runtime.pre_input.Prepare(p.manager_1856_counter_320,error);}
    bool ResetProcessedInput(ProcessedPhysicsInput& p,std::string&) override{ResetProcessedPhysicsInput(p);return true;}
    bool ActorQuery56(std::uint32_t& out,std::string&) override{out=host.actor_query_56;return true;}
    bool ActorQuery44(std::uint32_t& out,std::string&) override{out=host.actor_query_44;return true;}
    bool ResetPlayerProbe(PlayerInputState& p,PhysicalPlayerInput&,std::string&) override{p.probe={};return true;}
    bool CheckTeleport(PlayerInputState& p,PhysicalPlayerInput& physical,ProcessedPhysicsInput& out,std::string& error) override
    {
        if(physical.state.flag_61!=0&&!teleport.Teleport(owners,host.published_board_transform,p,physical,out,error))return false;
        if((p.flags_1296&(1u<<19))!=0){if(!teleport.Teleport(owners,DeckFrame(owners.physical.board),p,physical,out,error))return false;p.flags_1296&=~(1u<<19);}
        if(pending){if(!teleport.Teleport(owners,*pending,p,physical,out,error))return false;pending.reset();}
        return true;
    }
    bool ActorInputAvailable(bool& out,std::string&) override{out=host.input_available;return true;}
    bool TransitionAction(float& out,std::string&) override{out=host.transition_action;return true;}
    bool CalculateGroundPosition(const PhysicalPlayerInput&,RawVector& out,std::string&) override{out=PlayerGroundPosition(owners.physical.board,ground_frame);return true;}
    bool PrepareBoardToolkit(PlayerInputState&,PhysicalPlayerInput&,ProcessedPhysicsInput& out,std::string&) override
    {
        auto t=BoardToolkit::FromBoard(owners.physical.board,out.flags_2468,out.scalar_2612,Float4(out.vectors_464_480_496_512_528[0]),owners.ground.retained_board_normal);
        owners.ground.retained_board_normal=t.filtered_normal;out.scalar_2616=t.absolute_speed;runtime.toolkit=t;return true;
    }
    bool ProcessSkeleton(const AnimationInputPacket& packet,PhysicalPlayerInput& physical,ProcessedPhysicsInput& p,std::string& error) override
    {
        if(!runtime.toolkit){error="Input toolkit must precede Skeleton::ProcessData";return false;}
        if(!owners.animation_input.SelectPhysicsMode(p.state_variant_index_2528,error))return false;
        return owners.skeleton_input.ProcessData(*runtime.toolkit,packet,physical,p,owners.SkeletonOwners(),animation.pose,animation.collision,error);
    }
    bool UpdateGrindManager(PlayerInputState&,PhysicalPlayerInput&,ProcessedPhysicsInput& p,std::string& error) override
    {
        if(runtime.pending_grind){error="Previous grind input was not consumed by PostInput";return false;}
        const auto& a=owners.animation_input;const auto& e=a.extra;
        const PlayerGrindPreContext context{DeckFrame(owners.physical.board),host.air_counter_40,p.state_2504,animation.air_targeting_grind_9653,
            a.fields.balance,e.grind_translation,e.grind_stability_nudge,e.grind_up_down,e.grind_grab_min_height};
        PlayerGrindLiveHost live(owners.physical.board,owners.physical.settings.board,owners.grind_materials);
        std::optional<PlayerGrindPending> pending_result;
        if(!runtime.grind->PreUpdate(p,provider,owners.physical.world,context,live,pending_result,error))return false;
        runtime.pending_grind=std::make_unique<PlayerGrindPending>(std::move(*pending_result));return true;
    }
};
}
PlayerInputRuntime::PlayerInputRuntime()=default;
PlayerInputRuntime::~PlayerInputRuntime()=default;
PlayerInputRuntime::PlayerInputRuntime(PlayerInputRuntime&&) noexcept=default;
PlayerInputRuntime& PlayerInputRuntime::operator=(PlayerInputRuntime&&) noexcept=default;
std::optional<PlayerInputRuntime> PlayerInputRuntime::Load(const SettingsDatabase& db,std::string& error)
{
    PlayerInputRuntime value;ResetPhysicalPlayerOutputs(value.physical);ResetProcessedPhysicsInput(value.processed);
    if(!LoadPlayerInputState(db,value.player,error)||!value.normal_settings_.Load(db,error))return std::nullopt;
    auto g=PlayerGrindInputState::Load(db,error);if(!g)return std::nullopt;value.grind=std::make_unique<PlayerGrindInputState>(std::move(*g));return value;
}
bool PlayerInputRuntime::RequestTeleport(Mat4 f,std::string& error)
{
    if(pending_teleport_){error="A pending teleport must complete before replacement";return false;}
    pending_teleport_=f;return true;
}
void PlayerInputRuntime::UpdateDynamicNormal(const PhysicalRidingOutputs& riding,Vec3 gravity)
{dynamic_normal.Update(riding.ground,gravity,processed.scalar_2656,normal_settings_);}
bool PlayerInputRuntime::PublishBoard(const PhysicalRidingOutputs& riding,std::string& error)
{return PublishPlayerBoardOutputs(physical,riding,toolkit,dynamic_normal,processed,error);}
bool PlayerInputRuntime::PublishGrindGraphOutputs(const SkeletonPhysicalRecord& record,Vec4 up,const PlayerTrajectoryGrindOwner& trajectory,std::string& error)
{return PublishPlayerGrindGraphOutputs(physical,record,up,toolkit,trajectory,error);}
bool PlayerInputRuntime::ProcessStage(PlayerInputOwners owners,const Mat4& frame,const AnimationInputPacket& packet,PlayerInputHostFrame host,
    PlayerInputAnimationFrame animation,PlayerInputTeleportServices& teleport,PlayerInputStage stage,const PlayerGrindStaticProvider& provider,
    std::optional<InputContinuation>& result,std::string& error)
{
    Services services(*this,owners,frame,host,animation,teleport,provider,pending_teleport_);InputPhaseError failure;
    InputContinuation continuation;
    const bool ok=stage.kind==PlayerInputStage::Kind::ThroughTeleport?
        StartPlayerInputPhase(player,physical,packet,processed,services,continuation,failure):
        FinishPlayerInputPhase(stage.continuation,player,physical,packet,processed,services,failure);
    if(!ok){error="Player input: "+(failure.kind==InputPhaseError::Kind::InvalidStateVariant?
        "InvalidStateVariant("+std::to_string(failure.state_variant)+")":"Service("+DebugString(failure.service)+")");return false;}
    result=stage.kind==PlayerInputStage::Kind::ThroughTeleport?std::optional<InputContinuation>(continuation):std::nullopt;return true;
}
}
