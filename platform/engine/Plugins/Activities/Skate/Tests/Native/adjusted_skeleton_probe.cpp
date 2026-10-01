// SPDX-License-Identifier: Apache-2.0
// The checker prepends the accepted physical probe adapters, before main.
#include "FootIk.h"
#include "GrindAirPoseAdjustment.h"
#include "OffboardPoseAdjustment.h"
#include "SkeletonLineQueries.h"
namespace
{
void OutOffset(const SkateboardOffset& s){Out(s.transform);Out(s.orientation_frames);Out(s.height_frames);Out(std::uint32_t(s.orientation_refreshed));Out(std::uint32_t(s.height_refreshed));}
void OutLanding(const LandingAdjustment& s){Out(std::uint32_t(s.active));Out(s.kind);Out(s.time);Out(s.position);Out(s.velocity);Out(s.previous_com_velocity);Out(s.previous_animation_height);Out(s.previous_filtered_state);Out(s.desired_grind_com);}
void OutIk(const FootIk& ik)
{
    const auto& s=ik.state;Out(std::uint32_t(s.feet_enabled));
    for(const auto& l:s.limbs){Out(std::uint32_t(l.mode));Out(l.board_blend);Out(l.external_blend);Out(l.target_blend);Out(std::uint32_t(l.external_target_set));Out(std::uint32_t(l.local_target_set));Out(l.external_target_local_delta);Out(l.part_position);}
    for(const auto& l:s.frames){for(const auto& m:{l.target,l.world,l.external_world,l.board,l.parent_world,l.external_parent_world,l.parent_board})Out(m);Out(std::uint32_t(l.within_contact_bounds));}
    for(const auto& t:s.external_targets){Out(t.world_position);Out(t.animation_position);Out(t.normal);Out(std::uint32_t(t.normal_set));Out(t.normal_blend);}
    for(const auto& c:s.contacts.feet){Out(c.query_state);Out(c.position);Out(c.desired_offset);Out(c.offset);}Out(std::uint32_t(s.contacts.support_failed));Out(std::uint32_t(s.contacts.support_failed_this_update));
}
void OutGrind(const GrindAir& s){Out(s.offset_delta);Out(s.offset);Out(s.angle_delta);Out(s.angles);Out(std::uint32_t(s.selected_kind.has_value()));Out(std::uint32_t(s.selected_kind.value_or(0)));Out(s.headings);}
void OutPlayerQueries(const PlayerInputState& player){for(const auto& q:{player.hips_line_test_1488,player.left_line_test_1536,player.right_line_test_1584}){Out(q.position);Out(q.normal);Out(q.surface);Out(std::uint32_t(q.valid));}}
void OutAdjusted(const AnimatedSkeleton& a,const FootIk& ik,const GrindAir& grind,const PlayerInputState& queries)
{
    OutOffset(a.board_offset);OutLanding(a.landing);Out(a.targets);Out(a.animation_board);Out(a.unadjusted_board);Out(a.animation_hips);Out(a.motion.trajectory);Out(a.motion.inverse_trajectory);Out(a.motion.next_trajectory);Out(a.motion.velocity_world);Out(a.board_at_y_delta);OutIk(ik);OutGrind(grind);OutPlayerQueries(queries);
}
void OutLoaded(const AnimatedSkeleton& a,const FootIk& ik,const GrindAirSettings& g)
{
    const auto& s=a.settings;Out(s.masses);for(auto b:s.bone_indices)Out(std::uint32_t(b));Out(s.physics_frames);for(auto b:s.target_bones)Out(std::uint32_t(b));Out(s.landing_on_board_blend.x);Out(s.landing_on_board_blend.y);
    const auto& l=s.landing;for(const auto& p:{l.manual_blend,l.grind_blend,l.coffin_height}){Out(p.x);Out(p.y);}for(float v:{l.minimum_height,l.maximum_velocity,l.manual_damping,l.manual_spring,l.ground_minimum_compression_time,l.ground_damping,l.ground_spring,l.grind_animation_target_time,l.grind_damping,l.grind_spring,l.grind_target_delta,l.desired_com_height,l.coffin_time,l.coffin_maximum_velocity,l.coffin_blend_frames,l.coffin_base_height})Out(v);
    for(auto p:ik.geometry.parents)Out(p?std::uint32_t(*p):0xffffffffu);Out(ik.geometry.inverse_part_frames);const auto& q=ik.settings;Out(q.angle_limits.minimum_degrees);Out(q.angle_limits.maximum_degrees);Out(q.blend.hand_inner_padding);Out(q.blend.hand_outer_padding);Out(q.blend.external_blend_step);Out(q.blend.board_blend_step);Out(q.post_ik_padding);Out(q.contact_bounds);Out(q.foot_on_deck_padding);for(float v:{q.wipeout_feet_offset,q.deck_half_width,q.deck_half_length,q.deck_total_half_length,q.deck_front_angle_degrees,ik.post_settings.minimum_board_up,ik.post_settings.wipeout_height,ik.post_settings.riding_height})Out(v);for(auto b:ik.bone_indices)Out(std::uint32_t(b));
    Out(std::uint32_t(g.frames));Out(g.stomp);Out(g.points);Out(g.ranges);Out(g.distances);Out(g.yaw_assist);Out(g.max_offset);Out(g.max_delta);Out(g.max_angle);
}
std::vector<Mat4> Hierarchy(AnimationPoseEvaluator& evaluator,std::uint32_t kind)
{
    PoseCommand c;c.kind=PoseCommand::Kind::Pose;c.name=std::array<const char*,4>{{"RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"}}.at(kind);std::vector<Sqt> pose;std::vector<Mat4> globals;std::string error;if(!evaluator.Evaluate({c},pose,error)||!evaluator.Hierarchy(pose,globals,error)){std::cerr<<error;std::exit(2);}return globals;
}
RawVector Raw(Vec4 v){RawVector w;for(unsigned i=0;i<4;++i)std::memcpy(&w[i],&v[i],4);return w;}
struct AdjustedFrame {PlayerInputState queries;ProcessedPhysicsInput input{};};
void AdjustedOwnerError(std::uint32_t mode,PhysicalSimulationRuntime& r,AnimatedSkeleton& a,FootIk& ik,GrindAir& grind,const GrindAirSettings& settings,AnimationPoseEvaluator& evaluator,const SettingsDatabase& data)
{
    std::string error;bool ok=false;const AnimatedSkeletonOwners owners{r.animation_record,r.roots,r.board_frames};const auto globals=Hierarchy(evaluator,0);std::uint32_t flags2468=0,flags2472=0;
    if(mode<=2)
    {
        auto rig=evaluator.frames.rig;const auto original=a.settings.bone_indices[0];
        if(mode==0)a.settings.bone_indices[0]=std::size_t(-1);else if(mode==1)rig.bones[original].parent=static_cast<std::int32_t>(original);else for(auto& bone:rig.bones)bone.parent=-1;
        ok=FootIk::Load(data,rig,a,error).has_value();a.settings.bone_indices[0]=original;
    }
    else if(mode==3)ok=a.ProcessPose(owners,{},LandingInput{},1.0f/60.0f,flags2468,flags2472,std::nullopt,error);
    else if(mode==4){const auto old=a.settings.target_bones[0];a.settings.target_bones[0]=std::size_t(-1);ok=a.ProcessPose(owners,globals,LandingInput{},1.0f/60.0f,flags2468,flags2472,std::nullopt,error);a.settings.target_bones[0]=old;}
    else if(mode==5){ProcessedPhysicsInput p{};p.state_2508=201;std::array<Mat4,24> drives;ok=ik.Update(a,owners,{},p,std::size_t(-1),SkeletonIdentity,{},drives,error);}
    else if(mode==6||mode==7){ProcessedPhysicsInput p{};p.category_2512=500;p.state_2508=500;ok=UpdateOffboardPoseAdjustment(a,mode==6?std::vector<Mat4>{}:globals,{std::size_t(-1),std::size_t(-1)},p,error);}
    else if(mode==8||mode==9)
    {
        grind.target.reset();auto s=settings;if(mode==9){grind.Start(GrindAirTarget{});s.frames=1;}
        std::optional<GrindAirAdjustment> adjustment;ok=grind.Update({true,SkeletonIdentity,{},{},{0,1,0,0},1.0f/60.0f,0,0,0,0},s,adjustment,error);
    }
    else if(mode==10){const auto old=a.settings.bone_indices[23];a.settings.bone_indices[23]=std::size_t(-1);ok=a.ProcessPose(owners,globals,LandingInput{},1.0f/60.0f,flags2468,flags2472,std::nullopt,error);a.settings.bone_indices[23]=old;}
    else std::abort();Out(std::uint32_t(ok));Out(error);
}
void AdjustedTick(PhysicalSimulationRuntime& r,AnimatedSkeleton& animated,FootIk& ik,GrindAir& grind,const GrindAirSettings& grind_settings,AnimationPoseEvaluator& evaluator,AdjustedFrame& state)
{
    const auto pose=Word();auto& p=state.input;p.timestep_2604=Float();p.state_2508=Word();p.category_2512=Word();const auto filtered=Word();p.flags_2468=Word();p.flags_2472=Word();p.flags_2476=Word();p.flags_2480=Word();p.flags_2484=Word();const auto contact=Word();const float balance=Float(),spin=Float(),lift=Float();p.state_timer_2664=Float();const bool wipeout=Word()!=0,on_board=Word()!=0;const auto offset=Floats<4>();const float time=Float();const bool grind_active=Word()!=0;
    p.line_tests_960_1008_1056={state.queries.left_line_test_1536,state.queries.right_line_test_1584,state.queries.hips_line_test_1488};p.player_state_value_2520=filtered;
    std::string error;SkeletonLineTests lines;const AnimatedSkeletonOwners owners{r.animation_record,r.roots,r.board_frames};
    if(!r.BeginBoardQueries(error)||!QuerySkeletonLines(r.world,r.skeleton,lines,error)){std::cerr<<error;std::exit(2);}const auto globals=Hierarchy(evaluator,pose);
    if(!UpdateOffboardPoseAdjustment(animated,globals,animated.ReparentedHandIndices(),p,error)){std::cerr<<error;std::exit(2);}
    p.vectors_400_416[0]=Raw(Four(r.board.Bodies()[6].rates.linear_velocity));p.vectors_720_784_800_816_832_864[0]=Raw(Four(r.board.Bodies()[6].rates.angular_velocity));p.vectors_544_560_592_608[0]=Raw({0,1,0,0});
    bool adjusted=false;if(grind_active&&!UpdateGrindAirPoseAdjustment(grind,grind_settings,r.DeckFrame(),p,animated,owners,globals,adjusted,error)){std::cerr<<error;std::exit(2);}
    const Vec4 com=r.skeleton.record.centre_of_mass,velocity=r.skeleton.record.centre_of_mass_velocity;const float height=com[1]-r.DeckFrame()[3][1];
    const LandingInput landing{filtered,p.flags_2468,p.flags_2472,p.flags_2476,balance,velocity[1],height,0};const auto on=on_board?std::optional<LandingOnBoardPoseInput>({r.DeckFrame(),offset,p.flags_2480,time}):std::nullopt;
    if(!animated.ProcessPose(owners,globals,landing,p.timestep_2604,p.flags_2468,p.flags_2472,on,error)){std::cerr<<error;std::exit(2);}
    r.deck_velocity=Four(r.board.Bodies()[6].rates.linear_velocity);for(auto& b:r.skeleton.BodiesMut()){if((b.state_flags&7)==2)b.state_flags=(b.state_flags&8)|4;b.rates.cool_down=0;}
    if(!r.FinishBoardQueries(error)){std::cerr<<error;std::exit(2);}
    // GroundPacketInputs reads the retained Processed528 publication. The
    // current collision normal is a separate observation, published below;
    // it must not replace that retained field before the reckoning call.
    p.wheel_count_2556=std::uint32_t(r.riding.ground.wheel_contact_count);p.scalar_2652=r.riding.motion.speed;p.scalar_2616=r.riding.motion.ground_speed;p.vectors_464_480_496_512_528[0]=Raw(Four(r.riding.ground.wheel_normal));
    const auto collision_dynamic_up=r.riding.ground.overall_normal;Vec4 retained_dynamic_up;for(unsigned lane=0;lane<4;++lane)std::memcpy(&retained_dynamic_up[lane],&p.vectors_464_480_496_512_528[4][lane],4);
    const PhysicalGroundPacket packet{r.riding.ground.wheel_normal,{retained_dynamic_up[0],retained_dynamic_up[1],retained_dynamic_up[2]},r.riding.motion.speed,r.riding.motion.ground_speed,r.riding.ground.wheel_contact_count};
    r.processed_flags_2468=p.flags_2468;r.riding.UpdateGroundReckoning(r.board,{r.animation_record.ComToDeck(),spin},p.flags_2468,balance,false,packet);r.board_frames.UpdateComLift(r.roots.animation_to_world,animated.animation_hips[3],lift);r.PrepareGroundSkeleton(animated.animation_board,r.riding.reckoning_frames.system,p.timestep_2604);r.UpdateRootDerivative(p.timestep_2604);
    const auto targets=r.UpdateTargetPositions(animated.animation_hips,animated.animation_board,false);if(!targets.continuous){r.ResetPhysicalPose();if(p.state_2508!=0&&p.state_2508!=702)r.invalid_target_reset=true;}
    std::array<Mat4,24> drives;if(!ik.Update(animated,owners,globals,p,contact==2?std::size_t(-1):animated.settings.bone_indices[contact==0?15:19],r.board_frames.physical_board,r.skeleton.record.pose[23][3],drives,error)){std::cerr<<error;std::exit(2);}r.UpdateBoneDrives(drives);r.ApplySkeletonGravity(9.81f);animated.FinishGround();lines.Publish(state.queries);
    if(!r.Solve({0,0},error)){std::cerr<<error;std::exit(2);}r.FinishBoardOutputs({p.state_2508,packet.wheel_normal,{r.roots.animation_to_world[1][0],r.roots.animation_to_world[1][1],r.roots.animation_to_world[1][2]}, {r.DeckFrame()[3][0],r.DeckFrame()[3][1],r.DeckFrame()[3][2]},float(r.ticks)*p.timestep_2604});
    p.vectors_544_560_592_608[0]=Raw(r.roots.animation_to_world[1]);p.time_on_ground_2752=float(r.ticks)*p.timestep_2604;
    PhysicalFeedbackInput feedback{p.state_2508,p.category_2512,p.flags_2472,p.flags_2480,{},{}};feedback.vectors_464_480_496_512_528[0]=Four(packet.wheel_normal);feedback.vectors_464_480_496_512_528[1]=feedback.vectors_464_480_496_512_528[2]=Four(r.riding.ground.parts[6].point);feedback.vectors_464_480_496_512_528[4]=Four(collision_dynamic_up);feedback.vectors_880_896_912_928_944[0]=animated.animation_hips[3];feedback.vectors_880_896_912_928_944[1]={0,1,0,0};
    for(unsigned field:{1u,2u,4u})p.vectors_464_480_496_512_528[field]=Raw(feedback.vectors_464_480_496_512_528[field]);for(unsigned field:{0u,1u})p.vectors_880_896_912_928_944[field]=Raw(feedback.vectors_880_896_912_928_944[field]);r.PublishFeedback(feedback);
    const auto post=ik.PostPhysics(r.skeleton,{p.state_2508,p.category_2512,r.riding.ground.part_contact_count!=0,wipeout,p.flags_2468,p.flags_2484,p.state_timer_2664,p.player_state_value_2520,r.roots.world_to_animation,r.DeckFrame()});
    r.skeleton.PublishPhysicalRecord(r.DeckFrame());for(bool b:post)Out(std::uint32_t(b));Out(ik.PhysicalToePositions(r.skeleton.record));Out(std::uint32_t(lines.hips.hit));Out(std::uint32_t(lines.feet[0].hit));Out(std::uint32_t(lines.feet[1].hit));Out(std::uint32_t(adjusted));if(!r.FinishFrame(error)){std::cerr<<error;std::exit(2);}
}
}
int main(int argc,char** argv)
{
    if(argc!=5)return 2;SettingsDatabase data;PhysicsSkeletons physical;AnimationPoseFrames frames;std::string error;
    if(!data.Load(FileBytes(argv[1]),error)||!physical.Load(FileBytes(argv[2]),argv[4],error)||!frames.rig.Load(FileBytes(argv[3]),error)){std::cerr<<error;return 2;}const auto* skeleton=physical.Find("PHYS_TPOSE");if(!skeleton)return 2;
    AnimationPoseEvaluator evaluator(std::move(frames));const auto settings=PhysicalSimulationSettings::Load(data,*skeleton,evaluator.frames.rig,error);const auto animation_settings=AnimatedSkeletonSettings::Load(data,*skeleton,evaluator.frames.rig,false,error);const auto grind_settings=GrindAirSettings::Load(data,error);if(!settings||!animation_settings||!grind_settings){std::cerr<<error;return 2;}
    const auto cases=Word();for(std::uint32_t c=0;c<cases;++c)
    {
        const auto spawn=ReadAffine();auto world=ReadWorld(settings->board.floor_material);const bool seams=Word()!=0;auto runtime=PhysicalSimulationRuntime::Initialize(*settings,data,evaluator,std::move(world),spawn,error);if(!runtime){std::cerr<<error;return 2;}auto& r=*runtime;if(seams)r.EnableImportedFloorSeams();AnimatedSkeleton animated(*animation_settings);auto loaded=FootIk::Load(data,evaluator.frames.rig,animated,error);if(!loaded){std::cerr<<error;return 2;}auto ik=*loaded;GrindAir grind;AdjustedFrame state;const auto commands=Word();Out(c);Out(commands);const auto mark=output.size();Out(0u);const auto initial=output.size();Out(0u);Snapshot(r);OutLoaded(animated,ik,*grind_settings);OutAdjusted(animated,ik,grind,state.queries);output[initial]=output.size()-initial-1;
        for(unsigned k=0;k<commands;++k)
        {
            const auto op=Word();Out(op);const auto at=output.size();Out(0u);
            switch(op)
            {
            case 0:AdjustedTick(r,animated,ik,grind,*grind_settings,evaluator,state);break;
            case 1:ik.EnableFeet(Word()!=0);break;case 2:ik.state.Reset();break;case 3:animated.board_offset.RefreshTransform(Matrix());break;
            case 4:{const float height=Float(),frames=Float();animated.board_offset.RefreshHeight(height,frames);break;}
            case 5:animated.FinishGround();break;case 6:animated.motion.ResetBoardOrientationHistory();break;
            case 7:{const auto limb=Word(),mode=Word();const auto v=Floats<8>();if(limb>=4)std::abort();auto& l=ik.state.limbs[limb];auto& t=ik.state.external_targets[limb];l.target_blend=v[0];l.external_target_set=mode==1;l.local_target_set=mode==2;t.world_position=t.animation_position={v[1],v[2],v[3],0};t.normal={v[4],v[5],v[6],v[7]};t.normal_set=true;t.normal_blend=.6f;break;}
            case 8:{GrindAirTarget target;target.start=Floats<4>();target.end=Floats<4>();target.owner=Word();target.primitive_flags=Word();target.orientation.kind=Word();target.orientation.garbage=Word()!=0;target.orientation.boardslide_dir=Floats<4>();target.orientation.tipslide_dir=Floats<4>();target.orientation.backslash_dir=Floats<4>();target.orientation.high_side=Floats<4>();grind.Start(target);break;}
            case 9:r.ReplaceWorld(ReadWorld(r.settings.board.floor_material));break;
            case 10:r.roots.supplied_prediction=Floats<4>();ik.state.MarkSupportFailedThisUpdate();break;
            case 11:{const auto root=Floats<4>(),middle=Floats<4>(),end=Floats<4>();auto solved=Floats<4>(),target=Floats<4>();const foot_ik::AngleLimits limits{Float(),Float()};const bool override=Word()!=0;const auto budget=Word();Out(std::uint32_t(foot_ik::SolveTwoBone(root,middle,end,solved,target,limits,override,budget)));Out(solved);Out(target);break;}
            case 12:{std::array<std::optional<std::size_t>,24> parents;for(auto& p:parents){const auto v=Word();if(v!=0xffffffffu)p=v;}std::array<Mat4,24> frames;for(auto& m:frames)m=Matrix();const auto geometry=foot_ik::Geometry::Create(parents,frames,error);Out(std::uint32_t(geometry.has_value()));Out(error);if(geometry){for(auto p:geometry->parents)Out(p?std::uint32_t(*p):0xffffffffu);Out(geometry->inverse_part_frames);error.clear();Out(std::uint32_t(geometry->ValidateLimbs(foot_ik::Limbs,error)));Out(error);}break;}
            case 13:AdjustedOwnerError(Word(),r,animated,ik,grind,*grind_settings,evaluator,data);break;
            default:std::abort();
            }
            Snapshot(r);OutAdjusted(animated,ik,grind,state.queries);output[at]=output.size()-at-1;
        }
        output[mark]=output.size()-mark-1;
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:output)for(unsigned i=0;i<4;++i)std::cout.put(static_cast<char>(w>>(8*i)));
}
