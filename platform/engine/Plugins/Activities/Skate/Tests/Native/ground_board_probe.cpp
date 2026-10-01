// SPDX-License-Identifier: Apache-2.0
#include "GroundSettings.h"
#include "GroundBoard.h"
#include "GroundCorrections.h"
#include "DeckAngularCorrections.h"
#include "RidingCollisionResponse.h"
#include "RidingAngles.h"
#include "BoardRuntime.h"
#include "DeckGeometry.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    detail::DataReader reader;
    explicit Input(const std::vector<std::uint8_t>& b):reader{b} {reader.at=0;}
    std::uint32_t Word() {return reader.Word();}
    float Float() {const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
    template<std::size_t N> std::array<float,N> Floats() {std::array<float,N> a;for (auto& v:a) v=Float();return a;}
    template<std::size_t N> std::array<std::uint32_t,N> Words() {std::array<std::uint32_t,N> a;for (auto& v:a) v=Word();return a;}
    template<std::size_t N> PointGraph<N> Curve() {return {Floats<N>(),Floats<N>()};}
    Vec3 Three() {return {Float(),Float(),Float()};}
    Mat4 Matrix() {return {Floats<4>(),Floats<4>(),Floats<4>(),Floats<4>()};}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    void Value(Vec3 v) {Float(v.x);Float(v.y);Float(v.z);}
    void Value(Vec4 v) {for (auto x:v) Float(x);}
    void Value(Mat4 v) {for (auto c:v) Value(c);}
    void Value(Basis3 v) {for (auto c:v.columns) for (auto x:c) Float(x);}
    template<std::size_t N> void Curve(const PointGraph<N>& p) {for (auto x:p.x) Float(x);for (auto y:p.y) Float(y);}
    void Append(const Output& o) {bytes.insert(bytes.end(),o.bytes.begin(),o.bytes.end());}
    void Block(const Output& o) {Word(std::uint32_t(o.bytes.size()/4));Append(o);}
    void Body(const BodySnapshot& b) {const auto& r=b.rates;const auto& d=b.inertia;Word(b.state_flags);Value(r.orientation);Value(r.basis);Value(r.world_inverse_inertia);for (auto v:{r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration}) Value(v);Float(r.kinetic_energy);Word(r.cool_down);Value(d.inverse_tensor);for (auto v:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag}) Float(v);}
};
// GENERATED_PROTOCOL
Vec3 Three(Vec4 v) {return {v[0],v[1],v[2]};}
Vec4 Four(Vec3 v) {return {v.x,v.y,v.z,0};}
Output Arguments(std::initializer_list<Vec4> values) {Output o;for (auto v:values) o.Value(v);return o;}
GroundLaunchInfo AuthoredPacket(std::uint32_t seed)
{
    GroundLaunchInfo p;p.vector_224={float(seed)*.125f,.25f,-.5f,.125f};p.vector_240={-.125f,.5f,float(seed)*.25f,.25f};p.flag_269=true;p.flags_270=0x1234;p.wall_jump=false;return p;
}
struct Services final:GroundBoardServices
{
    BoardRuntime& board;const GroundSettings& settings;std::uint32_t seed,fail=0,calls=0,branch=0,wipeouts=0,commits=0;Output trace;GroundContactResponse contact{};std::optional<GroundBoardCollisionResponse> retained_collision;std::optional<GroundLaunchInfo> launch;Vec4 processed_velocity{.125f,.25f,.5f,.75f};ContactMaterial material{.125f,.25f,.5f};ReckoningFrames reckoning;
    Services(BoardRuntime& b,const GroundSettings& s,std::uint32_t n):board(b),settings(s),seed(n) {reckoning.system[3]={.125f,.25f,.5f,1};reckoning.inverse_system[3]={-.125f,-.25f,-.5f,1};}
    bool Gate(std::uint32_t id,const Output& args,std::string& error) {++calls;trace.Word(id);trace.Block(args);if (calls==fail) {error="Ground fixture failure "+std::to_string(calls);return false;}return true;}
    bool Empty(std::uint32_t id,std::string& error) {return Gate(id,{},error);}
    GroundLaunchPhysical Physical() const {return {reckoning,{.125f,.25f,.5f,.75f},{-.125f,.5f,.25f,.125f},{.5f,2,.25f,1},{.5f,3,.25f,1},{1,2,3,.125f},{.25f,.5f,.75f,.25f},seed%2?0x2000u:0u,1.f/60.f};}
    bool CenterOfMassHeight(float& v,std::string& e) override {const Vec4 c{.25f,.5f,1,.125f};if (!Gate(0,Arguments({c}),e)) return false;v=GroundCentreOfMassHeight(c);return true;}
    bool SetContactWheelMaterials(std::string& e) override {Output a;Observe(a,settings.wheel_material);if (!Gate(1,a,e)) return false;material=settings.wheel_material;return true;}
    bool ContactResponse(GroundContactFrame f,Vec4 previous,GroundBoardContactResponse& out,std::string& e) override {Output a;Observe(a,f);a.Value(previous);if (!Gate(2,a,e)) return false;WallRideSettings s{};for (std::size_t i=0;i<8;++i) {s.anti_gravity_vs_time.x[i]=float(i);s.anti_gravity_vs_time.y[i]=.125f;}s.max_dot_floor_wall=.5f;s.foot_force_time=.09f;s.auto_jump_height=.6f;s.max_time=1;s.velocity_time_to_consider=.25f;s.auto_jump_y_down_scalar=.66f;s.auto_jump_force=3;const Vec4 normal=branch==1?Vec4{1,0,0,0}:Vec4{0,1,0,0};contact=CalculateWallRideResponse(s,{normal,normal,{2,-2,4,.125f},8,9.81f,5,1},f,previous);out=contact;return true;}
    bool UpdateBodyAccumulator(std::string& e) override {if (!Empty(3,e)) return false;ApplyGroundBodyTorque(board.BodiesMut()[6].rates);return true;}
    bool SetAnimatedVelocity(Vec4 v,std::string& e) override {if (!Gate(4,Arguments({v}),e)) return false;for (auto& b:board.BodiesMut()) b.rates.linear_velocity=Three(v);return true;}
    bool WriteProcessedVelocity(Vec4 v,std::string& e) override {if (!Gate(5,Arguments({v}),e)) return false;processed_velocity=v;return true;}
    bool BuildAnimatedPose(GroundLaunchInfo& p,std::string& e) override {if (!Empty(6,e)) return false;p=AuthoredPacket(seed);return true;}
    bool PublishAnimatedPose(const GroundLaunchInfo& p,std::string& e) override {Output a;Observe(a,p);if (!Gate(7,a,e)) return false;launch=p;launch->Fill(Physical(),.125f,.25f);return true;}
    bool UpdateExternalPlayer(const GroundLaunchInfo& p,Vec4 v,std::string& e) override {Output a;Observe(a,p);a.Value(v);if (!Gate(8,a,e)) return false;if (!launch) {e="Ground launch packet was not filled";return false;}launch->WallJump(v);return true;}
    bool CommitExternalPlayer(std::string& e) override {Output a;if (launch) {Observe(a,*launch);Observe(a,launch->SelectorLaunch());}if (!Gate(9,a,e)) return false;++commits;return true;}
    bool FinalizeAnimatedBoard(std::string& e) override {return Empty(10,e);}
    bool CollisionForce(Vec4 normal,std::optional<GroundBoardCollisionResponse>& out,std::string& e) override {if (!Gate(11,Arguments({normal}),e)) return false;RidingCollisionResponseSettings s{.75f,-.125f,.75f,.75f,{}};for (std::size_t n=0;n<8;++n) {s.torque_vs_angle.x[n]=float(n);s.torque_vs_angle.y[n]=.125f;}const auto r=CalculateRidingCollisionResponse(s,{branch==2?0x20000u:0u,{1,0,0,.125f},{-.25f,0,1,.25f},{0,0,1,0},{0,1,0,0},normal,1.f/60.f,8});if (r&&r->applied) {out=GroundBoardCollisionResponse{r->force,r->point,r->angular_displacement};retained_collision=out;}else out.reset();return true;}
    bool CollisionForceDotVelocity(Vec4 f,Vec4 v,float& out,std::string& e) override {if (!Gate(12,Arguments({f,v}),e)) return false;out=GroundCollisionForceProjection(f,v);return true;}
    bool ApplyVector(Vec4 v,std::string& e) override {if (!Gate(13,Arguments({v}),e)) return false;ApplyDeckLimitedDisplacement(board.BodiesMut()[6].rates,Three(v));return true;}
    bool ApplyAngularDisplacement(Vec4 v,std::string& e) override {if (!Gate(14,Arguments({v}),e)) return false;ApplyDeckAngularDisplacement(board.BodiesMut()[6].rates,Three(v));return true;}
    bool AngleBetween(Vec4 a,Vec4 b,Vec4 axis,float& out,std::string& e) override {if (!Gate(15,Arguments({a,b,axis}),e)) return false;out=RidingSignedAngle(Three(a),Three(b),Three(axis));return true;}
    bool GroundDot3(Vec4 a,Vec4 b,float& out,std::string& e) override {if (!Gate(16,Arguments({a,b}),e)) return false;out=Dot3(a,b);return true;}
    bool GroundScaleToMagnitude(Vec4 v,float square,float size,Vec4& out,std::string& e) override {Output a;a.Value(v);a.Float(square);a.Float(size);if (!Gate(17,a,e)) return false;out=GroundScaleToMagnitudeKernel(v,square,size);return true;}
    static Vec4 GroundScaleToMagnitudeKernel(Vec4 v,float square,float size) {return atelier::skate::GroundScaleToMagnitude(v,square,size);}
    bool BuildHangForce(Vec4& out,std::string& e) override {const auto p=board.PartTransforms()[6].translation;const Vec4 start{0,0,0,0},end{0,0,2,0};if (!Gate(18,Arguments({start,end,Four(p)}),e)) return false;out=GroundHangForce(start,end,Four(p));return true;}
    bool ApplyHangForce(Vec4 f,std::string& e) override {if (!Gate(19,Arguments({f}),e)) return false;const auto p=board.PartTransforms()[6].translation;GroundApplyWorldForce(board.BodiesMut()[6],p,Three(f),p);return true;}
    bool DetectHungUpGeometry(bool& hung,std::string& e) override {Output a;a.Word(seed%2);if (!Gate(20,a,e)) return false;hung=seed%2!=0;return true;}
    bool RequestHungWipeout(std::string& e) override {if (!Empty(21,e)) return false;++wipeouts;return true;}
    bool WheelCatchDisplacement(Vec4& out,std::string& e) override {if (!Empty(22,e)) return false;const auto b=board.PartTransforms()[6].basis.columns;out=GroundWheelCatchDisplacement({b[1][0],b[1][1],b[1][2],0},{b[2][0],b[2][1],b[2][2],0});return true;}
    bool ApplyWheelCatchDisplacement(Vec4 v,std::string& e) override {if (!Gate(23,Arguments({v}),e)) return false;ApplyDeckAngularDisplacement(board.BodiesMut()[6].rates,Three(v));return true;}
    bool PinToCapturedPosition(float x,float z,std::string& e) override {Output a;a.Float(x);a.Float(z);if (!Gate(24,a,e)) return false;const auto v=GroundPinningVelocity(Four(board.PartTransforms()[6].translation),x,z,1.f/60.f);for (auto& b:board.BodiesMut()) b.rates.linear_velocity=Three(v);return true;}
};
void Snapshot(Output& o,const PhysicsGroundState& state,const SpeedWobbleState& wobble,const TruckSteeringState& truck,const SpeedModelState& speed,const ManualState& manual,float heading,const BoardRuntime& board,const std::vector<InertiaDynamics>& detached,const std::vector<std::size_t>& indices,const Services& services)
{
    Observe(o,state);for (auto w:wobble.words) o.Word(w);Observe(o,truck);Observe(o,speed);Observe(o,manual);o.Float(heading);for (const auto& b:board.Bodies()) o.Body(b);o.Word(std::uint32_t(detached.size()));for (const auto& d:detached) {o.Value(d.inverse_tensor);for (auto v:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag}) o.Float(v);}o.Word(std::uint32_t(indices.size()));for (auto index:indices) o.Word(std::uint32_t(index));o.Word(std::uint32_t(board.Forces().Count()));for (std::size_t n=0;n<board.Forces().Count();++n) {const auto& f=board.Forces().Entries()[n];o.Word(f.tag);o.Value(f.force_world);o.Value(f.point_body);}o.Value(services.processed_velocity);Observe(o,services.material);o.Word(services.retained_collision.has_value());if (services.retained_collision) {o.Value(services.retained_collision->force_2528);o.Value(services.retained_collision->point_2544);o.Value(services.retained_collision->vector_2592);}o.Word(services.launch.has_value());if (services.launch) {Observe(o,*services.launch);Observe(o,services.launch->SelectorLaunch());}o.Word(services.wipeouts);o.Word(services.commits);o.Word(services.calls);o.Block(services.trace);
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;std::ifstream file(argv[1],std::ios::binary);const std::vector<std::uint8_t> packed{std::istreambuf_iterator<char>(file),{}};SettingsDatabase data;GroundProfiles profiles;std::string error;if (!data.Load(packed,error)||!profiles.Load(data,error)) {std::cerr<<error;return 2;}const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);Output out;const auto count=input.Word();
    for (std::uint32_t c=0;c<count;++c)
    {
        const auto mode=input.Word(),surface=input.Word();const auto tuning=ReadTrainerTuning(input);const auto selected=profiles.Select(mode,surface,error);if (!selected) {std::cerr<<error;return 2;}const auto settings=selected->Tuned(tuning);auto state=ReadPhysicsGroundState(input);const auto seed=input.Word(),preseed=input.Word();SpeedWobbleState wobble{{0,0x12340000u+seed,0,0,0,0,0,0x00123456u}};TruckSteeringState truck{.125f,{.25f,-.125f},{.05f,.125f}};SpeedModelState speed{2,0x80000000};ManualState manual{.125f,.25f,.375f,.5f,0};float heading=.125f;
        const Basis3 identity{std::array<std::array<float,3>,3>{{{1,0,0},{0,1,0},{0,0,1}}}};BoardRuntime board(DefaultSkateboardMassProperties(),AuthoredBodyTransforms(AuthoredTransformInputs::Stock()),{identity,{0,2,0}},{1.f/60.f,60,9,.001f,{0,-9.81f,0}},BoardMotion::Active);for (std::size_t n=0;n<7;++n) {auto& b=board.BodiesMut()[n];b.rates.angular_velocity={.125f,.25f,.375f};b.rates.torque_acceleration={float(n)*.125f,.25f,-.125f};b.inertia.linear_drag=.125f+float(n)*.03125f;}for (std::uint32_t n=0;n<preseed;++n) board.ForcesMut().Append({100+n,{float(n),.25f,-.125f},{.125f,.25f,.375f}});Services services(board,settings,seed);Output config;Observe(config,settings);GroundLaunchInfo packet;Observe(config,packet);Observe(config,packet.SelectorLaunch());packet=AuthoredPacket(seed);Observe(config,packet);Observe(config,packet.SelectorLaunch());packet.Fill(services.Physical(),.125f,.25f);Observe(config,packet);Observe(config,packet.SelectorLaunch());packet.WallJump({2,4,-3,.125f});Observe(config,packet);Observe(config,packet.SelectorLaunch());out.Word(c);out.Block(config);
        const auto ticks=input.Word();for (std::uint32_t tick=0;tick<ticks;++tick)
        {
            services.branch=input.Word();services.fail=input.Word();const auto clear=input.Word(),binding=input.Word();auto frame=ReadGroundBoardInput(input);if (clear) board.ClearForces();services.calls=0;services.trace.bytes.clear();std::vector<InertiaDynamics> detached;for (const auto& b:board.Bodies()) detached.push_back(b.inertia);std::vector<std::size_t> indices{0,1,2,3,4,5,6};if (binding==1) indices[3]=7;else if (binding==2) detached.resize(6);BodyInertias inertias{indices.data(),indices.size(),detached.data(),detached.size()};auto queue=board.Forces();GroundBoardError failure;const auto result=UpdateGroundBoard(state,{wobble,truck,speed,manual,heading,queue,inertias},settings.Board(),frame,services,failure);
            for (std::size_t n=0;n<detached.size();++n) board.BodiesMut()[n].inertia.linear_drag=detached[n].linear_drag;board.ForcesMut()=queue;out.Word(c);out.Word(tick);out.Word(result.has_value());std::array<std::uint32_t,6> outcome{};std::string text;
            if (result) {outcome[0]=std::uint32_t(result->kind);outcome[1]=result->tag_15_queued;outcome[2]=result->ordinary.manual_correction;outcome[3]=result->ordinary.terminal_force_tag;outcome[4]=result->ordinary.terminal_force_queued;outcome[5]=result->ordinary.speed_model_reset;}
            else {outcome[0]=0xffffffff;outcome[1]=std::uint32_t(failure.kind);if (failure.kind==GroundBoardError::Kind::Service) {outcome[2]=std::uint32_t(failure.stage);text=failure.source;}else if (failure.kind==GroundBoardError::Kind::Manual) {outcome[3]=std::uint32_t(failure.manual.kind);text=failure.manual.kind==ManualError::Kind::Angle?"Ground manual angle unavailable":failure.manual.measurement;}else {outcome[3]=std::uint32_t(failure.drag);text="Ground drag binding "+std::to_string(outcome[3]);}}
            for (auto v:outcome) out.Word(v);out.String(text);Output snapshot;Snapshot(snapshot,state,wobble,truck,speed,manual,heading,board,detached,indices,services);out.Block(snapshot);
        }
    }
    if (!input.reader.ok||input.reader.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));
}
