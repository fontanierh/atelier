// Prefixed by accepted physical/adjusted probe observation adapters.
#include "SkeletonInputRuntime.h"
struct Input
{
    std::uint32_t Word(){return ::Word();}float Float(){return ::Float();}
    std::uint64_t Wide(){const auto lo=Word();return lo|(std::uint64_t(Word())<<32);}
    template<std::size_t N>std::array<float,N> Floats(){return ::Floats<N>();}
    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> v;for(auto& x:v)x=Word();return v;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& x:a)x=f(*this);return a;}
    template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>{f(*this)}:std::nullopt;}
    AnimationAttribute Attribute(){AnimationAttribute a;a.name=Words<5>();a.kind=std::uint8_t(Word());a.status=std::uint8_t(Word());a.sequence_id=std::int32_t(Word());a.begin_time=Float();a.end_time=Float();for(auto& v:a.payload){if(Word())v=Word();else v.reset();}return a;}
};
struct Output
{
    std::vector<std::uint32_t>& words;
    void Word(std::uint32_t v){words.push_back(v);}void Wide(std::uint64_t v){Word(std::uint32_t(v));Word(std::uint32_t(v>>32));}
    void Float(float v){std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}
};
// GENERATED_PROTOCOL
struct Actions final:ActionMap
{
    std::array<float,18> values{};std::vector<std::uint32_t> calls;
    float Value(std::uint32_t a)override{calls.push_back(a);if(a<64||a>81)std::abort();return values[a-64];}
    std::uint8_t State(std::uint32_t a)override{return Value(a)!=0;}
};
namespace
{
void ObserveDispatcher(const SkeletonInputRuntime& s,const PhysicsAnimationInput& input,const SkeletonWobble& wobble,bool elapsed,const ProcessedPhysicsInput& p,const Actions& actions)
{
    Out(std::uint32_t(s.reenable_requested));Out(std::uint32_t(s.teleporting));Out(s.force_mode);Out(s.head_tracking_history);Out(std::uint32_t(s.head_tracking_active));Out(std::uint32_t(s.grind_air_started));Out(std::uint32_t(s.grind_air_active));Out(std::uint32_t(s.grind_air_adjusting));OutGrind(s.grind_air);
    Out(std::uint32_t(wobble.active));Out(std::uint32_t(wobble.landing));Out(wobble.time);Out(wobble.amplitude);Out(wobble.direction);Out(std::uint32_t(elapsed));
    Output o{output};Observe(o,input.fields);Observe(o,input.extra);Observe(o,input.contacts);Observe(o,input.output);Observe(o,input.JumpCache());Observe(o,input.Settings());for(bool b:input.HeightOverrides())Out(std::uint32_t(b));Out(std::uint32_t(input.RightToe()));Out(std::uint32_t(input.BoneNames().size()));for(const auto& n:input.BoneNames())Out(n);Out(std::uint32_t(actions.calls.size()));for(auto a:actions.calls)Out(a);Observe(o,p);
}
bool ProcessDispatcher(Input& i,PhysicalSimulationRuntime& r,AnimatedSkeleton& a,FootIk& ik,SkeletonInputRuntime& owner,PhysicsAnimationInput& input,SkeletonWobble& wobble,const SkeletonWobbleSettings& wobble_settings,AnimationPoseEvaluator& evaluator,AdjustedFrame& state,Actions& actions)
{
    const auto pose=i.Word();auto& p=state.input;p.timestep_2604=i.Float();p.state_2508=i.Word();p.category_2512=i.Word();p.filtered_state_2524=i.Word();p.flags_2468=i.Word();p.flags_2472=i.Word();p.flags_2476=i.Word();p.flags_2480=i.Word();p.flags_2484=i.Word();p.flags_2488=i.Word();const auto animation_flags=i.Word();const bool impulse=i.Word()!=0;const auto count=i.Word();std::vector<AnimationAttribute> attributes;for(unsigned n=0;n<count;++n)attributes.push_back(i.Attribute());actions.values=i.Floats<18>();const auto branch=i.Word();const bool solve=i.Word()!=0;actions.calls.clear();p.gravity_2648=9.81f;
    p.line_tests_960_1008_1056={state.queries.left_line_test_1536,state.queries.right_line_test_1584,state.queries.hips_line_test_1488};p.vectors_400_416[0]=Raw(Four(r.board.Bodies()[6].rates.linear_velocity));p.vectors_720_784_800_816_832_864[0]=Raw(Four(r.board.Bodies()[6].rates.angular_velocity));p.vectors_544_560_592_608[0]=Raw(Four(r.riding.ground.overall_normal));p.vectors_544_560_592_608[3]=Raw(r.skeleton.record.centre_of_mass_velocity);p.off_board_scalar_2832=.1f;
    std::string error;SkeletonLineTests lines;const auto owners=SkeletonInputOwners{r,a,ik,input};const auto collision=SkeletonInputCollision{r.collision_feedback.flags.compliant,r.collision_feedback.flags.has_impulse,r.collision_pose_error,r.skeleton_collision.partial_ragdoll,r.collision_feedback.drive_weight};
    if(!r.BeginBoardQueries(error)||!QuerySkeletonLines(r.world,r.skeleton,lines,error)){Out(0u);Out(error);return false;}
    const auto globals=pose==4?std::vector<Mat4>{}:Hierarchy(evaluator,pose);const auto toolkit=BoardToolkit::FromBoard(r.board,p.flags_2468,r.riding.motion.speed,Four(r.riding.ground.overall_normal),Four(r.riding.reckoning.ground_normal));
    AnimationPacketFields publication{};publication.timestep=p.timestep_2604;publication.flags_10375_10496_10784[1]=impulse;ExternalPhysicsInput external{};AnimationInputPacket packet{publication,external};packet.flags_10932=animation_flags;PhysicalPlayerInput physical{};
    if(!owner.ProcessData(toolkit,packet,physical,p,owners,{globals,attributes,actions},collision,error)){Out(0u);Out(error);r.FinishBoardQueries(error);lines.Publish(state.queries);return false;}
    if(!r.FinishBoardQueries(error)){Out(0u);Out(error);return false;}
    // GroundPacketInputs consumes retained Processed528; the collision normal
    // remains a separate physical-feedback observation below. The source call
    // transport saves/restores the entire processed packet around reckoning.
    const auto collision_dynamic_up=r.riding.ground.overall_normal;Vec4 retained_dynamic_up;for(unsigned lane=0;lane<4;++lane)std::memcpy(&retained_dynamic_up[lane],&p.vectors_464_480_496_512_528[4][lane],4);
    const PhysicalGroundPacket ground{r.riding.ground.wheel_normal,{retained_dynamic_up[0],retained_dynamic_up[1],retained_dynamic_up[2]},r.riding.motion.speed,r.riding.motion.ground_speed,r.riding.ground.wheel_contact_count};r.processed_flags_2468=p.flags_2468;
    if(branch!=3)
    {
        r.riding.UpdateGroundReckoning(r.board,{r.animation_record.ComToDeck(),input.fields.spin},p.flags_2468,input.fields.balance,false,ground);r.board_frames.UpdateComLift(r.roots.animation_to_world,a.animation_hips[3],.02f);bool ok=false;Mat4 frame=SkeletonIdentity;std::array<Mat4,24> drives;
        if(branch==0)ok=owner.GeneralUpdate(p,owners,globals,collision,drives,error);else if(branch==1)ok=owner.UpdateGround(r.riding.reckoning_frames.system,p,owners,globals,collision,frame,error);else if(branch==2)ok=owner.UpdateTeleport(r.riding.reckoning_frames.system,p,owners,globals,collision,frame,error);else std::abort();Out(frame);
        if(!ok){Out(0u);Out(error);lines.Publish(state.queries);return false;}
    }
    lines.Publish(state.queries);r.processed_flags_2468=p.flags_2468;
    if(solve)
    {
        if(!r.Solve({0,0},error)){Out(0u);Out(error);return false;}Out(std::uint32_t(r.contact_count));Out(std::uint32_t(r.solved_drives?r.solved_drives->rows.size():0));r.FinishBoardOutputs({p.state_2508,ground.wheel_normal,{r.roots.animation_to_world[1][0],r.roots.animation_to_world[1][1],r.roots.animation_to_world[1][2]},{toolkit.deck[3][0],toolkit.deck[3][1],toolkit.deck[3][2]},float(r.ticks)*p.timestep_2604});PhysicalFeedbackInput feedback{p.state_2508,p.category_2512,p.flags_2472,p.flags_2480,{},{}};feedback.vectors_464_480_496_512_528[0]=Four(ground.wheel_normal);feedback.vectors_464_480_496_512_528[1]=feedback.vectors_464_480_496_512_528[2]=Four(r.riding.ground.parts[6].point);feedback.vectors_464_480_496_512_528[4]=Four(collision_dynamic_up);feedback.vectors_880_896_912_928_944[0]=a.animation_hips[3];feedback.vectors_880_896_912_928_944[1]={0,1,0,0};r.PublishFeedback(feedback);
        auto observed=r.DeckFrame();const auto wobble_output=wobble.Update(wobble_settings);ApplySkeletonWobble(wobble_output,observed);Out(std::uint32_t(wobble_output.sampled));Out(wobble_output.tilt);Out(wobble_output.squish);Out(std::uint32_t(wobble_output.remains_active));Out(observed);const auto post=ik.PostPhysics(r.skeleton,{p.state_2508,p.category_2512,r.riding.ground.part_contact_count!=0,false,p.flags_2468,p.flags_2484,p.state_timer_2664,p.player_state_value_2520,r.roots.world_to_animation,observed});for(bool b:post)Out(std::uint32_t(b));r.skeleton.PublishPhysicalRecord(r.DeckFrame());if(!r.FinishFrame(error)){Out(0u);Out(error);return false;}
    }
    Out(1u);Out(std::string{});return true;
}
}
int main(int argc,char** argv)
{
    if(argc!=5)return 2;SettingsDatabase data;PhysicsSkeletons physical;AnimationPoseFrames frames;std::string error;if(!data.Load(FileBytes(argv[1]),error)||!physical.Load(FileBytes(argv[2]),argv[4],error)||!frames.rig.Load(FileBytes(argv[3]),error)){std::cerr<<error;return 2;}const auto* bank=physical.Find("PHYS_TPOSE");if(!bank)return 2;AnimationPoseEvaluator evaluator(std::move(frames));const auto settings=PhysicalSimulationSettings::Load(data,*bank,evaluator.frames.rig,error);const auto animated_settings=AnimatedSkeletonSettings::Load(data,*bank,evaluator.frames.rig,false,error);const auto wobble_settings=SkeletonWobbleSettings::Load(data,error);if(!settings||!animated_settings||!wobble_settings){std::cerr<<error;return 2;}
    Input i;const auto count=i.Word();for(unsigned c=0;c<count;++c)
    {
        const auto spawn=ReadAffine();auto world=ReadWorld(settings->board.floor_material);const bool seams=i.Word()!=0;auto value=PhysicalSimulationRuntime::Initialize(*settings,data,evaluator,std::move(world),spawn,error);if(!value){std::cerr<<error;return 2;}auto& r=*value;if(seams)r.EnableImportedFloorSeams();AnimatedSkeleton animated(*animated_settings);const auto loaded=FootIk::Load(data,evaluator.frames.rig,animated,error);auto runtime=SkeletonInputRuntime::Load(data,error);if(!loaded||!runtime){std::cerr<<error;return 2;}auto ik=*loaded;auto owner=*runtime;PhysicsAnimationInput input;if(!input.Load(data,evaluator.frames.rig,"normal",error)){std::cerr<<error;return 2;}SkeletonWobble wobble;bool elapsed=false;AdjustedFrame state;Actions actions;const auto n=i.Word();Out(c);Out(n);const auto mark=output.size();Out(0u);const auto initial=output.size();Out(0u);Snapshot(r);OutAdjusted(animated,ik,owner.grind_air,state.queries);ObserveDispatcher(owner,input,wobble,elapsed,state.input,actions);output[initial]=output.size()-initial-1;
        for(unsigned k=0;k<n;++k)
        {
            const auto op=i.Word();Out(op);const auto at=output.size();Out(0u);const auto owner_mark=output.size();Out(0u);switch(op)
            {
            case 0:{const auto status=output.size();Out(0u);const bool ok=ProcessDispatcher(i,r,animated,ik,owner,input,wobble,*wobble_settings,evaluator,state,actions);output[status]=std::uint32_t(ok);break;}
            case 1:owner.ResetForTeleport({r,animated,ik,input},wobble,elapsed);break;
            case 2:{const bool landing=i.Word()!=0,reverse=i.Word()!=0;wobble.Trigger(landing,reverse);break;}
            case 3:owner.reenable_requested=i.Word()!=0;owner.force_mode=i.Word();owner.head_tracking_active=i.Word()!=0;owner.grind_air_started=i.Word()!=0;owner.grind_air_active=i.Word()!=0;for(auto& v:owner.head_tracking_history)v=i.Floats<4>();break;
            case 4:{const auto limb=i.Word(),mode=i.Word();const auto v=i.Floats<8>();auto& l=ik.state.limbs[limb];auto& t=ik.state.external_targets[limb];l.target_blend=v[0];l.external_target_set=mode==1;l.local_target_set=mode==2;t.world_position=t.animation_position={v[1],v[2],v[3],0};t.normal={v[4],v[5],v[6],v[7]};t.normal_set=true;t.normal_blend=.6f;break;}
            case 5:{GrindAirTarget t;t.start=i.Floats<4>();t.end=i.Floats<4>();t.owner=i.Word();t.primitive_flags=i.Word();t.orientation.kind=i.Word();t.orientation.garbage=i.Word()!=0;t.orientation.boardslide_dir=i.Floats<4>();t.orientation.tipslide_dir=i.Floats<4>();t.orientation.backslash_dir=i.Floats<4>();t.orientation.high_side=i.Floats<4>();owner.grind_air.Start(t);break;}
            case 6:r.ReplaceWorld(ReadWorld(r.settings.board.floor_material));break;case 7:input.FinishOutputPublication();break;case 8:{error.clear();const bool ok=input.SelectPhysicsMode(i.Word(),error);Out(std::uint32_t(ok));Out(error);break;}case 9:{const auto flags=i.Word(),cool_down=i.Word();for(auto& body:r.skeleton.BodiesMut()){body.state_flags=flags;body.rates.cool_down=cool_down;}break;}default:std::abort();
            }
            output[owner_mark]=output.size()-owner_mark-1;Snapshot(r);OutAdjusted(animated,ik,owner.grind_air,state.queries);ObserveDispatcher(owner,input,wobble,elapsed,state.input,actions);output[at]=output.size()-at-1;
        }output[mark]=output.size()-mark-1;
    }if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:output)for(unsigned j=0;j<4;++j)std::cout.put(static_cast<char>(w>>(j*8)));
}
