// SPDX-License-Identifier: Apache-2.0
#include "PhysicalSimulationRuntime.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float PhysicalFloat(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::uint32_t PhysicalWord(float value){std::uint32_t word;std::memcpy(&word,&value,4);return word;}
Vec4 Lanes(Vec3 v){return {v.x,v.y,v.z,0.0f};}
Vec3 Xyz(Vec4 v){return {v[0],v[1],v[2]};}
Vec3 Column(const Mat4& m,std::size_t i){return Xyz(m[i]);}
Vec3 BasisColumn(Basis3 b,std::size_t i){const auto& c=b.columns[i];return {c[0],c[1],c[2]};}
Vec3 PhysicalAdd(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
float Select(float test,float positive,float negative){return test>=-0.0f?positive:negative;}
Vec3 PhysicalCross(Vec3 a,Vec3 b)
{return {std::fma(-a.z,b.y,a.y*b.z),std::fma(-a.x,b.z,a.z*b.x),std::fma(-a.y,b.x,a.x*b.y)};}
Vec3 SafeNormal(Vec3 value,Vec3 fallback)
{
    const float squared=Dot3(value,value),inverse=InverseLengthSquared(squared,2);
    const float magnitude=squared==0.0f?0.0f:squared*inverse;
    return magnitude>PhysicalFloat(0x358637bd)?Scale(value,inverse):fallback;
}
Vec3 PhysicalBlend(Vec3 from,Vec3 to,float amount){return Madd(to,amount,Scale(from,1.0f-amount));}
float UnitSaturate(float value){value=Select(-value,0.0f,value);return Select(1.0f-value,value,1.0f);}
Vec3 ClampLength(Vec3 value,float maximum)
{
    const float magnitude=Length3(value);if(magnitude<PhysicalFloat(0x37800000))return value;
    const float bounded=Select(maximum-magnitude,magnitude,maximum);
    float inverse=ReciprocalEstimate(magnitude);for(unsigned i=0;i<2;++i){const float error=std::fma(-inverse,magnitude,1.0f);inverse=std::fma(inverse,error,inverse);}
    return Scale(Scale(value,bounded),inverse);
}
void GroundBodySpin(std::array<std::uint32_t,44>& words,float input)
{
    const auto get=[&](std::size_t offset){return PhysicalFloat(words[offset/4]);};
    const auto set=[&](std::size_t offset,float v){words[offset/4]=PhysicalWord(v);};
    const float delta=input-get(120),derivative=std::fma(delta,1.5f,get(124)*0.0f);
    set(164,0.0f);set(120,input);words[43]&=0x00ffffff;set(124,derivative);
    float filtered=derivative*input>0.1f?derivative:0.0f;
    filtered=Select(-1.0f-filtered,-1.0f,filtered);filtered=Select(1.0f-filtered,filtered,1.0f);set(128,filtered);
    const auto index=words[42];if(index>=30)std::abort();set(index*4,filtered);words[42]=(index+1)%30;
    set(152,0.0f);set(144,0.0f);set(140,0.0f);set(132,std::fma(get(132),0.8f,input*0.2f));
}
std::optional<BoardProbeHit> ProbeHit(const WorldLineQueryResult& result)
{if(!result.hit)return std::nullopt;return BoardProbeHit{result.hit->geometry.position,result.hit->geometry.normal,result.hit->tag};}
const char* FieldName(PhysicalSimulationDiagnostic::Field field)
{
    using F=PhysicalSimulationDiagnostic::Field;
    switch(field){case F::Position:return "position";case F::LinearVelocity:return "linear_velocity";case F::AngularVelocity:return "angular_velocity";case F::ForceAcceleration:return "force_acceleration";case F::TorqueAcceleration:return "torque_acceleration";case F::OrientationInertia:return "orientation/inertia";}std::abort();
}
}
GroundNormalFilter GroundNormalFilter::Initialized(Vec4 control,Vec4 initial)
{
    GroundNormalFilter f;for(unsigned i=0;i<4;++i){f.words[i]=PhysicalWord(control[i]);f.words[4+i]=PhysicalWord(initial[i]);f.words[8+i]=PhysicalWord(initial[i]);}return f;
}
void GroundNormalFilter::PublishCurrent(Vec4 current){for(unsigned i=0;i<4;++i)words[4+i]=PhysicalWord(current[i]);}
Vec4 GroundNormalFilter::Filter(Vec4 input)
{
    std::array<float,24> previous;for(unsigned i=0;i<24;++i)previous[i]=PhysicalFloat(words[i]);
    const float blend=previous[3],retained=1.0f-blend;Vec4 output{};
    for(unsigned i=0;i<4;++i)
    {
        const float error=input[i]-previous[4+i],error_blend=std::fma(previous[12+i],retained,error*blend);
        const float input_delta=input[i]-previous[8+i],input_blend=std::fma(previous[20+i],retained,input_delta*blend);
        const float first=std::fma(error_blend,previous[1],previous[4+i]),predicted=std::fma(error,previous[0],first);
        output[i]=std::fma(input_blend-previous[16+i],previous[2],predicted);
        words[12+i]=PhysicalWord(error_blend);words[20+i]=PhysicalWord(input_blend);words[16+i]=PhysicalWord(output[i]-previous[4+i]);words[4+i]=PhysicalWord(output[i]);words[8+i]=PhysicalWord(input[i]);
    }return output;
}
Vec4 GroundNormalFilter::FilterRaw(Vec4 control,Vec4 input){for(unsigned i=0;i<4;++i)words[i]=PhysicalWord(control[i]);return Filter(input);}
Vec4 GroundNormalFilter::Update(Vec4 control,Vec4 input)
{
    for(unsigned i=0;i<4;++i)words[i]=PhysicalWord(control[i]);const auto filtered=Filter(input);const float squared=Dot3(filtered,filtered);
    float inverse=ReciprocalSquareRootEstimate(squared);
    for(unsigned i=0;i<2;++i){const float correction=std::fma(-squared,inverse*inverse,1.0f);inverse=std::fma(inverse*0.5f,correction,inverse);}
    Vec4 normal;for(unsigned i=0;i<4;++i)normal[i]=filtered[i]*inverse;PublishCurrent(normal);return normal;
}
GroundOrientation::GroundOrientation(const GroundOrientationSettings& s)
    :ground_filter(GroundNormalFilter::Initialized(s.ground_normal_smoothing,{0,1,0,0})),slow_filter(GroundNormalFilter::Initialized(s.up_vector_smoothing_slow,{0,1,0,0})),fast_filter(GroundNormalFilter::Initialized(s.up_vector_smoothing_fast,{0,1,0,0})){}
