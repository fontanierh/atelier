#include "AnimationPublication.h"
#include "DataReader.h"
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input:detail::DataReader
{
 explicit Input(const std::vector<std::uint8_t>& b):DataReader{b} {}
 bool Bool() {return Word()!=0;}
 std::vector<Mat4> Matrices() {const auto n=Word();std::vector<Mat4> ms;for (std::uint32_t i=0;i<n;++i) {Mat4 m;for (auto& r:m) for (auto& f:r) f=Float();ms.push_back(m);}return ms;}
 SkaterPublicationState Publication() {SkaterPublicationState p;p.orientation_bit31=Bool();p.mirrored=Bool();p.riding_fakie=Bool();p.weight_on_nose=Bool();p.relative_stance=std::int32_t(Word());p.natural_stance=std::int32_t(Word());p.request_bit16=Bool();p.request_bit15=Bool();p.air_dismount_revert_requested=Bool();p.air_dismount_revert_frames=std::int32_t(Word());if (Bool()) {AnimationSignal s;s.name_hash=Word();s.active=std::uint8_t(Word());p.signal=s;}return p;}
 PhysicsPosePacket Packet() {PhysicsPosePacket p;p.bone_count=Word();p.hierarchy=Matrices();p.local=Matrices();p.timestep=Float();for (auto& v:p.foot_surface_ids) v=Word();p.flags=Word();p.board_flipped=Bool();p.mirrored=Bool();p.riding_switch=Bool();p.riding_fakie=Bool();p.weight_forwards=Bool();p.regular_stance=Bool();p.air_dismount_revert_frames=std::int32_t(Word());return p;}
 AnimationAdditionalResetFields Fields() {AnimationAdditionalResetFields f;f.compression=Float();for (auto& v:f.foot_ik_influence) v=Float();f.next_step_position_valid=Bool();f.actor_flag_1904_bit23=Bool();f.actor_flag_1908_bit2=Bool();f.external_impulse_active=Bool();f.external_physics_input_active=Bool();f.externally_controlled=Bool();f.prevent_manual_respawn=Bool();f.ignore_respawn_reset_button=std::uint8_t(Word());f.force_braking=Bool();f.truck_tightness=Float();f.wheel_hardness=Float();for (auto& v:f.auxiliary_vectors) for (auto& x:v) x=Float();f.requested_physics_mode=Word();return f;}
};
static void Word(std::uint32_t w) {for (unsigned i=0;i<4;++i) std::cout.put(char(w>>(8*i)));}
static void Float(float f) {std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
static void String(std::string_view s) {Word(std::uint32_t(s.size()));std::cout.write(s.data(),s.size());}
static void Status(bool ok,const std::string& e) {Word(ok);if (!ok) String(e);}
static void Matrices(const std::vector<Mat4>& ms) {Word(std::uint32_t(ms.size()));for (const auto& m:ms) for (const auto& r:m) for (auto f:r) Float(f);}
static void Publication(const SkaterPublicationState& p) {Word(p.orientation_bit31);Word(p.mirrored);Word(p.riding_fakie);Word(p.weight_on_nose);Word(std::uint32_t(p.relative_stance));Word(std::uint32_t(p.natural_stance));Word(p.request_bit16);Word(p.request_bit15);Word(p.air_dismount_revert_requested);Word(std::uint32_t(p.air_dismount_revert_frames));Word(p.signal.has_value());if (p.signal) {Word(p.signal->name_hash);Word(p.signal->active);}}
static void Packet(const PhysicsPosePacket& p) {Word(p.bone_count);Matrices(p.hierarchy);Matrices(p.local);Float(p.timestep);for (auto v:p.foot_surface_ids) Word(v);Word(p.flags);Word(p.board_flipped);Word(p.mirrored);Word(p.riding_switch);Word(p.riding_fakie);Word(p.weight_forwards);Word(p.regular_stance);Word(std::uint32_t(p.air_dismount_revert_frames));}
static void Fields(const AnimationAdditionalResetFields& f) {Float(f.compression);for (auto v:f.foot_ik_influence) Float(v);Word(f.next_step_position_valid);Word(f.actor_flag_1904_bit23);Word(f.actor_flag_1908_bit2);Word(f.external_impulse_active);Word(f.external_physics_input_active);Word(f.externally_controlled);Word(f.prevent_manual_respawn);Word(f.ignore_respawn_reset_button);Word(f.force_braking);Float(f.truck_tightness);Float(f.wheel_hardness);for (const auto& v:f.auxiliary_vectors) for (auto x:v) Float(x);Word(f.requested_physics_mode);}
int main()
{
 const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);const auto count=input.Word();std::string error;
 for (std::uint32_t i=0;i<count;++i) {switch (input.Word()) {
  case 0:{auto p=input.Packet();auto f=input.Fields();Status(ResetAnimationPacket(p,f,error),error);Packet(p);Fields(f);break;}
  case 1:{auto s=input.Publication();auto p=input.Packet();const auto hierarchy=input.Matrices(),local=input.Matrices();const auto lo=input.Word(),hi=input.Word();const std::uint64_t w=lo|(std::uint64_t(hi)<<32);double dt;std::memcpy(&dt,&w,8);const auto name=input.String();std::int32_t result=0;const bool ok=PublishAnimationEvaluated(s,hierarchy,local,p,dt,name,result,error);Status(ok,error);if (ok) Word(std::uint32_t(result));Publication(s);Packet(p);break;}
  case 2:Word(AnimationSignalHash(input.String()));break;
  case 3:{AnimationPublication actor(input.Bool());auto requested=input.Word();const auto n=input.Word();Word(actor.flags);Float(actor.phase);Publication(actor.publication);Word(actor.Mirrored());Word(actor.Fakie());Word(actor.Switch());Float(actor.CullThreshold());Word(actor.CheckpointStance());Word(requested);for (std::uint32_t j=0;j<n;++j) {switch (input.Word()) {case 0:actor.flags=input.Word();actor.publication=input.Publication();actor.phase=input.Float();break;case 1:{const auto n=input.Word();std::vector<AnimationAttribute> attrs;for (std::uint32_t k=0;k<n;++k) {AnimationAttribute a;for (auto& w:a.name) w=input.Word();attrs.push_back(a);}actor.ApplyStanceEvents(attrs);break;}case 2:actor.PreparePublication();break;case 3:actor.FinishPublication();break;case 4:requested=actor.RequestedStanceForFoot(input.Word());break;default:return 2;}Word(actor.flags);Float(actor.phase);Publication(actor.publication);Word(actor.Mirrored());Word(actor.Fakie());Word(actor.Switch());Float(actor.CullThreshold());Word(actor.CheckpointStance());Word(requested);}break;}
  default:return 2;
 }}if (!input.ok||input.Remaining()!=0) return 2;return std::cout?0:2;
}
