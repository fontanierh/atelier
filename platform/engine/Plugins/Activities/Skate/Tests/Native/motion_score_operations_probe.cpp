// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionScoreOperations.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> File(const char* path) {std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes} {at=0;}
    IntentMap Map() {IntentMap out;const auto n=Word();for (std::uint32_t i=0;i<n;++i) {const auto name=String();out.Insert(name,Float());}return out;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    void Name(AttributeName n) {for (auto v:n) Word(v);}
    void OptionalName(std::optional<AttributeName> n) {Word(bool(n));if (n) Name(*n);}
    void Vector(const std::optional<MotionGraphScorePacket::NamedVector>& v) {Word(bool(v));if (v) {Name(v->first);for (auto f:v->second) Float(f);}}
    void Attribute(const AnimationAttribute& a) {Name(a.name);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto v:a.payload) {Word(bool(v));if (v) Word(*v);}}
    void Status(bool ok,std::string_view error) {Word(ok);String(ok?"":error);}
    void Scalar(bool ok,float value,std::string_view error) {Word(ok);if (ok) Float(value);else String(error);}
};
}
int main(int argc,char** argv)
{
    if (argc!=5) return 2;std::string error;AnimationMetadata metadata,other,fixture;Graph graph;GraphBinding binding;
    if (!metadata.Load(File(argv[1]),error) || !other.Load(File(argv[2]),error) || !metadata.Merge(other,error) || !fixture.Load(File(argv[3]),error) || !metadata.Merge(fixture,error) || !graph.Load(File(argv[4]),error) || !binding.Bind(graph,error)) {std::cerr<<error;return 2;}
    std::vector<GraphMotionScoreOperation> operations;
    for (const auto& op:binding.operations)
    {
        if (op.kind!=GraphOperationKind::Behavior) return 2;GraphMotionScoreOperation operation;bool recognized;
        if (!ParseGraphMotionScoreOperation(GraphAttributes(graph.elements[op.element].attributes),operation,recognized,error) || !recognized) {std::cerr<<error;return 2;}
        operations.push_back(std::move(operation));
    }
    MotionAnimation animation(std::move(metadata));animation.tree.skater_animation_flags=0x08020000;animation.tree.posture_bank_valid=true;
    MotionConditionRandom random;MotionGraphScorePacket score;MotionGraphMovingObjectRegistry moving;PlaybackContext context{false,false,true,EncodeAnimationName("Loose"),std::nullopt};const std::pair<bool,bool> height_settings{true,true};
    const ChannelSettings channel_settings{0,true,false,1,0,false,0,false,true};
    bool created;if (!animation.NewChannel("ProbeX","PROBE_TWEAK_X",channel_settings,created,error) || !animation.NewChannel("ProbeY","PROBE_TWEAK_Y",channel_settings,created,error)) {std::cerr<<error;return 2;}
    std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input r(bytes);Output out;
    const auto commands=r.Word();out.Word(commands);
    for (std::uint32_t tick=0;tick<commands;++tick)
    {
        const auto id=r.Word(),phase=r.Word(),clip=r.Word(),mirror=r.Word(),reset_score=r.Word();const auto channel_mask=r.Word();const auto dt=r.Float();
        animation.motion_intents=r.Map();animation.filtered_intents=r.Map();context.is_mirrored=mirror?std::optional<bool>(mirror==2):std::nullopt;if (reset_score) score=MotionGraphScorePacket{};
        if (id>=operations.size() || phase>2) return 2;animation.BeginGraphUpdate();
        if (clip)
        {
            bool played;const PlaybackRequest request{clip==1?"PROBE_EMPTY":"PROBE_HEIGHT",1,0,{1,0,0,0,false}};
            if (!animation.Play(request,played,error) || !played || !animation.RefreshTreeAttributes(error)) {std::cerr<<error;return 2;}
        }
        for (unsigned i=0;i<2;++i) if (channel_mask&(1u<<i))
            if (!animation.NewChannel(i==0?"SKCH_2H_SHIMMY_LEFT_CHANNEL":"SKCH_2H_SHIMMY_RIGHT_CHANNEL","PROBE_EMPTY",channel_settings,created,error)) {std::cerr<<error;return 2;}
        const bool success=operations[id].Execute({animation,random,score,moving,context,height_settings},std::uint8_t(phase),error);out.String(success?"":"MotionGraph behavior "+std::to_string(id)+": "+error);
        bool ok=animation.ApplyParameters(error);out.Status(ok,error);ok=animation.Advance(dt,0,error);out.Status(ok,error);ok=animation.RefreshTreeAttributes(error);out.Status(ok,error);
        out.Vector(score.handplant);out.Vector(score.grab);for (auto n:score.trick_names) out.OptionalName(n);out.Word(bool(score.name));if (score.name) out.Word(*score.name);out.Word(score.flags);out.Word(moving.Active());
        out.Word(std::uint32_t(animation.tree.construction_values.size()));for (auto v:animation.tree.construction_values) {out.Name(v.first);out.Name(v.second);}
        out.Word(std::uint32_t(animation.motion_attributes.size()));for (auto a:animation.motion_attributes) {out.Name(a.name);out.Float(a.value);}
        out.Word(std::uint32_t(animation.tree.tree_attributes.size()));for (const auto& a:animation.tree.tree_attributes) out.Attribute(a);
        for (auto channel:{"ProbeX","ProbeY","SKCH_2H_SHIMMY_LEFT_CHANNEL","SKCH_2H_SHIMMY_RIGHT_CHANNEL"}) {out.Word(animation.channels.Has(channel));out.Float(animation.channels.Remaining(channel));out.Float(animation.channels.Elapsed(channel));out.Word(animation.channels.InTransition(channel));}
        float value=0;ok=animation.CurrentTime(value,error);out.Scalar(ok,value,error);ok=animation.CurrentLength(value,error);out.Scalar(ok,value,error);
    }
    if (!r.ok || r.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}