void GroundOrientation::Reset(){dynamic_up=up=target=ground_normal={0,1,0};up_velocity={};ground_blend=0;fault.clear();}
void GroundOrientation::Update(const GroundOrientationSettings& s,GroundOrientationInput input)
{
    const auto entry_up=up,entry_velocity=up_velocity,entry_ground=ground_normal;const float entry_blend=ground_blend;
    const Vec3 up_axis{0,1,0};const auto normalized_com=SafeNormal(input.com_to_deck,{});const float amount=s.dynamic_up_vs_ground_y.Evaluate(input.ground_normal.y);
    const auto prediction=SafeNormal(PhysicalBlend(ground_normal,PhysicalAdd(up_axis,Subtract(input.dynamic_up,normalized_com)),amount),{});
    dynamic_up=input.dynamic_up;ground_normal=Xyz(ground_filter.Update(s.ground_normal_smoothing,Lanes(input.ground_normal)));
    const auto horizontal_axis=PhysicalCross(up_axis,ground_normal);
    if(Dot3(horizontal_axis,horizontal_axis)>PhysicalFloat(0x3a83126f))
    {
        const auto axis=Scale(horizontal_axis,InverseLengthSquared(Dot3(horizontal_axis,horizontal_axis),2));const auto projected=Subtract(prediction,Scale(axis,Dot3(axis,prediction)));
        const float prediction_to_ground=BoardGroundAngleBetween(projected,ground_normal),prediction_to_up=BoardGroundAngleBetween(projected,up_axis);
        const float ground_to_up=BoardGroundAngleBetween(ground_normal,up_axis),old_up_to_up=BoardGroundAngleBetween(up,up_axis);
        auto candidate=prediction_to_ground<prediction_to_up?ground_normal:up_axis;
        if(prediction_to_ground<ground_to_up&&prediction_to_up<ground_to_up)candidate=projected;
        const float alpha=(input.speed+1.0f)*PhysicalFloat(0x3a83126f);
        if(!(old_up_to_up>ground_to_up||prediction_to_up>old_up_to_up))candidate=Madd(up,1.0f-alpha,Scale(candidate,alpha));
        const float slope=UnitSaturate(ground_to_up*PhysicalFloat(0x3ea2f983));float target_blend=s.ground_vector_blend.Evaluate(slope);
        if(input.wheel_contact_count<=s.minimum_wheels_for_ground_blend)target_blend=0.0f;
        const float delta=target_blend-ground_blend,lower=Select(-s.ground_blend_max_delta-delta,-s.ground_blend_max_delta,delta);
        ground_blend+=Select(s.ground_blend_max_delta-lower,lower,s.ground_blend_max_delta);target=SafeNormal(PhysicalBlend(candidate,ground_normal,ground_blend),{});
    }
    else target=ground_normal;
    if(input.wheel_contact_count>=2&&input.animation_balance==0.0f)
    {
        const float usage=s.deck_angle_usage_vs_speed.Evaluate(input.deck_angle_curve_input);
        const auto axis=SafeNormal(PhysicalCross(input.board_forward,ground_normal),{});
        const auto deck_up=SafeNormal(Subtract(input.board_up,Scale(axis,Dot3(input.board_up,axis))),{});
        target=SafeNormal(PhysicalBlend(target,deck_up,usage),{});
    }
    const auto slow=SafeNormal(Xyz(slow_filter.FilterRaw(s.up_vector_smoothing_slow,Lanes(target))),{});
    const auto fast=SafeNormal(Xyz(fast_filter.FilterRaw(s.up_vector_smoothing_fast,Lanes(target))),{});
    const float speed_fraction=input.speed*PhysicalFloat(0x3dcccccd),mix=s.up_vector_smoothing_vs_speed.Evaluate(speed_fraction);
    const auto filtered=SafeNormal(PhysicalBlend(slow,fast,mix),{});const float max_delta=s.up_vector_max_delta_vs_speed.Evaluate(speed_fraction)*PhysicalFloat(0x3e4ccccd);
    const auto difference=Subtract(filtered,up);const float magnitude=Length3(difference),bounded=Select(magnitude-max_delta,max_delta,magnitude);
    const auto stepped=SafeNormal(Madd(SafeNormal(difference,{}),bounded,up),{}),desired_velocity=Subtract(stepped,up);
    const auto acceleration=ClampLength(Subtract(desired_velocity,up_velocity),s.up_vector_max_acceleration*PhysicalFloat(0x3c888889));
    up_velocity=PhysicalAdd(up_velocity,acceleration);const auto side=Scale(input.previous_reckoning_right,Dot3(up_velocity,input.previous_reckoning_right));
    up_velocity=Madd(side,s.extra_side_damping,Subtract(up_velocity,side));const auto unnormalized=PhysicalAdd(up,up_velocity);up=SafeNormal(unnormalized,unnormalized);
    if(0.0f>Dot3(up_velocity,desired_velocity))up_velocity=Scale(up_velocity,s.anti_wobble_damping);
    if(input.prevent_up_behind_board&&Dot3(up,input.effective_board_forward)<0.0f){const auto right=PhysicalCross(up,input.effective_board_forward);up=SafeNormal(PhysicalCross(input.effective_board_forward,right),up);up_velocity=Scale(up_velocity,0.5f);}
    slow_filter.PublishCurrent(Lanes(up));fast_filter.PublishCurrent(Lanes(up));
    if(fault.empty()&&!(std::isfinite(up.x)&&std::isfinite(up.y)&&std::isfinite(up.z)))
    {
        // Hexadecimal floats: a residual too small for decimal formatting (a denormal) still shows.
        const auto f=[](float x){char text[32];std::snprintf(text,sizeof text,"%a",double(x));return std::string(text);};
        const auto v=[&f](Vec3 a){return "("+f(a.x)+","+f(a.y)+","+f(a.z)+")";};
        fault="up non-finite: up "+v(entry_up)+" velocity "+v(entry_velocity)+" ground "+v(entry_ground)+" blend "+f(entry_blend)
            +" | com_to_deck "+v(input.com_to_deck)+" wheel_normal "+v(input.ground_normal)+" dynamic_up "+v(input.dynamic_up)+" speed "+f(input.speed)
            +" wheels "+std::to_string(input.wheel_contact_count)+" balance "+f(input.animation_balance)+" deck_angle "+f(input.deck_angle_curve_input)
            +" board_up "+v(input.board_up)+" board_forward "+v(input.board_forward)+" effective_forward "+v(input.effective_board_forward)+" previous_right "+v(input.previous_reckoning_right)
            +" | target "+v(target)+" ground_after "+v(ground_normal)+" velocity_after "+v(up_velocity);
    }
}
float SpeedAndSlopeSettings::Calculate(float ground_normal_y,float forward_speed) const
{
    const float normal_y=VectorMin(1.0f,VectorMax(-1.0f,ground_normal_y)),half_pi=PhysicalFloat(0x3fc90fdb);float inverse=ReciprocalEstimate(half_pi);
    for(unsigned i=0;i<2;++i){const float error=std::fma(-inverse,half_pi,1.0f);inverse=std::fma(inverse,error,inverse);}
    float slope=inverse*Acos(normal_y);if(slope>PhysicalFloat(0x3f99999a))slope=0.0f;
    const float absolute=std::fabs(forward_speed),nonnegative=Select(-absolute,0.0f,absolute),bounded=Select(heading_adjust_max_speed-nonnegative,nonnegative,heading_adjust_max_speed);
    const float fraction=bounded/heading_adjust_max_speed,speed_factor=turn_torque_vs_speed.Evaluate(fraction),slope_factor=turn_torque_vs_slope.Evaluate(slope);return speed_factor*slope_factor;
}
void PhysicalBoardProbes::ResetResults(){deck={};wall={};}
void PhysicalBoardProbes::PrepareWall(WallLineInput input){wall_line=WallProbe(input);}
bool PhysicalBoardProbes::Start(const BoardRuntime& board,const WorldGeometry& world,std::string& error)
{
    if(pending){error="Board probes submitted twice without publication";return false;}
    const auto line=DeckProbe(board.PartTransforms()[6].translation);deck.Start(line.start);
    const auto result=world.QuerySweptLine(line.start,line.end,DeckProbeRadius);if(result.error){error=std::string("Stock deck ground probe: ")+result.error;return false;}
    const auto deck_hit=ProbeHit(result);std::optional<std::optional<BoardProbeHit>> wall_hit;
    if(wall_line){wall.Start(wall_line->start);const auto query=world.QueryThinLine(wall_line->start,wall_line->end);if(query.error){error=std::string("Stock wall floor probe: ")+query.error;return false;}wall_hit.emplace(ProbeHit(query));}
    else wall.Disable();pending=Pending{deck_hit,wall_hit};return true;
}
bool PhysicalBoardProbes::Publish(std::string& error)
{
    if(!pending){error="Board probe publication requires a submitted batch";return false;}const auto result=*pending;pending.reset();deck.Publish(result.deck);if(result.wall)wall.Publish(*result.wall);else wall.Disable();return true;
}
PhysicalRidingOutputs::PhysicalRidingOutputs(PhysicalRidingSettings s,const BoardRuntime& board,std::uint32_t flags)
    :settings(std::move(s)),reckoning(settings.orientation),motion(BoardMotionOutput::FromBoard(board,reckoning.ground_normal,flags)),heading_adjust_factor(settings.speed.Calculate(ground.wheel_normal.y,motion.forward_speed)){}
