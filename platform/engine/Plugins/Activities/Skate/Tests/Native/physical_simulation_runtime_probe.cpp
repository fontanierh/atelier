// The checker prepends the tested skeleton record adapters.
#include "PhysicalSimulationRuntime.h"
#include <fstream>
#include <iterator>
namespace
{
std::vector<std::uint8_t> FileBytes(const char* path){std::ifstream f(path,std::ios::binary);return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(f),{});}
AffineTransform ReadAffine(){AffineTransform t;for(auto& c:t.basis.columns)c=Floats<3>();t.translation=Vector();return t;}
void OutAffine(AffineTransform t){Out(t.basis);Out(t.translation);}
Vec4 Four(Vec3 v){return {v.x,v.y,v.z,0};}
WorldGeometry ReadWorld(ContactMaterial material)
{
    std::vector<WorldTriangle> triangles;const auto n=Word();
    for(std::uint32_t k=0;k<n;++k){const std::array<Vec3,3> v{Vector(),Vector(),Vector()};const float fat=Float();const auto flags=Word(),tag=Word();triangles.push_back({TriangleFromVolume(v,fat,{1,1,1},flags),material,tag});}
    return WorldGeometry(std::move(triangles));
}
void OutRoots(const SkeletonRootFrames& r)
{
    Out(r.board);Out(r.inverse_board);Out(r.previous_board_position);Out(r.predicted_board_position);Out(std::uint32_t(r.supplied_prediction.has_value()));Out(r.supplied_prediction.value_or(Vec4{}));
    Out(r.animation_to_board);Out(r.animation_to_world);Out(r.world_to_animation);Out(r.heading_alignment);Out(std::uint32_t(r.initialize_heading));
}
void OutBoardFrames(const SkeletonBoardFrames& b)
{for(const auto& m:{b.physical_board,b.skate_root,b.animation_target,b.com_frame,b.lifted_com_frame})Out(m);for(const auto& v:{b.centre_of_mass,b.previous_centre_of_mass,b.com_velocity,b.local_centre_of_mass,b.local_board_position})Out(v);Out(b.lift_height);}
void OutGround(const PhysicalRidingOutputs& r)
{
    const auto& w=r.wheel_lines;const auto& g=r.ground;Out(w.normals);Out(w.distances);Out(w.physics_surfaces);Out(w.minimum_distance);
    for(const auto& c:g.parts){Out(std::uint32_t(c.in_contact));Out(c.normal);Out(c.point);Out(c.relative_velocity);}Out(g.previous_velocities);Out(g.accelerations);Out(g.closing_velocity);
    Out(g.maximum_closing_speed);Out(g.opposing_contact);Out(g.surface_twelve_height);Out(g.collision_flags);Out(g.overall_normal);Out(g.wheel_normal);for(auto v:g.valid_wheel_normals)Out(std::uint32_t(v));
    Out(std::uint32_t(g.part_contact_count));Out(std::uint32_t(g.wheel_contact_count));Out(g.time_without_wheel_contact);Out(g.wheel_angular_drag);
    for(const auto& p:{r.probes.deck,r.probes.wall}){Out(p.start);Out(p.point);Out(p.normal);Out(p.surface_tag);Out(std::uint32_t(p.hit));}
    const auto& o=r.reckoning;for(const auto& v:{o.dynamic_up,o.up,o.target,o.up_velocity,o.ground_normal})Out(v);Out(o.ground_blend);Out(o.ground_filter.words);Out(o.slow_filter.words);Out(o.fast_filter.words);
    const auto& f=r.reckoning_frames;for(const auto& m:{f.ground,f.system,f.unflipped,f.inverse_system,f.body_flip})Out(m);Out(f.heading);Out(f.target_lean_angle);Out(f.lateral_tilt);Out(r.body_spin);
    const auto& m=r.motion;Out(m.angular_velocity);Out(m.linear_velocity);Out(m.ground_velocity);Out(m.speed);Out(m.ground_speed);Out(m.forward_speed);Out(m.effective_basis);Out(r.heading_adjust_factor);
}
void OutBatch(const SkeletonDriveBatch& b)
{
    Out(std::uint32_t(b.rows.size()));for(std::size_t i=0;i<b.rows.size();++i){const auto p=PackDrive(b.rows[i]);Out(p.words);Out(std::uint32_t(p.reaction_a));Out(std::uint32_t(p.reaction_b));const auto id=b.identities[i];Out(std::uint32_t(id.kind));Out(std::uint32_t(id.index));Out(std::uint32_t(id.channel));Out(std::uint32_t(b.spy[i]));}
}
struct FrameContext {BoardPossessionProcessed processed{};std::optional<Mat4> toolkit;float dt=1.0f/60.0f;};
void OutPossessionFill(BoardPossessionFill f){Out(f.angle_36);Out(f.angle_40);for(bool b:{f.held_311,f.free_312,f.returning_313,f.hiding_321,f.flag_322,f.flag_323,f.flag_324})Out(std::uint32_t(b));}
void OutPossessionLive(const PhysicalSimulationRuntime& r)
{
    const auto& c=r.settings.board.collision;for(const auto& m:{c.wheel_material,c.truck_material,c.deck_material}){Out(m.static_friction);Out(m.dynamic_friction);Out(m.restitution);}Out(std::uint32_t(c.truck_collisions));Out(std::uint32_t(c.deck_geometry.children.size()));for(const auto& child:c.deck_geometry.children)Out(std::uint32_t(child.collision_enabled));
    const auto& l=r.possession_live;Out(std::uint32_t(l.volumes.deck));Out(std::uint32_t(l.volumes.trucks));Out(std::uint32_t(l.volumes.wheels));Out(std::uint32_t(l.volumes.deck_children.size()));for(bool child:l.volumes.deck_children)Out(std::uint32_t(child));
    Out(l.alignment.first_1008);Out(l.alignment.second_1024);Out(l.alignment.factor_1040);Out(std::uint32_t(l.alignment.flag_1044));Out(std::uint32_t(l.alignment_active));for(const auto& m:l.standard_materials){Out(m.static_friction);Out(m.dynamic_friction);Out(m.restitution);}Out(l.released_material.static_friction);Out(l.released_material.dynamic_friction);Out(l.released_material.restitution);Out(l.standard_drag);Out(std::uint32_t(l.output.has_value()));if(l.output)OutPossessionFill(*l.output);
}
void Snapshot(const PhysicalSimulationRuntime& r)
{
    for(const auto& b:r.board.Bodies())Out(b);Out(r.board.Hook().body);Out(r.board.Hook().drive.frames);Out(r.board.Hook().drive.dynamics);for(const auto& p:r.board.PartTransforms())OutAffine(p);OutAffine(r.board.HookTransform());Out(r.board.CollisionGroup());
    Out(r.skeleton);OutDrives(r.skeleton_drives);OutMode(r.skeleton_collision);OutFeedback(r.collision_feedback);OutErrors(r.pose_errors);OutRoots(r.roots);OutBoardFrames(r.board_frames);Out(r.animation_record);
    Out(r.deck_velocity);Out(r.root_velocity);Out(r.previous_root_position);Out(r.reset_local_hips);Out(std::uint32_t(r.invalid_target_reset));Out(r.animation_board_to_physics);Out(r.extra_target_positions);Out(r.drive_frames);
    Out(r.correction.board_prediction_error);Out(std::uint32_t(r.correction.pending));Out(r.collision_pose_error);Out(r.collision_extra_errors);Out(std::uint32_t(r.collision_maximum_error.has_value()));Out(r.collision_maximum_error.value_or(0));
    Out(std::uint32_t(r.solved_drives.has_value()));if(r.solved_drives)OutBatch(*r.solved_drives);
    Out(std::uint32_t(r.board.SolvedContacts().size()));for(const auto& c:r.board.SolvedContacts()){Out(c.words);Out(std::uint32_t(c.reaction_a));Out(std::uint32_t(c.reaction_b));}
    OutGround(r.riding);Out(std::uint32_t(r.contact_count));Out(std::uint32_t(r.network_contacts));Out(std::uint32_t(r.ticks));Out(std::uint32_t(r.ticks>>32));Out(r.processed_flags_2468);Out(std::uint32_t(r.board_wiping_out));Out(std::uint32_t(r.failed));
    Out(r.controller_fields.word_444);Out(r.controller_fields.state_448);Out(std::uint32_t(r.controller_fields.system_on_452));const auto& p=r.possession.state;Out(p.retrieval.initial_0);Out(p.retrieval.target_64);Out(p.retrieval.current_128);Out(p.retrieval.elapsed_192);Out(p.retrieval.duration_196);Out(p.retrieval.progress_200);Out(p.retrieval.weight_204);for(const auto& h:p.hands){Out(h.child);Out(h.parent);Out(h.dynamics);}Out(p.selected_hand_424);
    Out(std::uint32_t(r.network_proxies.bodies.size()));for(const auto& b:r.network_proxies.bodies)Out(b);OutPossessionLive(r);
}
std::array<Mat4,24> Pose(AnimationPoseEvaluator& evaluator,const PhysicalSimulationSettings& s,std::uint32_t kind)
{
    const std::array<const char*,4> names{"RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"};PoseCommand command;command.kind=PoseCommand::Kind::Pose;command.name=names.at(kind);std::vector<Sqt> pose;std::vector<Mat4> hierarchy;std::string error;std::array<Mat4,24> mapped;
    if(!evaluator.Evaluate({command},pose,error)||!evaluator.Hierarchy(pose,hierarchy,error)||!MapAnimationParts(hierarchy,s.bone_indices,s.physics_frames,mapped,error)){std::cerr<<error;std::exit(2);}return mapped;
}
void Tick(PhysicalSimulationRuntime& r,AnimationPoseEvaluator& evaluator,std::uint8_t& animated,FrameContext& context)
{
    const auto pose_kind=Word();const float dt=Float();r.settings.board.step.iterations=Word();r.processed_flags_2468=Word();
    PhysicalFeedbackInput input{};input.state_2508=Word();input.category_2512=Word();input.flags_2472=Word();input.flags_2480=Word();const auto flags2476=Word(),flags2488=Word();const float spin=Float(),balance=Float();const bool coffin=Word()!=0;const float lift=Float();
    const auto force=Vector(),point=Vector();const std::array<float,2> targets{Float(),Float()};const float gravity=Float();std::string error;
    if(!r.BeginBoardQueries(error)){Out(0u);Out(error);return;}const auto mapped=Pose(evaluator,r.settings,pose_kind);r.animation_record.Update(mapped,r.roots.animation_to_board,r.skeleton.definition.animation_masses);
    r.deck_velocity=Four(r.board.Bodies()[6].rates.linear_velocity);for(auto& b:r.skeleton.BodiesMut()){if((b.state_flags&7)==2)b.state_flags=(b.state_flags&8)|4;b.rates.cool_down=0;}
    if(!r.FinishBoardQueries(error)){Out(0u);Out(error);return;}
    const PhysicalGroundPacket packet{r.riding.ground.wheel_normal,r.riding.ground.overall_normal,r.riding.motion.speed,r.riding.motion.ground_speed,r.riding.ground.wheel_contact_count};
    input.vectors_464_480_496_512_528[0]=Four(packet.wheel_normal);input.vectors_464_480_496_512_528[1]=input.vectors_464_480_496_512_528[2]=Four(r.riding.ground.parts[6].point);input.vectors_464_480_496_512_528[4]=Four(packet.dynamic_up);
    input.vectors_880_896_912_928_944[0]=mapped[23][3];input.vectors_880_896_912_928_944[1]={0,1,0,0};
    r.riding.UpdateGroundReckoning(r.board,{r.animation_record.ComToDeck(),spin},r.processed_flags_2468,balance,coffin,packet);
    r.board_frames.UpdateComLift(r.roots.animation_to_world,mapped[23][3],lift);r.PrepareGroundSkeleton(mapped[0],r.riding.reckoning_frames.system,dt);r.UpdateRootDerivative(dt);
    const auto update=r.UpdateTargetPositions(mapped[23],mapped[0],false);if(!update.continuous){r.ResetPhysicalPose();if(input.state_2508!=0&&input.state_2508!=702)r.invalid_target_reset=true;}r.UpdateBoneDrives(mapped);r.ApplySkeletonGravity(gravity);
    r.board.ForcesMut().Append({std::uint32_t(r.ticks),force,point});const auto cached=r.DeckFrame();BoardPossessionProcessed possession_input{cached,r.roots.animation_to_world,r.skeleton.record.centre_of_mass,{},mapped[0][2],input.vectors_464_480_496_512_528[0],0,0,0};possession_input.flags_2476=flags2476;possession_input.flags_2480=input.flags_2480;possession_input.flags_2488=flags2488;context={possession_input,cached,dt};r.UpdatePossession(possession_input,cached,animated,dt);
    if(!r.Solve(targets,error)){Out(0u);Out(error);return;}
    r.FinishBoardOutputs({input.state_2508,packet.wheel_normal,{r.roots.animation_to_world[1][0],r.roots.animation_to_world[1][1],r.roots.animation_to_world[1][2]}, {cached[3][0],cached[3][1],cached[3][2]},float(r.ticks)*dt});r.PublishFeedback(input);r.PublishPossession(possession_input,cached);const bool ok=r.FinishFrame(error);Out(std::uint32_t(ok));if(!ok)Out(error);
}
void AppendProxy(PhysicalSimulationRuntime& r)
{
    const auto offset=Vector();const float age=Float();const auto q=Floats<4>();const auto lo=Word(),hi=Word();NetworkBodyState frame;frame.root={{},q};frame.enabled=std::uint64_t(lo)|(std::uint64_t(hi)<<32);
    for(const auto& b:r.board.Bodies())frame.bodies.push_back({{{b.rates.position.x+offset.x,b.rates.position.y+offset.y,b.rates.position.z+offset.z},q},{}, {}});
    for(const auto& b:r.skeleton.Bodies())frame.bodies.push_back({{{b.rates.position.x+offset.x,b.rates.position.y+offset.y,b.rates.position.z+offset.z},q},{}, {}});
    auto volumes=BoardWorldVolumes(r.board,r.settings.board.collision);SkeletonCollisionMode mode(r.settings.collision,false);for(auto& p:mode.parts){p.enabled=true;p.volume_group=0;}std::string error;const auto rider=SkeletonWorldVolumes(r.skeleton,mode,error);if(!rider)std::abort();volumes.insert(volumes.end(),rider->begin(),rider->end());
    const auto schema=NetworkCollisionSchema::FromWorldVolumes(volumes,r.board.Bodies(),r.skeleton.Bodies(),0);r.network_proxies.Append(frame,schema,{r.board.Bodies(),r.skeleton.Bodies(),r.settings.board.masses,r.skeleton.definition,4},age);
}
}
int main(int argc,char** argv)
{
    if(argc!=5)return 2;std::string error;SettingsDatabase database;PhysicsSkeletons physical;AnimationPoseFrames frames;
    if(!database.Load(FileBytes(argv[1]),error)||!physical.Load(FileBytes(argv[2]),argv[4],error)||!frames.rig.Load(FileBytes(argv[3]),error)){std::cerr<<error;return 2;}const auto* bank=physical.Find("PHYS_TPOSE");if(!bank)return 2;
    AnimationPoseEvaluator evaluator(std::move(frames));const auto settings=PhysicalSimulationSettings::Load(database,*bank,evaluator.frames.rig,error);if(!settings){std::cerr<<error;return 2;}
    const auto cases=Word();for(std::uint32_t c=0;c<cases;++c)
    {
        const auto spawn=ReadAffine();auto world=ReadWorld(settings->board.floor_material);const bool seams=Word()!=0;auto value=PhysicalSimulationRuntime::Initialize(*settings,database,evaluator,std::move(world),spawn,error);if(!value){std::cerr<<error;return 2;}auto& r=*value;if(seams)r.EnableImportedFloorSeams();std::uint8_t animated=0;FrameContext context;
        const auto n=Word();Out(c);Out(n);const auto mark=output.size();Out(0u);const auto initial=output.size();Out(0u);Snapshot(r);output[initial]=std::uint32_t(output.size()-initial-1);
        for(std::uint32_t k=0;k<n;++k)
        {
            const auto op=Word();Out(op);const auto at=output.size();Out(0u);
            if(op==0)Tick(r,evaluator,animated,context);
            else if(op==1){const bool ok=r.BeginBoardQueries(error);Out(std::uint32_t(ok));if(!ok)Out(error);}
            else if(op==2){const bool ok=r.FinishBoardQueries(error);Out(std::uint32_t(ok));if(!ok)Out(error);}
            else if(op==3)r.riding.ResetForTeleport();
            else if(op==4)r.ReplaceWorld(ReadWorld(r.settings.board.floor_material));
            else if(op==5){const bool ok=r.skeleton_collision.SelectDriven(Word(),error);Out(std::uint32_t(ok));if(!ok)Out(error);}
            else if(op==6){r.correction.pending=Word()!=0;const auto flags=Word(),flags2476=Word();r.correction.Apply(r.skeleton,Four(r.riding.reckoning.ground_normal),Word()!=0,flags,flags2476);}
            else if(op==7){r.controller_fields={Word(),Word(),Word()!=0};}
            else if(op==8)AppendProxy(r);
            else if(op==9)r.network_proxies={};
            else if(op==10){const BoardPossessionObserveInput input{context.processed,context.toolkit,r.riding.ground,r.riding.wheel_lines,r.skeleton.record,r.collision_feedback,r.drive_frames,r.roots.animation_to_world};const auto o=ObserveBoardPossession(r.board,input);LiveBoardPossessionEffects effects(r.board,animated,r.board_wiping_out,r.possession_live,r.settings.board.collision,context.dt);r.possession.Hold(r.controller_fields,o,effects);r.possession_live.PublishVolumes(r.settings.board.collision);}
            else return 2;
            Snapshot(r);for(std::uint32_t stat:{std::uint32_t(r.contact_count),std::uint32_t(r.network_contacts),std::uint32_t(r.board.SolvedContacts().size()),std::uint32_t(r.solved_drives?r.solved_drives->rows.size():0),std::uint32_t(r.network_proxies.bodies.size()),std::uint32_t(r.riding.ground.part_contact_count),std::uint32_t(r.riding.ground.wheel_contact_count),std::uint32_t(animated)})Out(stat);output[at]=std::uint32_t(output.size()-at-1);
        }output[mark]=std::uint32_t(output.size()-mark-1);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:output)for(unsigned i=0;i<4;++i)std::cout.put(char(w>>(8*i)));
}
