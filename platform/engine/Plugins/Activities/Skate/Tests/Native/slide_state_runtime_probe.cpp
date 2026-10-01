// SPDX-License-Identifier: Apache-2.0
#include "SlideStateRuntime.h"
#include "GroundControlSettings.h"
#include "DeckGeometry.h"
#include "DataReader.h"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
struct Input
{
    detail::DataReader reader;
    explicit Input(const std::vector<std::uint8_t>& bytes):reader{bytes} {reader.at=0;}
    std::uint32_t Word() {return reader.Word();}
    float Float() {const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
    Vec4 Four() {return {Float(),Float(),Float(),Float()};}
    Vec3 Three() {return {Float(),Float(),Float()};}
    PointGraph<8> Curve() {PointGraph<8> p;for (auto& v:p.x) v=Float();for (auto& v:p.y) v=Float();return p;}
    SlideInput Slide() {return {Four(),Four(),Four(),Four(),Four(),Four(),Float(),Float(),Float(),Float(),Float()};}
    SteeringInput Steering() {return {Float(),Float(),Float(),Float(),Float(),Float(),Word()!=0};}
    ManualInput Manual() {return {Float(),Float(),Float(),Float(),Float(),Float(),Word()!=0,Word()!=0,Word()!=0,Word()!=0,Word()!=0,Four(),Four(),Four(),Four(),Four(),Four(),Four()};}
    GroundContactFrame Contact() {return {Four(),Four(),Four(),Word(),Word()!=0,Float(),Float()};}
    SlideGroundForceFrame Force() {return {Float(),Float(),Float(),Float(),Float(),Float(),Four(),Four(),Four()};}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}
    void String(std::string_view v) {Word(std::uint32_t(v.size()));bytes.insert(bytes.end(),v.begin(),v.end());}
    void Value(Vec3 v) {Float(v.x);Float(v.y);Float(v.z);}
    void Value(Vec4 v) {for (auto x:v) Float(x);}
    void Value(Basis3 b) {for (auto c:b.columns) for (auto x:c) Float(x);}
    void Body(const BodySnapshot& b) {const auto& r=b.rates;const auto& d=b.inertia;Word(b.state_flags);Value(r.orientation);Value(r.basis);Value(r.world_inverse_inertia);for (auto v:{r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration}) Value(v);Float(r.kinetic_energy);Word(r.cool_down);Value(d.inverse_tensor);for (auto x:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag}) Float(x);}
};
struct Services final:SlideStateServices
{
    BoardRuntime& board;const SteeringSettings& steering;const ManualSettings& manual;ManualMode manual_mode;const GroundForceSettings& force;const WallRideSettings& wall;const RidingCollisionResponseSettings& collision;
    std::uint32_t fail=0;bool toolkit=true;SlideCompletedFrame completed{};SteeringInput steering_input{};ManualInput manual_input{};GroundContactFrame contact{};SlideGroundForceFrame force_input{};
    std::vector<std::uint32_t> trace;std::optional<SlideCollisionForce> retained;std::optional<RidingCollisionPhysical> observed_collision;std::optional<Vec4> launch;float spin=0,balance=0;std::uint32_t observed_mode=0xffffffffu;
    Services(BoardRuntime& b,const SteeringSettings& s,const ManualSettings& m,ManualMode mm,const GroundForceSettings& f,const WallRideSettings& w,const RidingCollisionResponseSettings& c):board(b),steering(s),manual(m),manual_mode(mm),force(f),wall(w),collision(c) {}
    bool Stage(std::uint32_t code,std::string& error) {trace.push_back(code);if (fail==code) {error="Slide fixture producer failure "+std::to_string(code);return false;}return true;}
    bool RequireCurrentSlideToolkit(std::string& error) override {trace.push_back(1);if (!toolkit) {error="Slide requires current BoardToolkit";return false;}return true;}
    bool UpdateSlideReckoning(std::string&) override {trace.push_back(2);return true;}
    bool UpdateSlideSkeletonGround(std::string& error) override {if (!Stage(3,error)) return false;if (fail==5) toolkit=false;return true;}
    bool CaptureSlidePhysicsError(std::string&) override {trace.push_back(4);return true;}
    std::optional<SlideCompletedFrame> ReadCompletedSlideFrame(std::string& error) override {trace.push_back(5);if (!toolkit) {error="Slide requires current BoardToolkit";return std::nullopt;}return completed;}
    std::optional<SlideGroundInputs> PrepareSlideGroundInput(std::uint32_t mode,std::string& error) override {trace.push_back(6);observed_mode=mode;if (mode>4) {error="Invalid pumping physics mode "+std::to_string(mode);return std::nullopt;}trace.push_back(7);return SlideGroundInputs{steering_input,manual_input,contact,force_input,steering,manual,manual_mode,force,wall};}
    bool CalculateSlideCollisionForce(RidingCollisionPhysical input,std::optional<SlideCollisionForce>& applied,std::string&) override {trace.push_back(9);observed_collision=input;const auto response=CalculateRidingCollisionResponse(collision,input);if (!response||!response->applied) {applied.reset();return true;}applied=SlideCollisionForce{response->force,response->point,response->angular_displacement};retained=applied;return true;}
    bool LaunchSlideTrajectory(Vec4 velocity,std::string& error) override {launch=velocity;if (!Stage(10,error)||!Stage(11,error)||!Stage(12,error)) return false;trace.push_back(13);if (fail==13) {error="Slide trajectory requires current board toolkit";return false;}trace.push_back(14);return Stage(15,error);}
    void Read(Input& i) {fail=i.Word();toolkit=i.Word()!=0;completed.surface_mode=i.Word();completed.pumping_mode=i.Word();completed.flags_2468=i.Word();completed.flags_2472=i.Word();completed.wheel_count=i.Word();completed.slide=i.Slide();completed.up=i.Four();completed.collision_displacement=i.Four();completed.collision_velocity=i.Four();completed.travel_direction=i.Four();completed.ground_normal=i.Three();completed.total_mass=i.Float();completed.gravity=i.Float();completed.scalar_2652=i.Float();completed.processed_timestep=i.Float();steering_input=i.Steering();manual_input=i.Manual();contact=i.Contact();force_input=i.Force();trace.clear();observed_collision.reset();launch.reset();observed_mode=0xffffffffu;}
};
void Snapshot(Output& o,const SlideState& slide,const ManualState& manual,const TruckSteeringState& steering,const BoardRuntime& board,bool elapsed,float angle,float speed,std::uint8_t animated,std::uint32_t mode,float balance,const ContactMaterial& material,const Services& s)
{
    for (auto v:{slide.start_speed,slide.steering_push,slide.damped_turn}) o.Float(v);o.Word(slide.flag48);o.Word(slide.wall_riding);for (auto v:{manual.filtered_angle_error,manual.target_angle,manual.measured_angle,manual.angular_correction,manual.elapsed,steering.deck_tilt,steering.targets[0],steering.targets[1],steering.activation_time[0],steering.activation_time[1]}) o.Float(v);
    o.Word(elapsed);o.Float(angle);o.Float(speed);o.Word(animated);o.Word(mode);o.Float(balance);for (auto v:{material.static_friction,material.dynamic_friction,material.restitution}) o.Float(v);for (const auto& b:board.Bodies()) o.Body(b);for (auto w:board.Hook().drive.frames) o.Word(w);for (auto w:board.Hook().drive.dynamics) o.Word(w);o.Word(std::uint32_t(board.Forces().Count()));for (std::size_t n=0;n<board.Forces().Count();++n) {const auto& f=board.Forces().Entries()[n];o.Word(f.tag);o.Value(f.force_world);o.Value(f.point_body);}
    o.Word(s.retained.has_value());if (s.retained) {o.Value(s.retained->force_2528);o.Value(s.retained->point_2544);o.Value(s.retained->vector_2592);}o.Word(std::uint32_t(s.trace.size()));for (auto v:s.trace) o.Word(v);o.Word(s.observed_mode);o.Word(s.observed_collision.has_value());if (s.observed_collision) {const auto& p=*s.observed_collision;o.Word(p.flags);o.Value(p.collision_displacement);o.Value(p.velocity);o.Value(p.forward);o.Value(p.up);o.Value(p.ground_normal);o.Float(p.time_step);o.Float(p.mass);}o.Word(s.launch.has_value());if (s.launch) o.Value(*s.launch);
}
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;std::ifstream f(argv[1],std::ios::binary);const std::vector<std::uint8_t> packed{std::istreambuf_iterator<char>(f),{}};SettingsDatabase data;std::string error;SlideStateSettings stock;SteeringSettings steering_settings;ManualSettings manual_settings{};ManualMode manual_mode{};GroundForceSettings force_settings{};if (!data.Load(packed,error)||!stock.Load(data,error)||!steering_settings.Load(data,error)||!LoadGroundManualSettings(data,manual_settings,error)||!LoadGroundManualMode(data,"normal",manual_mode,error)||!LoadGroundForceSettings(data,force_settings,error)) {std::cerr<<error;return 2;}
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(bytes);Output output;const auto cases=i.Word();
    for (std::uint32_t c=0;c<cases;++c)
    {
        WallRideSettings wall{i.Curve(),i.Float(),i.Float(),i.Float(),i.Float(),i.Float(),i.Float(),i.Float()};RidingCollisionResponseSettings collision{i.Float(),i.Float(),i.Float(),i.Float(),i.Curve()};SlideState state{i.Float(),i.Float(),i.Float(),i.Word()!=0,i.Word()!=0};ManualState manual{i.Float(),i.Float(),i.Float(),i.Float(),i.Float()};TruckSteeringState steering{i.Float(),{i.Float(),i.Float()},{i.Float(),i.Float()}};bool elapsed=i.Word()!=0;float angle=i.Float(),speed=i.Float();auto animated=std::uint8_t(i.Word());auto mode=i.Word();auto balance=i.Float();
        SimulationStep simulation{1.f/60.f,60,9,.001f,{0,-9.81f,0}};const Basis3 identity{std::array<std::array<float,3>,3>{{{1,0,0},{0,1,0},{0,0,1}}}};BoardRuntime board(DefaultSkateboardMassProperties(),AuthoredBodyTransforms(AuthoredTransformInputs::Stock()),{identity,{0,2,0}},simulation,BoardMotion::Active);board.HookMut().drive.EnableAngularSoft();
        for (auto& b:board.BodiesMut()) {b.rates.linear_velocity=i.Three();b.rates.angular_velocity=i.Three();b.rates.force_acceleration=i.Three();b.rates.torque_acceleration=i.Three();b.inertia.linear_drag=i.Float();}
        const auto preseed=i.Word();for (std::uint32_t n=0;n<preseed;++n) board.ForcesMut().Append({i.Word(),i.Three(),i.Three()});ContactMaterial material{.137f,.317f,.731f},standard{.113f,.517f,.173f};Services services(board,steering_settings,manual_settings,manual_mode,force_settings,wall,collision);const auto count=i.Word();
        for (std::uint32_t tick=0;tick<count;++tick)
        {
            const auto op=i.Word();services.trace.clear();services.observed_collision.reset();services.launch.reset();services.observed_mode=0xffffffffu;bool ok=true;error.clear();
            if (op==0) {const auto category=i.Word();const auto value=i.Float();EnterSlideState(state,board,{elapsed,angle,speed,animated,manual,mode,balance},category,value);}
            else if (op==1) ExitSlideState(state,material,standard);
            else if (op==2) {services.Read(i);ok=UpdateSlideState(state,stock,{board,manual,steering,material},services,error);}
            else if (op==3) board.ClearForces();
            else if (op==4) board.ForcesMut().Append({i.Word(),i.Three(),i.Three()});
            else return 2;
            output.Word(c);output.Word(tick);output.Word(op);output.Word(ok);output.String(error);Output row;Snapshot(row,state,manual,steering,board,elapsed,angle,speed,animated,mode,balance,material,services);output.Word(std::uint32_t(row.bytes.size()/4));output.bytes.insert(output.bytes.end(),row.bytes.begin(),row.bytes.end());
        }
    }
    if (!i.reader.ok||i.reader.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(output.bytes.data()),std::streamsize(output.bytes.size()));
}
