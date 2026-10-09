#include "PlayerStatePostInputRuntime.h"
#include "PlayerPostInput.h"
#include <cassert>
#include <cstring>
namespace atelier::skate
{
namespace
{
float Value(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
Vec4 Value(const RawVector& words){Vec4 value;std::memcpy(value.data(),words.data(),16);return value;}
Vec3 XYZ(const RawVector& words){return {Value(words[0]),Value(words[1]),Value(words[2])};}
class Services final : public PostInputServices
{
public:
    float heading;
    PlayerGrindInputState& grind;
    std::optional<PlayerGrindPending> pending;
    PlayerGrindPostContext grind_context;
    PlayerGrindLiveHost host;
    std::optional<PlayerGrindPostResult> result;
    ProcessedPhysicsInput& processed;
    AirTrajectoryRuntime& trajectory;
    AirSelectorInput trajectory_input;
    Vec4 trajectory_board_position;
    const WorldGeometry& world;
    std::array<std::optional<OffboardGrabRecord>,2> grab_records;
    std::optional<std::string> error;
    Services(float h,PlayerGrindInputState& g,std::optional<PlayerGrindPending> p,
        PlayerGrindPostContext c,PhysicalSimulationRuntime& f,const PlayerGrindMaterials& materials,
        ProcessedPhysicsInput& input,AirTrajectoryRuntime& t,AirSelectorInput ti,Vec4 board,
        std::array<std::optional<OffboardGrabRecord>,2> records)
        :heading(h),grind(g),pending(std::move(p)),grind_context(c),
        host(f.board,f.settings.board,materials),processed(input),trajectory(t),trajectory_input(ti),
        trajectory_board_position(board),world(f.world),grab_records(std::move(records)){}
    void UpdateGrindManager() override
    {
        if(!pending){error="Grind post-input requires this tick's pre-input queries";return;}
        auto work=std::move(*pending);pending.reset();std::string diagnostic;
        if(!grind.PostUpdate(processed,world,std::move(work),grind_context,host,result,diagnostic))
            error=std::move(diagnostic);
    }
    std::uint8_t UpdateTrajectorySelector() override
    {
        auto input=trajectory_input;input.flags_2476=processed.flags_2476;
        const auto context=AirTrajectoryGrindContext::FromProcessed(processed,trajectory_board_position);
        bool valid=false;std::string diagnostic;
        if(!trajectory.Update(input,world,context,valid,diagnostic))
        {error=std::move(diagnostic);return 0;}
        return std::uint8_t(valid);
    }
    float CalculateHeading() override{return heading;}
    void RegisterCandidate(CandidateRegistration registration) override
    {
        const auto index=registration==CandidateRegistration::First1888?0u:1u;
        if(grab_records[index])CopyGrabRecord(processed.grab_records_1888_2176[index],grab_records[index]->words);
        else error="Grab publication requested without a completed record";
    }
};
}
bool CompletePlayerPostInput(PlayerStateCoordinatorOwners owners,AirPhaseOwners air,
    const PlayerGrindMaterials& materials,GrindRuntime& grind_runtime,std::string& error)
{
    assert(&owners.physical==&air.physical&&&owners.input.processed==&air.processed
        &&&owners.input.toolkit==&air.toolkit&&&owners.state.post.jump_reference==&air.post.jump_reference
        &&&owners.state.post.jump_fix_frames==&air.post.jump_fix_frames);
    AirSelectorInput trajectory_input;
    if(!BindAirSelectorInput(BindAirPhaseInput(air),air.settings,trajectory_input,error))return false;
    auto& input=owners.input;
    if(!input.toolkit){error="Post-input trajectory requires this tick's board toolkit";return false;}
    const auto board_position=input.toolkit->deck[3];auto& post=owners.state.post;auto& p=input.processed;
    auto publication=owners.grab.Publish();
    std::optional<std::uint32_t> object;
    if(publication.object)object=*publication.object;
    CandidatePublicationFields candidates{bool(publication.records[0]),bool(publication.records[0]),
        bool(publication.records[1]),bool(publication.records[1]),object.value_or(p.object_2464),
        std::uint32_t(bool(object)),std::uint32_t(owners.grab.Cache().interactable_latched),bool(publication.object)};
    PostInputPlayerFields player{post.jump_reference,input.player.flags_1296,
        static_cast<std::uint32_t>(input.player.ground_history_frames_1304),post.jump_fix_frames,post.latch_frames};
    PostInputProcessedFields processed{post.jump_reference,p.object_2464,p.flags_2468,p.flags_2472,
        p.flags_2480,p.flags_2484,p.state_2508,post.state_frames,post.jump_fix_frames,post.heading_adjust};
    PostInputPhysOutFields output{owners.state.ground_output&&owners.state.ground_output->ground_32.wall_ride_exit,
        input.physical.air.launched_442!=0,input.physical.air.launch_velocity_128,post.complete};
    const float heading=owners.physical.riding.UpdateInputHeading(Value(p.vectors_464_480_496_512_528[0][1]),p.scalar_2612);
    std::optional<PlayerGrindPending> pending;
    if(input.pending_grind){pending.emplace(std::move(*input.pending_grind));input.pending_grind.reset();}
    assert(input.grind);
    const auto& fields=owners.animation_input.fields;const auto& extra=owners.animation_input.extra;
    Services services(heading,*input.grind,std::move(pending),{owners.physical.DeckFrame(),fields.balance,
        extra.grind_translation,extra.grind_stability_nudge,extra.grind_up_down,extra.grind_grab_min_height},
        owners.physical,materials,p,air.trajectory,trajectory_input,board_position,std::move(publication.records));
    RunPostInput({player,processed,output,candidates},services);
    if(services.error){error=std::move(*services.error);return false;}
    if(!services.result){error="Grind post-input did not publish its result";return false;}
    auto result=std::move(*services.result);
    processed.flags_2468|=p.flags_2468&0x00040000;
    for(const auto reason:result.wipeout_reasons)owners.wipeout.Request(reason,0);
    grind_runtime.Observe(result.observation);
    input.grind_observation=std::make_unique<PlayerGrindObservation>(result.observation);
    const auto& g=p.grind;
    if((g.flags_1516&0x08000000)!=0)
        owners.ground_lifecycle.edge=GroundPhaseEdge{g.flags_1516,Value(g.vector_1232),XYZ(g.second_start_1312),XYZ(g.second_end_1328)};
    else owners.ground_lifecycle.edge.reset();
    post.trajectory_pending=air.trajectory.selector.Pending();post.trajectory_valid=air.trajectory.selector.Valid();
    post.trajectory_available=air.trajectory.selector.Valid();post.trajectory_new_candidate=air.trajectory.selector.JustChanged();
    input.player.flags_1296=player.flags_1296;
    input.player.ground_history_frames_1304=static_cast<std::int32_t>(player.state_frames_1304);
    p.flags_2468=processed.flags_2468;p.flags_2472=processed.flags_2472;
    p.flags_2480=processed.flags_2480;p.flags_2484=processed.flags_2484;p.object_2464=processed.word_2464;
    post.jump_reference=player.jump_reference_1264;post.jump_fix_frames=player.jump_fix_frames_1308;
    post.latch_frames=player.latch_frames_1320;post.state_frames=processed.state_frames_2572;
    post.heading_adjust=processed.scalar_2740;post.complete=output.complete_76;error.clear();return true;
}
}
