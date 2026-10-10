#include "GroundPropulsion.h"
#include "SpeedModel.h"
#include "RidingAngles.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> out;
std::uint32_t Word()
{
    char bytes[4]; if (!std::cin.read(bytes, 4)) std::exit(2);
    return std::uint32_t(static_cast<unsigned char>(bytes[0]))
        | (std::uint32_t(static_cast<unsigned char>(bytes[1])) << 8)
        | (std::uint32_t(static_cast<unsigned char>(bytes[2])) << 16)
        | (std::uint32_t(static_cast<unsigned char>(bytes[3])) << 24);
}
float Float() { const auto word = Word(); float value; std::memcpy(&value, &word, 4); return value; }
Vec3 Three() { return {Float(), Float(), Float()}; }
Vec4 Four() { return {Float(), Float(), Float(), Float()}; }
PointGraph<8> Curve() { PointGraph<8> c; for (auto& v : c.x) v = Float(); for (auto& v : c.y) v = Float(); return c; }
void Out(std::uint32_t word) { out.push_back(word); }
void Out(float value) { std::uint32_t word; std::memcpy(&word, &value, 4); Out(word); }
void Out(Vec3 v) { Out(v.x); Out(v.y); Out(v.z); }
void Out(Vec4 v) { for (auto lane : v) Out(lane); }
void Out(QueuedPointForce f) { Out(f.tag); Out(f.force_world); Out(f.point_body); }
void Out(PushAcceleration p) { Out(p.vector); Out(p.local_point); Out(std::uint32_t(p.suppressed)); }
void Out(const BoardForceQueue& q) { Out(std::uint32_t(q.Count())); for(std::size_t i=0;i<q.Count();++i) Out(q.Entries()[i]); }
PushInput Push() { return {Word(), Word(), Float(), Float(), Float(), Float(), Float(), Three()}; }
PushLimits Limits() { return {Float(), Float(), Float()}; }
BrakeInput Brake() { return {Word(), Float(), Float(), Float(), Float(), Three()}; }
BrakeSettings Brakes() { return {Float(), Float(), Float()}; }
SpeedModelSettings SpeedSettings() { return {Float(), Float(), Float(), Float(), Float(), Float(), Curve(), Float(), Float(), Float(), Float(), Curve(), Curve(), Word()!=0, Float(), Four(), Four()}; }
SpeedModelInput SpeedInput() { return {Word(), Word(), std::int32_t(Word()), std::int32_t(Word()), Float(), Float(), Float(), Float(), Float(), Float(), Float(), Float(), Four(), Four(), Four(), Four(), Four(), Float()}; }
GroundPropulsionInput GroundInput() { return {Word(), Word(), Float(), Float(), Float(), Float(), Float(), Float(), Three(), Three(), Float()}; }
GroundPropulsionSettings GroundSettings() { return {Brakes(), Float(), {Float(), Float()}}; }
ManualSettings ManualSettingsInput() { return {Curve(),Float(),Float(),Float(),Float(),Float(),{Float(),Float(),Float()},{Float(),Float(),Float()},Float(),Float(),Float(),Float(),Float()}; }
ManualInput ManualInputs() { return {Float(),Float(),Float(),Float(),Float(),Float(),Word()!=0,Word()!=0,Word()!=0,Word()!=0,Word()!=0,Four(),Four(),Four(),Four(),Four(),Four(),Four()}; }
void Out(ManualState state) { for(float v:{state.filtered_angle_error,state.target_angle,state.measured_angle,state.angular_correction,state.elapsed})Out(v); }
void Out(ManualEffect e) { Out(e.angular_displacement);Out(e.force_world);Out(e.force_point_body);Out(e.corrective_force_world);Out(e.corrective_point_body);Out(std::uint32_t(e.correction_active));Out(std::uint32_t(e.opposing_motion_without_correction)); }
struct Measurement final : ManualAngleMeasurement {
 std::uint32_t mode=0,calls=0;float supplied=0;std::array<Vec4,3> last{};
 bool AngleBetween(Vec4 a,Vec4 b,Vec4 axis,float& output,std::string& error) override {
  ++calls;last={a,b,axis};if(mode==1){error="probe manual measurement unavailable";return false;}
  output=mode==2?supplied:RidingSignedAngle(Vec3{a[0],a[1],a[2]},Vec3{b[0],b[1],b[2]},Vec3{axis[0],axis[1],axis[2]});error.clear();return true;
 }
 void Snapshot() const { Out(calls);for(auto v:last)Out(v); }
};
}
int main()
{
 const auto cases=Word();for(std::uint32_t c=0;c<cases;++c) {
  const auto op=Word();Out(c);Out(op);const auto mark=out.size();Out(0u);
  switch(op) {
   case 0: { const auto input=Push();Out(CalculatePushAcceleration(input,Limits()));break; }
   case 1: { const auto input=Brake();Out(CalculateBraking(input,Brakes()));break; }
   case 2: { const LinearDragInput input{Word(),Float(),Float(),Float(),Float()};const LinearDragSettings settings{Float(),Float(),Float(),Float()};Out(CalculateLinearDrag(input,settings));break; }
   case 3: {
    const auto settings=SpeedSettings();SpeedModelState state{Float(),Word()};Out(state.target_speed);Out(state.flags_1360);const auto steps=Word();Out(steps);
    for(std::uint32_t n=0;n<steps;++n) { const auto flags=Word();state.flags_1360|=flags;const auto input=SpeedInput();for(float v:UpdateSpeedModel(state,settings,input))Out(v);Out(state.target_speed);Out(state.flags_1360); }break;
   }
   case 4: {
    BoardForceQueue q;const auto fill=Word();for(std::uint32_t n=0;n<fill;++n) { const QueuedPointForce f{Word(),Three(),Three()};if(!q.Append(f))return 2; }Out(q);const auto steps=Word();Out(steps);
    for(std::uint32_t n=0;n<steps;++n) { if(Word())q.Clear();const auto input=GroundInput();const auto settings=GroundSettings();auto suppressed=std::uint8_t(Word());const bool manual=Word()!=0;const auto force=Four(),point=Four();const auto result=CalculateGroundPropulsion(input,settings,suppressed);Out(std::uint32_t(suppressed));Out(result.braking);Out(result.push);const auto submission=result.Submit(ManualEffect{{},{},{},force,point,manual,false},q);Out(std::uint32_t(submission.manual_correction));Out(std::uint32_t(submission.appended[0]));if(!submission.manual_correction)Out(std::uint32_t(submission.appended[1]));Out(q); }break;
   }
   case 5: { const auto input=Push();const auto limits=Limits();const auto count=Word();std::vector<float> masses;for(std::uint32_t n=0;n<count;++n)masses.push_back(Float());BoardForceQueue q;Out(EnqueuePush(input,limits,masses,q));Out(q);break; }
   case 6: { float output=12.75f;const bool ok=NormalizeManualAngle(Float(),output);Out(std::uint32_t(ok));Out(output);break; }
   case 7: {
    const auto settings=ManualSettingsInput();const ManualMode mode{Float(),Word()!=0};ManualState state{Float(),Float(),Float(),Float(),Float()};Measurement measurement;Out(state);measurement.Snapshot();const auto steps=Word();Out(steps);
    for(std::uint32_t n=0;n<steps;++n) {
     const auto cmd=Word();Out(cmd);
     if(cmd==0)state.Reset();else if(cmd==1){const auto category=Word();Out(std::uint32_t(state.EnterGround(category,Float())));}
     else if(cmd==2){measurement.mode=Word();measurement.supplied=Float();const auto input=ManualInputs();ManualError error;const auto result=CalculateManual(state,settings,mode,input,measurement,error);Out(std::uint32_t(bool(result)));if(result)Out(*result);else Out(std::uint32_t(error.kind));}
     else return 2;Out(state);measurement.Snapshot();
    }break;
   }
   default:return 2;
  }out[mark]=std::uint32_t(out.size()-mark-1);
 }if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto word:out)for(unsigned i=0;i<4;++i)std::cout.put(char(word>>(8*i)));
}
