// SPDX-License-Identifier: Apache-2.0
#include "AnimationAirborne.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes} {at=0;}
    bool Boolean() {return Word()!=0;}
    Vec4 Vector() {Vec4 v;for (auto& f:v) f=Float();return v;}
    IntentMap Map() {IntentMap map;const auto n=Word();for (std::uint32_t i=0;i<n;++i) {const auto name=String();map.Insert(name,Float());}return map;}
};
std::vector<std::uint8_t> File(const char* path) {std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Output
{
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(char(v>>(i*8)));}
    void Float(float f) {std::uint32_t word;std::memcpy(&word,&f,4);Word(word);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));std::cout.write(s.data(),s.size());}
    void Status(bool ok,const std::string& error) {Word(ok);if (!ok) String(error);}
    void Attribute(const AnimationAttribute& a) {for (const auto w:a.name) Word(w);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (const auto w:a.payload) {Word(bool(w));if (w) Word(*w);}}
    void Commands(const std::vector<PoseCommand>& commands)
    {
        Word(std::uint32_t(commands.size()));
        for (const auto& c:commands)
        {
            Word(std::uint32_t(c.kind));switch (c.kind)
            {
            case PoseCommand::Kind::Clip:String(c.name);Float(c.previous_time);Float(c.time);Word(c.loops);break;
            case PoseCommand::Kind::Blend:Float(c.weight);break;
            case PoseCommand::Kind::WeightedBlend:Word(std::uint32_t(c.weights.size()));for (const auto w:c.weights) Float(w);break;
            case PoseCommand::Kind::ChannelBlend:Float(c.weight);Word(c.use_channels_from_weights);break;
            case PoseCommand::Kind::Pose:String(c.name);break;
            case PoseCommand::Kind::Add:Word(c.motion_is_a);break;
            case PoseCommand::Kind::Mirror:Word(c.trajectory_mode);break;
            }
        }
    }
};
}
int main(int argc,char** argv)
{
    if (argc!=6) return 2;
    AnimationMetadata metadata,other,fixture;Graph graph;SettingsDatabase data;std::string error;
    if (!metadata.Load(File(argv[1]),error)||!other.Load(File(argv[2]),error)||!metadata.Merge(other,error)||!fixture.Load(File(argv[3]),error)||!metadata.Merge(fixture,error)||!graph.Load(File(argv[4]),error)||!data.Load(File(argv[5]),error)) {std::cerr<<error;return 2;}
    GraphBinding binding;if (!binding.Bind(graph,error)) {std::cerr<<error;return 2;}
    std::vector<GraphMotionAirborneOperation> operations;std::vector<GraphMotionAirborneInstance> instances;
    for (const auto& source:binding.operations)
    {
        GraphMotionAirborneOperation op;bool recognized;
        if (source.kind!=GraphOperationKind::Behavior||!ParseGraphMotionAirborneOperation(GraphAttributes(graph.elements[source.element].attributes),op,recognized,error)||!recognized) {std::cerr<<error;return 2;}
        instances.push_back(CreateGraphMotionAirborneInstance(op));operations.push_back(op);
    }
    AnimationAirborneSettings settings;if (!LoadAnimationAirborneSettings(data,settings,error)) {std::cerr<<error;return 2;}
    MotionAnimation animation(std::move(metadata));animation.tree.posture_bank_valid=true;animation.tree.skater_animation_flags=0x08020000;
    const auto play=[&](std::string_view name) {PlaybackRequest request;request.animation=name;request.speed=1;request.transition.kind=1;bool played;return animation.Play(request,played,error)&&animation.RefreshTreeAttributes(error);};
    if (!play("AIR_INITIAL_NONE")) {std::cerr<<error;return 2;}
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);Output out;
    const auto count=input.Word();std::vector<std::string> names;for (std::uint32_t i=0;i<count;++i) names.push_back(input.String());
    for (std::size_t i=0;i<names.size();++i) {const ChannelSettings channel{0,true,false,1,0,false,0,false,false};bool created;if (!animation.NewChannel("OBS"+std::to_string(i),"OBS_TREE"+std::to_string(i),channel,created,error)) {std::cerr<<error;return 2;}}
    const auto rows=input.Word();out.Word(rows);
    for (std::uint32_t row=0;row<rows;++row)
    {
        const auto id=input.Word(),phase=input.Word();const bool allocate=input.Boolean();const auto cache=input.Word();const auto dt=input.Float();const auto mask=input.Word();
        const auto category=input.Word(),physical_state=input.Word();const bool doing=input.Boolean();const std::array<std::uint32_t,2> hands{input.Word(),input.Word()};const bool mirrored=input.Boolean();
        const AnimationAirLegPhysical air{input.Vector(),input.Vector(),input.Vector(),input.Vector(),input.Vector(),input.Float(),input.Boolean(),input.Float()};
        const MotionGraphPrelandingInputs preland{input.Boolean(),input.Float(),input.Float(),input.Float(),input.Boolean(),input.Boolean(),input.Float(),input.Boolean(),input.Float(),input.Float(),input.Float()};
        const auto map=input.Map();if (id>=operations.size()||phase>2) return 2;
        const std::array<std::string_view,4> clips{"AIR_INITIAL_NONE","AIR_INITIAL_FLOAT","AIR_INITIAL_VECTOR","AIR_INITIAL_FULL_VECTOR"};
        if (cache&&(!play(clips[(cache-1)%clips.size()]))) {std::cerr<<error;return 2;}
        animation.BeginGraphUpdate();animation.AcceptMotionEffects(map);
        const auto physical=(mask&1)?std::optional<AnimationAirLegPhysical>(air):std::nullopt;const auto prelanding=(mask&2)?std::optional<MotionGraphPrelandingInputs>(preland):std::nullopt;
        GraphMotionAirborneContext context{animation,settings,physical,prelanding,(mask&4)?std::optional<std::uint32_t>(category):std::nullopt,(mask&8)?std::optional<std::uint32_t>(physical_state):std::nullopt,doing,hands,(mask&16)?std::optional<bool>(mirrored):std::nullopt};
        if (allocate) instances[id]=CreateGraphMotionAirborneInstance(operations[id]);
        const bool ok=ExecuteGraphMotionAirborneOperation(operations[id],instances[id],std::uint8_t(phase),dt,context,error);out.Status(ok,ok?"":"MotionGraph behavior "+std::to_string(id)+": "+error);
        out.Status(animation.ApplyParameters(error),error);out.Status(animation.Advance(dt,0,error),error);out.Status(animation.RefreshTreeAttributes(error),error);
        for (const auto& name:names) {auto a=MotionGraphAttribute{EncodeAnimationName(name),0}.ToAnimation();bool found;const auto query=animation.channels.QueryAttribute(a.name,15,a,found,error);out.Status(query,error);out.Word(found);out.Attribute(a);}
        for (const auto name:{"IA_BODYSPIN_OLLIE_FS_0_N","IA_BODYSPIN_OLLIE_BS_0_N"}) {out.Word(animation.channels.Has(name));out.Float(animation.channels.Elapsed(name));out.Float(animation.channels.Remaining(name));out.Word(animation.channels.InTransition(name));}
        std::vector<PoseCommand> commands;const auto pose=animation.EvaluatePose({.01f,true},commands,error);out.Status(pose,error);if (pose) out.Commands(commands);
    }
    if (!input.ok||input.Remaining()!=0) return 2;return std::cout?0:2;
}
