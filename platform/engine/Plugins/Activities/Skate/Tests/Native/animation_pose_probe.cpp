// SPDX-License-Identifier: Apache-2.0
#include "AnimationPose.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input:detail::DataReader
{
 explicit Input(const std::vector<std::uint8_t>& b):DataReader{b} {}
 Sqt Pose() {Sqt p;for (auto* a:{&p.scale,&p.rotation,&p.translation}) for (auto& f:*a) f=Float();return p;}
 std::vector<PoseCommand> Commands() {const auto n=Word();std::vector<PoseCommand> cs;for (std::uint32_t i=0;i<n;++i) {PoseCommand c;c.kind=PoseCommand::Kind(Word());switch (c.kind) {case PoseCommand::Kind::Clip:c.name=String();c.time=Float();c.previous_time=Float();c.loops=Word();break;case PoseCommand::Kind::Blend:c.weight=Float();break;case PoseCommand::Kind::WeightedBlend:{const auto size=Word();for (std::uint32_t j=0;j<size;++j) c.weights.push_back(Float());break;}case PoseCommand::Kind::ChannelBlend:c.weight=Float();c.use_channels_from_weights=Word()!=0;break;case PoseCommand::Kind::Pose:c.name=String();break;case PoseCommand::Kind::Add:c.motion_is_a=Word()!=0;break;case PoseCommand::Kind::Mirror:c.trajectory_mode=Word();break;}cs.push_back(std::move(c));}return cs;}
};
static void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(char(v>>(i*8)));}
static void String(std::string_view s) {Word(std::uint32_t(s.size()));std::cout.write(s.data(),s.size());}
static void Float(float f) {std::uint32_t v;std::memcpy(&v,&f,4);Word(v);}
static void Pose(Sqt p) {for (const auto* a:{&p.scale,&p.rotation,&p.translation}) for (const auto f:*a) Float(f);}
static bool Status(bool ok,const std::string& e) {Word(ok);if (!ok) String(e);return ok;}
static std::vector<std::uint8_t> Read(const std::filesystem::path& path) {std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};}
int main(int argc,char** argv)
{
 if (argc!=3) return 1;const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);input.at=8;const auto cases=input.Word(),n=input.Word();std::string error;AnimationPoseFrames frames;const std::filesystem::path native(argv[1]),root(argv[2]);
 if (!frames.rig.Load(Read(native/"rig.skate"),error)) {std::cerr<<error;return 2;}for (std::uint32_t i=0;i<n;++i) {auto c=std::make_shared<AnimationClipSamples>();if (!c->Load(Read(native/"clips"/(input.String()+".skate")),error)||!frames.RegisterClip(c,error)) {std::cerr<<error;return 2;}}
 AnimationPoseEvaluator evaluator(std::move(frames));const auto authored=root/"private/custom/crouch-treflip.json";std::filesystem::create_directories(authored.parent_path());
 for (std::uint32_t i=0;i<cases;++i) {switch (input.Word())
 {
  case 0:{const auto text=input.String();{std::ofstream file(authored);file<<text;}Status(evaluator.LoadAuthoredClips(root,error),error);break;}
  case 1:{const auto owner=input.String(),text=input.String();Status(evaluator.InstallModClips(owner,text,error),error);break;}
  case 2:evaluator.RemoveModClips(input.String());Status(true,error);break;
  case 3:evaluator.ClearModClips();Status(true,error);break;
  case 4:{const auto cs=input.Commands();std::vector<Sqt> p;if (Status(evaluator.Evaluate(cs,p,error),error)) {Word(std::uint32_t(p.size()));for (const auto& s:p) Pose(s);std::vector<Mat4> m;if (Status(evaluator.Hierarchy(p,m,error),error)) {Word(std::uint32_t(m.size()));for (const auto& matrix:m) for (const auto& column:matrix) for (auto v:column) Float(v);}}break;}
  case 5:{auto size=input.Word();std::vector<Sqt> p;for (std::uint32_t j=0;j<size;++j) p.push_back(input.Pose());size=input.Word();std::vector<std::int32_t> parents;for (std::uint32_t j=0;j<size;++j) parents.push_back(std::int32_t(input.Word()));size=input.Word();std::vector<std::int32_t> mirrors;for (std::uint32_t j=0;j<size;++j) mirrors.push_back(std::int32_t(input.Word()));const auto mode=input.Word();Status(MirrorAnimationPose(p,parents,mirrors,mode,error),error);Word(std::uint32_t(p.size()));for (const auto& s:p) Pose(s);break;}
  case 6:{const auto a=input.Pose(),b=input.Pose();std::optional<AnimationLoopTransform> l;if (input.Word()!=0) {AnimationLoopTransform t;for (auto& f:t.rotation) f=input.Float();for (auto& f:t.translation) f=input.Float();l=t;}Pose(AnimationTrajectoryDelta(a,b,l));break;}
  case 7:{const auto a=input.Pose(),b=input.Pose();Pose(AddAnimationPose(a,b,input.Word()!=0));break;}
  default:return 2;
 }}
 if (!input.ok||input.Remaining()!=0) return 2;return std::cout?0:2;
}
