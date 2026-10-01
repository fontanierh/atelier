// SPDX-License-Identifier: Apache-2.0
#include "AirStateSettings.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
struct Input
{
    std::vector<std::uint32_t> words;std::size_t at=0;
    std::uint32_t Word() {return words[at++];}
    float Float() {const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
    std::int32_t Signed() {const auto w=Word();std::int32_t i;std::memcpy(&i,&w,4);return i;}
    Vec4 Vector() {return {Float(),Float(),Float(),Float()};}
    Mat4 Matrix() {return {Vector(),Vector(),Vector(),Vector()};}
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w) {words.push_back(w);}
    void Float(float f) {std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void Vector(Vec4 v) {for (auto f:v) Float(f);}
    void Matrix(Mat4 v) {for (auto c:v) Vector(c);}
    void String(const std::string& s)
    {
        Word(static_cast<std::uint32_t>(s.size()));
        for (std::size_t i=0;i<s.size();i+=4) {std::uint32_t w=0;for (std::size_t j=0;j<4&&i+j<s.size();++j) w|=std::uint32_t(static_cast<unsigned char>(s[i+j]))<<(j*8);Word(w);}
    }
    void Status(bool ok,const std::string& error) {Word(ok);if (!ok) String(error);}
};
PhysicsAirFrame Frame(Input& i)
{
    const auto current=i.Vector();const auto ground=i.Float();const auto position=i.Vector(),velocity=i.Vector(),jump=i.Vector();
    const auto flags=i.Word();const auto state=i.Signed(),category=i.Signed(),frames=i.Signed();
    return {current,ground,position,velocity,jump,flags,state,category,frames,i.Float(),i.Float(),i.Float(),i.Float()};
}
void WriteFrame(Output& o,const PhysicsAirFrame& f)
{
    o.Vector(f.current_velocity_400);o.Float(f.ground_position_y_500);o.Vector(f.trajectory_position_592);o.Vector(f.trajectory_velocity_608);o.Vector(f.jump_velocity_848);
    o.Word(f.flags_2468);o.Word(std::uint32_t(f.previous_physics_state_2504));o.Word(std::uint32_t(f.previous_physics_category_2516));o.Word(std::uint32_t(f.frames_since_jump_correction_2576));
    for (auto v:{f.delta_time_2604,f.body_spin_input_2640,f.gravity_y_2648,f.state_timer_2664}) o.Float(v);
}
PhysicsAirReckoningFields Reckoning(Input& i) {return {i.Vector(),i.Vector(),i.Float(),i.Float()};}
void WriteReckoning(Output& o,const PhysicsAirReckoningFields& r) {o.Vector(r.current_landing_normal_1152);o.Vector(r.collision_reference_normal_1216);o.Float(r.body_spin_angle_1568);o.Float(r.body_spin_speed_1572);}
PhysicsAirSettings Settings(Input& i) {PhysicsAirSettings s;for (auto& v:s.body_spin_over_time_320.x) v=i.Float();for (auto& v:s.body_spin_over_time_320.y) v=i.Float();s.landing_normal_blend_388=i.Float();s.body_spin_scale_428=i.Float();s.landing_normal_angle_limit_444=i.Float();return s;}
void WriteSettings(Output& o,const AirStateSettings& s)
{for (auto v:s.state.body_spin_over_time_320.x) o.Float(v);for (auto v:s.state.body_spin_over_time_320.y) o.Float(v);for (auto v:{s.state.landing_normal_blend_388,s.state.body_spin_scale_428,s.state.landing_normal_angle_limit_444,s.steering_blend}) o.Float(v);for (auto v:s.grind_lock_distance) o.Float(v);}
AirTrajectory Trajectory(Input& i) {return {i.Vector(),i.Vector(),i.Vector(),i.Float()};}
void WriteTrajectory(Output& o,const AirTrajectory& t) {o.Vector(t.position);o.Vector(t.velocity);o.Vector(t.acceleration);o.Float(t.scalar_48);}
PhysicsAirState State(Input& i)
{
    PhysicsAirState s;s.centre_of_mass_trajectory=Trajectory(i);s.landing_normal=i.Vector();s.time_in_state=i.Float();s.start_y=i.Float();s.max_y=i.Float();s.reached_apex=i.Word()!=0;s.use_centre_of_mass_velocity=i.Word()!=0;s.selector_latch_174=i.Word()!=0;s.trajectory_query_countdown=i.Signed();return s;
}
void WriteState(Output& o,const PhysicsAirState& s)
{WriteTrajectory(o,s.centre_of_mass_trajectory);o.Vector(s.landing_normal);o.Float(s.time_in_state);o.Float(s.start_y);o.Float(s.max_y);o.Word(s.reached_apex);o.Word(s.use_centre_of_mass_velocity);o.Word(s.selector_latch_174);o.Word(std::uint32_t(s.trajectory_query_countdown));}
AirLaunchInfo Info(Input& i)
{
    AirLaunchInfo l;l.reckoning_transform=i.Matrix();l.reckoning_inverse=i.Matrix();l.start_velocity=i.Vector();l.com_velocity=i.Vector();l.skeleton_vector_160=i.Vector();l.skeleton_vector_176=i.Vector();l.board_position=i.Vector();l.animation_com_position=i.Vector();l.start_position_override=i.Vector();l.board_position_override=i.Vector();l.cone_angle_x=i.Float();l.cone_angle_z=i.Float();l.timestep=i.Float();l.player_jumped=i.Word()!=0;l.use_position_override=i.Word()!=0;l.trajectory_count=std::uint16_t(i.Word());return l;
}
void WriteInfo(Output& o,const AirLaunchInfo& l)
{
    o.Matrix(l.reckoning_transform);o.Matrix(l.reckoning_inverse);for (auto v:{l.start_velocity,l.com_velocity,l.skeleton_vector_160,l.skeleton_vector_176,l.board_position,l.animation_com_position,l.start_position_override,l.board_position_override}) o.Vector(v);
    o.Float(l.cone_angle_x);o.Float(l.cone_angle_z);o.Float(l.timestep);o.Word(l.player_jumped);o.Word(l.use_position_override);o.Word(l.trajectory_count);
}
struct TracedInfo final : AirLaunchInfo
{
    Output& out;explicit TracedInfo(Output& trace):out(trace) {}
    void SetStartVelocity(Vec4 v) override {out.Word(100);out.Vector(v);AirLaunchInfo::SetStartVelocity(v);}
    Vec4 CentreOfMassAnimationPosition() const override {out.Word(101);out.Vector(animation_com_position);return animation_com_position;}
    void SetTrajectoryStartPositionOverride(Vec4 v) override {out.Word(102);out.Vector(v);AirLaunchInfo::SetTrajectoryStartPositionOverride(v);}
    void SetBoardPositionOverride(Vec4 v) override {out.Word(103);out.Vector(v);AirLaunchInfo::SetBoardPositionOverride(v);}
    std::array<float,2> ConeAngles() const override {out.Word(104);out.Float(cone_angle_x);out.Float(cone_angle_z);return AirLaunchInfo::ConeAngles();}
    void SetConeAngles(std::array<float,2> v) override {out.Word(105);out.Float(v[0]);out.Float(v[1]);AirLaunchInfo::SetConeAngles(v);}
    void SetPlayerJumped(bool v) override {out.Word(106);out.Word(v);AirLaunchInfo::SetPlayerJumped(v);}
    void SetUseTrajectoryStartPositionOverride(bool v) override {out.Word(107);out.Word(v);AirLaunchInfo::SetUseTrajectoryStartPositionOverride(v);}
    void SetTrajectoryCount(std::uint16_t v) override {out.Word(108);out.Word(v);AirLaunchInfo::SetTrajectoryCount(v);}
};
struct Runtime final : PhysicsAirRuntime
{
    mutable Output trace;AirMath math;AirLaunchInfo fill;float height;Vec4 velocity;bool query_started;std::optional<Vec4> normal;bool com_ready;
    PhysicsAirReckoningFields reckoning;bool collision;AirBoardForce force;
    explicit Runtime(Input& i):fill(Info(i)),height(i.Float()),velocity(i.Vector()),query_started(i.Word()!=0)
    {const bool has_normal=i.Word()!=0;const auto n=i.Vector();if (has_normal) normal=n;com_ready=i.Word()!=0;reckoning=Reckoning(i);collision=i.Word()!=0;force={i.Vector(),i.Vector()};}
    float Minimum(float a,float b) override {const auto v=math.Minimum(a,b);trace.Word(110);trace.Float(a);trace.Float(b);trace.Float(v);return v;}
    float LengthSquared(Vec4 a) override {const auto v=math.LengthSquared(a);trace.Word(111);trace.Vector(a);trace.Float(v);return v;}
    float Length(Vec4 a) override {const auto v=math.Length(a);trace.Word(112);trace.Vector(a);trace.Float(v);return v;}
    Vec4 ClampLength(Vec4 a,float m) override {const auto v=math.ClampLength(a,m);trace.Word(113);trace.Vector(a);trace.Float(m);trace.Vector(v);return v;}
    bool SetAirCollisionUpdateEnabled(bool v,std::string&) override {trace.Word(1);trace.Word(v);return true;}
    bool SetSkeletonCollisionState(std::uint32_t v,std::string&) override {trace.Word(2);trace.Word(v);return true;}
    bool SetSkeletonInverseKinematicsEnabled(bool v,std::string&) override {trace.Word(3);trace.Word(v);return true;}
    bool EnableBoardAngularDriveOnly(std::string&) override {trace.Word(4);return true;}
    bool SetFootplantFlag240(bool v,std::string&) override {trace.Word(5);trace.Word(v);return true;}
    bool ResetFootplants(std::string&) override {trace.Word(6);return true;}
    float BoardTransformHeight() override {trace.Word(7);trace.Float(height);return height;}
    bool RequestSkeletonHeadingUpdate(std::string&) override {trace.Word(8);return true;}
    bool UpdateAirCollision(std::string&) override {trace.Word(9);return true;}
    bool TrajectoryQueryJustStarted() const override {trace.Word(10);trace.Word(query_started);return query_started;}
    bool ConstructTrajectoryLaunchInfo(std::unique_ptr<PhysicsAirLaunchInfo>& out,std::string&) override {trace.Word(11);auto info=std::make_unique<TracedInfo>(trace);WriteInfo(trace,*info);out=std::move(info);return true;}
    bool FillSkeletonLaunchInfo(PhysicsAirLaunchInfo& out,std::string&) override {trace.Word(12);WriteInfo(trace,fill);static_cast<AirLaunchInfo&>(out)=fill;return true;}
    bool LaunchTrajectory(const PhysicsAirLaunchInfo& info,std::string&) override {trace.Word(13);WriteInfo(trace,static_cast<const AirLaunchInfo&>(info));return true;}
    bool UpdateTrajectorySelector(std::string&) override {trace.Word(14);return true;}
    std::optional<Vec4> SelectorLandingNormal() const override {trace.Word(15);trace.Word(bool(normal));if (normal) trace.Vector(*normal);return normal;}
    bool SelectorCentreOfMassTrajectoryReady() const override {trace.Word(16);trace.Word(com_ready);return com_ready;}
    float AngleBetweenVectors(Vec4 a,Vec4 b) override {const auto v=AirAngleBetweenVectors(a,b);trace.Word(17);trace.Vector(a);trace.Vector(b);trace.Float(v);return v;}
    bool UpdateReckoningAirStates(Vec4 n,float blend,float spin,float flip,PhysicsAirReckoningFields& out,std::string&) override {trace.Word(18);trace.Vector(n);trace.Float(blend);trace.Float(spin);trace.Float(flip);WriteReckoning(trace,reckoning);out=reckoning;return true;}
    bool UpdateKnownAirSkeleton(Vec4 p,std::string&) override {trace.Word(19);trace.Vector(p);return true;}
    bool UpdateAnimatedSkateboardSkeleton(bool v,std::string&) override {trace.Word(20);trace.Word(v);return true;}
    bool UpdateBoardSteeringTilt(float v,std::string&) override {trace.Word(21);trace.Float(v);return true;}
    bool CalculateAirCollisionForce(Vec4 n,AirBoardForce& out,bool& created,std::string&) override {trace.Word(22);trace.Vector(n);trace.Vector(out.force_world);trace.Vector(out.point_board_local);trace.Word(collision);trace.Vector(force.force_world);trace.Vector(force.point_board_local);out=force;created=collision;return true;}
    bool EnqueueBoardForce(std::uint32_t tag,AirBoardForce f,std::string&) override {trace.Word(23);trace.Word(tag);trace.Vector(f.force_world);trace.Vector(f.point_board_local);return true;}
    bool SetBoardVelocity(Vec4 v,std::string&) override {trace.Word(24);trace.Vector(v);return true;}
    bool EnableSkateboardErrorOnSkeleton(std::string&) override {trace.Word(25);return true;}
    Vec4 BoardBodyVelocity() override {trace.Word(26);trace.Vector(velocity);return velocity;}
    bool CheckForAirWipeout(bool v,std::string&) override {trace.Word(27);trace.Word(v);return true;}
};
AirStateBindingInput Binding(Input& i)
{
    AirStateBindingInput p;for (auto& group:p.vectors_400_416) for (auto& w:group) w=i.Word();for (auto& group:p.vectors_464_480_496_512_528) for (auto& w:group) w=i.Word();for (auto& group:p.vectors_544_560_592_608) for (auto& w:group) w=i.Word();for (auto& w:p.prepared_jump_704) w=i.Word();for (auto& w:p.jump_reference) w=i.Word();
    p.flags_2468=i.Word();p.flags_2472=i.Word();p.flags_2476=i.Word();p.state_2504=i.Word();p.category_2516=i.Word();p.state_variant_index_2528=i.Word();p.jump_fix_frames=i.Word();p.external_physics_flags=i.Word();
    p.timestep_2604=i.Float();p.transition_2636=i.Float();p.gravity_2648=i.Float();p.state_timer_2664=i.Float();p.body_spin=i.Float();p.world_gravity=i.Vector();p.reckoning_system=i.Matrix();p.reckoning_inverse=i.Matrix();p.skeleton_local_centre_of_mass=i.Vector();p.skeleton_local_board_position=i.Vector();const bool has_toolkit=i.Word()!=0;const auto deck=i.Matrix();if (has_toolkit) p.toolkit_deck=deck;p.trajectory_cone_x=i.Float();p.trajectory_cone_z=i.Float();return p;
}
void Bind(Output& o,const AirStateBindingInput& p,const AirStateSettings& settings)
{
    WriteFrame(o,BindPhysicsAirFrame(p));AirSelectorInput selector;AirLaunchInfo launch;std::string error;
    const bool selected=BindAirSelectorInput(p,settings,selector,error);o.Status(selected,error);
    if (selected) {for (auto v:{selector.gravity,selector.ground_normal,selector.contact_position,selector.heading_direction,selector.reference_up}) o.Vector(v);o.Float(selector.board_vertical_velocity);o.Float(selector.directional_input);for (auto v:{selector.previous_physics_state,selector.flags_2472,selector.flags_2476,selector.offboard_flags_1776}) o.Word(v);o.Float(selector.grind_lock_distance);}
    const bool launched=BindAirLaunchInfo(p,launch,error);o.Status(launched,error);if (launched) WriteInfo(o,launch);
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;
    SettingsDatabase data;std::string error;
    std::ifstream settings_file(argv[1],std::ios::binary);
    const std::vector<std::uint8_t> settings_bytes{std::istreambuf_iterator<char>(settings_file),{}};
    if (!data.Load(settings_bytes,error)) {std::cerr<<error;return 2;}
    AirStateSettings stock;
    if (!stock.Load(data,error)) {std::cerr<<error;return 2;}
    const std::vector<char> bytes{std::istreambuf_iterator<char>(std::cin),{}};if (bytes.size()%4) return 2;Input i;i.words.resize(bytes.size()/4);std::memcpy(i.words.data(),bytes.data(),bytes.size());Output o;WriteSettings(o,stock);o.Vector(PhysicsAirHostComAcceleration());const auto count=i.Word();o.Word(count);
    PhysicsAirState state;PhysicsAirReckoningFields reckoning{{0,1,0,0},{0,1,0,0},0,0};AirMath math;
    for (std::uint32_t row=0;row<count;++row)
    {
        const auto op=i.Word();Output trace,extra;bool ok=true;error.clear();
        if (op==0) {state=State(i);reckoning=Reckoning(i);}
        else if (op==1||op==2||op==5)
        {
            const auto frame=Frame(i);const auto acceleration=i.Vector();Runtime r(i);
            if (op==1) ok=EnterPhysicsAir(state,frame,acceleration,r,error);
            else if (op==5) ok=UpdatePhysicsAirBoard(state,frame,reckoning,r,error);
            else {const bool use_stock=i.Word()!=0;const auto settings=Settings(i);ok=UpdatePhysicsAir(state,frame,use_stock?stock.state:settings,reckoning,acceleration,r,error);}
            trace=std::move(r.trace);
        }
        else if (op==3) {Runtime r(i);ok=UpdatePhysicsAirPost(state,r,error);trace=std::move(r.trace);}
        else if (op==4) ExitPhysicsAir(state,reckoning);
        else if (op==6)
        {
            const auto frame=Frame(i);const auto frames=i.Signed();const auto left=i.Vector(),right=i.Vector();const auto maximum=i.Float();
            extra.Vector(CalculateAirVelocityFromJump(frame,frames,math));extra.Float(math.Minimum(left[0],right[0]));extra.Float(math.LengthSquared(left));extra.Float(math.Length(left));extra.Vector(math.ClampLength(left,maximum));extra.Float(AirAngleBetweenVectors(left,right));extra.Float(WrapAirSignedAngle(maximum));extra.Vector(ClampAirJumpVelocity(left,right));
        }
        else if (op==7) {state.centre_of_mass_trajectory=Trajectory(i);IntegrateAirTrajectoryFixedStep(state.centre_of_mass_trajectory);}
        else if (op==8) Bind(extra,Binding(i),stock);
        else if (op==9) {state=PhysicsAirState{};AirLaunchInfo info;WriteInfo(extra,info);}
        else return 2;
        o.Word(row);o.Word(op);o.Status(ok,error);WriteState(o,state);WriteReckoning(o,reckoning);const auto result=FillPhysicsAirOutput(state);o.Word(result.is_at_apex);o.Float(result.jump_height);o.Vector(result.landing_normal);o.Word(bool(result.scalar_184_write));if (result.scalar_184_write) o.Float(*result.scalar_184_write);
        o.Word(static_cast<std::uint32_t>(trace.words.size()));o.words.insert(o.words.end(),trace.words.begin(),trace.words.end());o.Word(static_cast<std::uint32_t>(extra.words.size()));o.words.insert(o.words.end(),extra.words.begin(),extra.words.end());
    }
    if (i.at!=i.words.size()) return 2;
    std::cout.write(reinterpret_cast<const char*>(o.words.data()),static_cast<std::streamsize>(o.words.size()*4));return 0;
}