void PhysicalRidingOutputs::ResetForTeleport()
{const float elapsed=ground.time_without_wheel_contact;const auto drag=ground.wheel_angular_drag;ground={};ground.time_without_wheel_contact=elapsed;ground.wheel_angular_drag=drag;wheel_lines={};probes.ResetResults();}
float PhysicalRidingOutputs::UpdateInputHeading(float y,float speed){heading_adjust_factor=settings.speed.Calculate(y,speed);return heading_adjust_factor;}
void PhysicalRidingOutputs::UpdateGroundReckoning(const BoardRuntime& board,PhysicalRidingPose pose,std::uint32_t flags,float balance,bool coffin,PhysicalGroundPacket packet,std::optional<Vec4> heading)
{
    const auto deck=board.PartTransforms()[6];const auto previous_right=reckoning_frames.system[0];reckoning_frames.heading=heading?*heading:Lanes(BasisColumn(deck.basis,2));GroundBodySpin(body_spin,pose.body_spin);
    const auto effective=BoardMotionOutput::FromBoard(board,reckoning.ground_normal,flags);
    reckoning.Update(settings.orientation,{pose.com_to_deck,packet.wheel_normal,packet.dynamic_up,packet.speed,packet.wheel_count,balance,packet.absolute_speed,
        BasisColumn(deck.basis,1),BasisColumn(deck.basis,2),BasisColumn(effective.effective_basis,2),Xyz(previous_right),coffin});
    const auto up=Lanes(reckoning.up);reckoning_frames.CalculateTransform(up,Lanes(reckoning.ground_normal));reckoning_frames.CalculateDynamicLean(up,Lanes(reckoning.dynamic_up));
    reckoning_frames.CalculateTilt((flags&0x100000)!=0,settings.tilt_vs_rotation,settings.tilt_vs_slope);
}
void PhysicalRidingOutputs::UpdateSlideReckoning(const BoardToolkit& toolkit,PhysicalRidingPose pose,std::uint32_t flags,float balance,bool coffin,PhysicalGroundPacket packet)
{
    const auto previous_right=reckoning_frames.system[0];reckoning_frames.heading=toolkit.deck[2];reckoning.dynamic_up=packet.dynamic_up;GroundBodySpin(body_spin,pose.body_spin);
    reckoning.Update(settings.orientation,{pose.com_to_deck,packet.wheel_normal,packet.dynamic_up,packet.speed,packet.wheel_count,balance,toolkit.absolute_speed,
        Column(toolkit.deck,1),Column(toolkit.deck,2),Column(toolkit.effective,2),Xyz(previous_right),coffin});
    const auto up=Lanes(reckoning.up);reckoning_frames.CalculateTransform(up,Lanes(reckoning.ground_normal));reckoning_frames.CalculateDynamicLean(up,Lanes(reckoning.dynamic_up));
    reckoning_frames.CalculateTilt((flags&0x100000)!=0,settings.tilt_vs_rotation,settings.tilt_vs_slope);
}
bool PhysicalRidingOutputs::StartWheelQueries(const BoardRuntime& board,const WorldGeometry& world,std::string& error)
{
    if(pending_wheel_queries){error="Wheel queries were started twice without result publication";return false;}
    const auto lines=WheelLines(board,reckoning.up);std::array<std::optional<WheelLineHit>,4> results;
    for(std::size_t i=0;i<4;++i){const auto query=world.QueryThinLine(lines[i].start,lines[i].end);if(query.error){error="Wheel"+std::to_string(i)+" stock line query: "+query.error;return false;}if(query.hit)results[i]=WheelLineHit{query.hit->geometry.fraction,query.hit->geometry.normal,query.hit->tag};}
    if(!probes.Start(board,world,error))return false;pending_wheel_queries=results;return true;
}
bool PhysicalRidingOutputs::FinishWheelQueries(std::string& error)
{
    if(!pending_wheel_queries){error="EndBoard requires its submitted wheel query batch";return false;}const auto hits=*pending_wheel_queries;pending_wheel_queries.reset();wheel_lines.Publish(hits);return probes.Publish(error);
}
void PhysicalRidingOutputs::FinishPostPhysics(BoardRuntime& board,bool wiping,std::uint32_t flags,float dt)
{
    ground.Update(board.ContactReports(),wheel_lines,reckoning.up,settings.maximum_ground_angle,wiping);
    std::array<Vec3,7> velocities;for(unsigned i=0;i<7;++i)velocities[i]=board.Bodies()[i].rates.linear_velocity;ground.SampleAccelerations(velocities,dt);ground.AdvanceContactTime(dt);
    for(unsigned i=0;i<4;++i)board.BodiesMut()[i].inertia.angular_drag=ground.wheel_angular_drag[i];motion=BoardMotionOutput::FromBoard(board,reckoning.ground_normal,flags);
}
void PhysicalSkeletonCorrection::ObserveBoard(Vec4 actual,Vec4 predicted){for(unsigned i=0;i<4;++i)board_prediction_error[i]=actual[i]-predicted[i];}
void PhysicalSkeletonCorrection::Apply(SkeletonBody& body,Vec4 normal,bool wipeout,std::uint32_t flags,std::uint32_t flags2476)
{
    const auto error=board_prediction_error;
    if(wipeout&&(flags2476&(1u<<30))!=0)
    {
        if(1.0f>Dot3(error,error))for(unsigned part=0;part<24;++part){auto frame=body.record.pose[part];for(unsigned i=0;i<4;++i)frame[3][i]+=error[i];body.SetPartTransform(part,frame);}pending=false;
    }
    else if(!wipeout&&(flags&(1u<<18))==0&&pending)
    {
        const float distance=Dot3(error,normal),allowed=VectorMin(0.0f,distance);Vec4 offset;
        for(unsigned i=0;i<4;++i){const float tangent=error[i]-normal[i]*distance;offset[i]=std::fma(normal[i],allowed,tangent);}
        for(unsigned part=1;part<24;++part)for(unsigned i=0;i<4;++i)body.record.pose[part][3][i]+=offset[i];pending=false;
    }
}
PhysicalSimulationRuntime::PhysicalSimulationRuntime(PhysicalSimulationSettings s,BoardRuntime b,WorldGeometry w,SkeletonBody rider,SkeletonJoints joints,SkeletonDrives drives,const std::array<Mat4,24>& initial)
    :settings(std::move(s)),board(std::move(b)),world(std::move(w)),riding(settings.riding,board,0x2000),skeleton(std::move(rider)),skeleton_joints(std::move(joints)),skeleton_drives(std::move(drives)),
    skeleton_collision(settings.collision,false),collision_feedback(settings.feedback),possession(settings.possession),possession_live(settings.possession_live),drive_frames(initial)
{
    const auto spawn=DeckFrame();roots.ResetInitialAlignment(skeleton.animation_to_world);board_frames.Reset(spawn);
    for(unsigned i=0;i<2;++i)board_frames.PublishCentreOfMass(skeleton.record.centre_of_mass,settings.board.step.simulation.time_step,0);
    board_frames.PublishLocalObservations(roots,spawn);const auto targets=skeleton_drives.targets.UpdateExtraTargets(skeleton,board_frames.com_frame,board_frames.lifted_com_frame);
    extra_target_positions={targets.com,targets.lifted_com,targets.following_com};pose_errors.targets=extra_target_positions;
}
std::optional<PhysicalSimulationRuntime> PhysicalSimulationRuntime::Initialize(PhysicalSimulationSettings s,const SettingsDatabase& data,const std::vector<Mat4>& hierarchy,WorldGeometry world,AffineTransform spawn,std::string& error)
{
    error.clear();BoardRuntime board(s.board.masses,s.board.authored,spawn,s.board.step.simulation,BoardMotion::Active);
    std::array<Mat4,24> initial;if(!MapAnimationParts(hierarchy,s.bone_indices,s.physics_frames,initial,error))return std::nullopt;
    Mat4 deck=SkeletonIdentity;const auto part=board.PartTransforms()[6];for(unsigned axis=0;axis<3;++axis)for(unsigned lane=0;lane<3;++lane)deck[axis][lane]=part.basis.columns[axis][lane];deck[3]=Lanes(part.translation);
    auto body=LoadSkeletonBody(data,s.physical,initial,deck,s.board.step.simulation,std::nullopt,error);if(!body)return std::nullopt;
    auto joints=LoadSkeletonJoints(data,s.physical,hierarchy,s.hierarchy_parents,s.bone_indices,error);if(!joints)return std::nullopt;
    auto drives=LoadSkeletonDrives(data,s.physical,hierarchy,s.bone_indices,initial,*joints,body->animation_to_world,deck,s.board.step.simulation,error);if(!drives)return std::nullopt;
    return PhysicalSimulationRuntime(std::move(s),std::move(board),std::move(world),std::move(*body),std::move(*joints),std::move(*drives),initial);
}
std::optional<PhysicalSimulationRuntime> PhysicalSimulationRuntime::Initialize(PhysicalSimulationSettings s,const SettingsDatabase& data,const AnimationPoseEvaluator& evaluator,WorldGeometry world,AffineTransform spawn,std::string& error)
{
    PoseCommand command;command.kind=PoseCommand::Kind::Pose;command.name="RIG_TPOSE";std::vector<Sqt> pose;std::vector<Mat4> hierarchy;
    if(!evaluator.Evaluate({command},pose,error)||!evaluator.Hierarchy(pose,hierarchy,error))return std::nullopt;return Initialize(std::move(s),data,hierarchy,std::move(world),spawn,error);
}
Mat4 PhysicalSimulationRuntime::DeckFrame() const
{
    const auto deck=board.PartTransforms()[6];Mat4 frame=SkeletonIdentity;for(unsigned axis=0;axis<3;++axis)for(unsigned lane=0;lane<3;++lane)frame[axis][lane]=deck.basis.columns[axis][lane];frame[3]=Lanes(deck.translation);return frame;
}
bool PhysicalSimulationRuntime::BeginBoardQueries(std::string& error){board.ClearForces();return riding.StartWheelQueries(board,world,error);}
bool PhysicalSimulationRuntime::FinishBoardQueries(std::string& error){return riding.FinishWheelQueries(error);}
bool PhysicalSimulationRuntime::AdvanceClimbingBoardOnly(float dt,std::string& error)
{
    board.ClearForces();
    if(!riding.StartWheelQueries(board,world,error))return false;
    if(!riding.FinishWheelQueries(error))return false;
    const auto volumes=BoardWorldVolumes(board,settings.board.collision);
    const auto contacts=world_contacts_.Query(world,volumes,settings.query,settings.retention);
    contact_count=contacts.size();generated_contacts=contacts;
    board.Advance(contacts,{0.0f,0.0f},settings.board.step);
    riding.FinishPostPhysics(board,board_wiping_out,processed_flags_2468,dt);
    error.clear();return true;
}
Mat4 PhysicalSimulationRuntime::PrepareGroundSkeleton(const Mat4& animation_board,const Mat4& reckoning,float dt)
{
    roots.initialize_heading=true;roots.Update(DeckFrame(),Lanes(board.Bodies()[6].rates.linear_velocity),dt,animation_board,reckoning);
    return board_frames.PrepareGround(roots,animation_record.pose[0],roots.board,processed_flags_2468);
}
void PhysicalSimulationRuntime::UpdateRootDerivative(float dt)
{
    float inverse=ReciprocalEstimate(dt);for(unsigned i=0;i<2;++i)inverse=std::fma(inverse,std::fma(-inverse,dt,1.0f),inverse);
    for(unsigned i=0;i<4;++i)root_velocity[i]=(roots.animation_to_world[3][i]-previous_root_position[i])*inverse;previous_root_position=roots.animation_to_world[3];
}
void PhysicalSimulationRuntime::ResetPhysicalPose()
{
    correction.pending=false;
    for(std::size_t part=0;part<26;++part)
    {
        skeleton.SetPartTransform(part,part<24?ComposeSkeletonAffine(roots.animation_to_world,drive_frames[part]):board_frames.com_frame);
        auto& rates=skeleton.BodiesMut()[part].rates;rates.linear_velocity={};rates.angular_velocity={};rates.force_acceleration=settings.board.step.simulation.gravity_acceleration;rates.torque_acceleration={};
    }
    reset_local_hips=drive_frames[23][3];const auto hips=TransformSkeletonPoint(roots.animation_to_world,reset_local_hips);skeleton.record.Reset(skeleton.PartTransforms());animation_record.ResetHistory();
    board_frames.centre_of_mass=hips;board_frames.previous_centre_of_mass=hips;board_frames.com_velocity={};pose_errors.ResetHistory();
}
void PhysicalSimulationRuntime::ApplySkeletonGravity(float gravity)
{
    const float step=PhysicalFloat(0x3c888889);Vec4 displacement{0.0f,-gravity,0.0f,0.0f};for(auto& x:displacement)x=((x*0.5f)*step)*step;
    for(std::size_t part=0;part<24;++part)skeleton.ApplyPartDisplacement(part,displacement);
}
SkeletonTargetUpdate PhysicalSimulationRuntime::UpdateTargetPositions(const Mat4& hips,const Mat4& animation_board,bool teleporting)
{
    const auto target=skeleton_drives.targets.UpdatePositions({hips,animation_board,roots.animation_to_world,roots.inverse_board,board_frames.skate_root,board_frames.com_frame,board_frames.lifted_com_frame,teleporting},skeleton);
    animation_board_to_physics=target.animation_board_to_physics;extra_target_positions={target.positions.com,target.positions.lifted_com,target.positions.following_com};pose_errors.SetTargets(target.positions);return target;
}
void PhysicalSimulationRuntime::UpdateBoneDrives(const std::array<Mat4,24>& frames){drive_frames=frames;skeleton_drives.Update(frames,skeleton_collision.partial_ragdoll,collision_feedback.drive_weight);}
void PhysicalSimulationRuntime::UpdatePossession(const BoardPossessionProcessed& p,std::optional<Mat4> toolkit_deck,std::uint8_t& animated,float dt)
{
    const BoardPossessionObserveInput input{p,toolkit_deck,riding.ground,riding.wheel_lines,skeleton.record,collision_feedback,drive_frames,roots.animation_to_world};
    UpdateBoardPossession(possession,possession_live,board,settings.board.collision,board_wiping_out,animated,controller_fields,input,dt);
}
BoardPossessionFill PhysicalSimulationRuntime::PublishPossession(const BoardPossessionProcessed& p,std::optional<Mat4> toolkit_deck)
{
    const BoardPossessionObserveInput input{p,toolkit_deck,riding.ground,riding.wheel_lines,skeleton.record,collision_feedback,drive_frames,roots.animation_to_world};
    return PublishBoardPossession(possession,possession_live,board,riding.ground,controller_fields,input);
}
bool PhysicalSimulationRuntime::Validate(PhysicalSimulationDiagnostic::Stage stage,std::string& error)
{
    std::vector<const BodySnapshot*> bodies;for(const auto& b:board.Bodies())bodies.push_back(&b);bodies.push_back(&board.Hook().body);for(const auto& b:skeleton.Bodies())bodies.push_back(&b);for(const auto& b:skeleton_drives.targets.bodies)bodies.push_back(&b);
    using F=PhysicalSimulationDiagnostic::Field;
    for(std::size_t i=0;i<bodies.size();++i)
    {
        const auto& b=*bodies[i];const auto& r=b.rates;std::optional<F> field;
        const std::array<Vec3,5> v{r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration};
        const auto limit=stage==PhysicalSimulationDiagnostic::Stage::EndFrame?3u:5u;
        for(unsigned j=0;j<limit;++j)if(!std::isfinite(v[j].x)||!std::isfinite(v[j].y)||!std::isfinite(v[j].z)){field=static_cast<F>(j);break;}
        if(stage!=PhysicalSimulationDiagnostic::Stage::EndFrame&&!field)
        {
            bool finite=true;for(auto x:r.orientation)finite=finite&&std::isfinite(x);for(const auto& c:r.basis.columns)for(auto x:c)finite=finite&&std::isfinite(x);for(const auto& c:r.world_inverse_inertia.columns)for(auto x:c)finite=finite&&std::isfinite(x);if(!finite)field=F::OrientationInertia;
        }
        // finish_skater checks board and skeleton rates, excluding hook/targets.
        if(stage==PhysicalSimulationDiagnostic::Stage::EndFrame&&(i==7||i>=8+26))continue;
        if(field){diagnostic=PhysicalSimulationDiagnostic{stage,*field,i,b};error="Non-finite "+std::string(FieldName(*field))+" "+(stage==PhysicalSimulationDiagnostic::Stage::BeforeSharedSolve?"before shared solve":stage==PhysicalSimulationDiagnostic::Stage::AfterSharedSolve?"after shared solve":"at end of frame")+"; reaction_body="+std::to_string(i);return false;}
    }return true;
}
bool PhysicalSimulationRuntime::Solve(std::array<float,2> truck_targets,std::string& error)
{
    error.clear();if(!Validate(PhysicalSimulationDiagnostic::Stage::BeforeSharedSolve,error))return false;
    auto board_volumes=BoardWorldVolumes(board,settings.board.collision);board_volumes.erase(std::remove_if(board_volumes.begin(),board_volumes.end(),[&](const BoardWorldVolume& v){return !possession_live.VolumeEnabled(CollisionBody::FromContactId(v.body_contact_id));}),board_volumes.end());
    const auto rider=SkeletonEnabledVolumes(skeleton,skeleton_collision,error);if(!rider)return false;
    auto contacts=world_contacts_.Query(world,board_volumes,settings.query,settings.retention);
    auto skeleton_query=settings.query;skeleton_query.edge_cos_bend_normal_threshold=-1.0f;auto rider_world=*rider;RetainSkeletonWorldVolumes(rider_world,skeleton_collision);
    const auto& rider_contacts=world_contacts_.Query(world,rider_world,skeleton_query,settings.retention);contacts.insert(contacts.end(),rider_contacts.begin(),rider_contacts.end());
    if(!AppendAssemblyContacts(contacts,board_volumes,*rider,board.CollisionGroup(),skeleton_collision,error))return false;
    network_contacts=AppendRemoteContacts(contacts,board_volumes,*rider,network_proxies.volumes);contact_count=contacts.size();generated_contacts=contacts;
    const float dt=settings.board.step.simulation.time_step;auto joints=skeleton_joints.Build(skeleton.Bodies(),AttachedReactionBase,dt);
    auto drives=skeleton_drives.Build(skeleton.Bodies(),AttachedReactionBase,AttachedReactionBase+SkeletonPartCount,dt);const auto skeleton_count=drives.rows.size();
    possession.AppendDrives(board.Bodies()[6],{skeleton.Bodies()[3],skeleton.Bodies()[7]},6,{AttachedReactionBase+3,AttachedReactionBase+7},dt,drives.rows);
    std::vector<BodySnapshot*> attached;for(auto& b:skeleton.BodiesMut())attached.push_back(&b);for(auto& b:skeleton_drives.targets.bodies)attached.push_back(&b);for(auto& b:network_proxies.bodies)attached.push_back(&b);
    std::vector<ContactConstraint> additional_contacts;board.AdvanceAttached(contacts,truck_targets,settings.board.step,{attached,additional_contacts,joints,drives.rows});solved_joints=joints;
    if(!Validate(PhysicalSimulationDiagnostic::Stage::AfterSharedSolve,error))return false;
    skeleton.PublishPhysicalRecord(DeckFrame());drives.rows.resize(skeleton_count);solved_drives=std::move(drives);return true;
}
void PhysicalSimulationRuntime::FinishBoardOutputs(WallLineInput input)
{riding.probes.PrepareWall(input);riding.FinishPostPhysics(board,board_wiping_out,processed_flags_2468,settings.board.step.simulation.time_step);}
void PhysicalSimulationRuntime::PublishFeedback(const PhysicalFeedbackInput& p)
{
    std::vector<const BodySnapshot*> attached;for(const auto& b:skeleton.Bodies())attached.push_back(&b);for(const auto& b:skeleton_drives.targets.bodies)attached.push_back(&b);for(const auto& b:network_proxies.bodies)attached.push_back(&b);
    CollectSkeletonContactReports(contact_reports,board.SolvedContacts(),{board.Bodies(),attached,SkeletonPartCount+SkeletonTargetCount,board.CollisionGroup(),skeleton_collision.assembly_group},settings.board.step.simulation.frequency);
    const auto deck=DeckFrame();correction.ObserveBoard(deck[3],roots.predicted_board_position);
    const bool entering=p.state_2508==501||p.state_2508==503,offboard=p.category_2512==500&&!entering;
    auto point=p.vectors_464_480_496_512_528[(p.state_2508==601||p.state_2508==602)?1:2];const auto n=riding.reckoning.ground_normal;auto normal=Lanes(n);
    if(offboard&&(p.flags_2480&2)!=0){point=p.vectors_880_896_912_928_944[0];normal=p.vectors_880_896_912_928_944[1];}
    const auto frames=skeleton.PartTransforms();collision_feedback.Update({settings.board.step.simulation.time_step,point,normal,p.state_2508==201?skeleton.record.velocities[23]:deck_velocity,board_frames.com_velocity,
        skeleton_collision.is_ragdoll,(p.flags_2472&0x8000)!=0,(p.flags_2472&0x10000000)!=0,offboard,entering,p.category_2512==600,controller_fields.state_448==1&&riding.ground.part_contact_count!=0,
        skeleton.record,skeleton.definition.animation_masses.part_weights,frames},contact_reports);
    skeleton_collision.FinishContactFrame();pose_errors.targets=extra_target_positions;pose_errors.Update(skeleton.record,roots.animation_to_world,drive_frames);
    const auto response=skeleton_collision.partial_ragdoll?pose_errors.PartialResponse():pose_errors.NormalResponse(collision_feedback,Lanes(n));collision_pose_error=response.impulse;collision_extra_errors=response.extra;collision_maximum_error=response.maximum_error;
    board_frames.PublishLocalObservations(roots,deck);board_frames.PublishCentreOfMass(skeleton.record.centre_of_mass,settings.board.step.simulation.time_step,p.flags_2472);
}
bool PhysicalSimulationRuntime::FinishFrame(std::string& error){++ticks;if(!Validate(PhysicalSimulationDiagnostic::Stage::EndFrame,error)){failed=true;return false;}return true;}
void PhysicalSimulationRuntime::EnableImportedFloorSeams(){world_contacts_.EnableImportedFloorSeams();}
void PhysicalSimulationRuntime::ReplaceWorld(WorldGeometry replacement)
{
    // The original BoardWorld owns both query storage and its imported-seam
    // flag. Replacing it clears that state while already submitted wheel and
    // probe results remain in RidingOutputs until their publication phase.
    world_contacts_=BoardWorldContacts{};world=std::move(replacement);
}
}
