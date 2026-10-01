// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionOffboardTiming.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> File(const char* p) {std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& b):DataReader{b} {at=0;}
    Vec4 Vector() {Vec4 out;for (auto& v:out) v=Float();return out;}
    IntentMap Map() {IntentMap out;const auto count=Word();for (std::uint32_t i=0;i<count;++i) {const auto n=String();out.Insert(n,Float());}return out;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    void Name(AttributeName n) {for (auto v:n) Word(v);}
    void Attribute(const AnimationAttribute& a) {Name(a.name);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto v:a.payload) {Word(bool(v));if (v) Word(*v);}}
    void Scalar(bool ok,float value,std::string_view e) {Word(ok);if (ok) Float(value);else String(e);}
    void Status(bool ok,std::string_view e) {Word(ok);String(ok?"":e);}
};
}
int main(int argc,char** argv)
{
    if (argc!=5) return 2;std::string error;AnimationMetadata metadata,other,fixture;Graph graph;GraphBinding binding;
    if (!metadata.Load(File(argv[1]),error) || !other.Load(File(argv[2]),error) || !metadata.Merge(other,error) || !fixture.Load(File(argv[3]),error) || !metadata.Merge(fixture,error) || !graph.Load(File(argv[4]),error) || !binding.Bind(graph,error)) {std::cerr<<error;return 2;}
    std::vector<GraphMotionOffboardTimingOperation> operations;std::vector<MotionGraphOffboardTimingInstance> instances;for (const auto& op:binding.operations) {GraphMotionOffboardTimingOperation out;bool recognized;if (op.kind!=GraphOperationKind::Behavior || !ParseGraphMotionOffboardTimingOperation(GraphAttributes(graph.elements[op.element].attributes),out,recognized,error) || !recognized) return 2;operations.push_back(out);instances.push_back(CreateMotionGraphOffboardTimingInstance(out));}
    MotionAnimation animation(std::move(metadata));animation.tree.skater_animation_flags=0x08020000;animation.tree.posture_bank_valid=true;const ChannelSettings settings{0,true,false,1,0,false,0,false,true};bool created;
    for (unsigned i=0;i<7;++i) if (!animation.NewChannel("TimingProbe"+std::to_string(i),"TIMING_OBSERVER_"+std::to_string(i),settings,created,error) || !created) return 2;float animation_phase=0;
    std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input r(bytes);Output out;const auto count=r.Word();out.Word(count);
    for (std::uint32_t tick=0;tick<count;++tick)
    {
        const auto id=r.Word(),phase=r.Word(),allocate=r.Word(),play=r.Word(),inject=r.Word();const auto dt=r.Float();std::optional<float> cadence;if (r.Word()) cadence=r.Float();std::optional<MotionGraphOffboardAirTiming> air;if (r.Word()) air=MotionGraphOffboardAirTiming{r.Float(),r.Float(),r.Vector()};
        std::optional<MotionGraphRunoutObservation> runout;if (r.Word()) runout=MotionGraphRunoutObservation{r.Word()!=0,r.Vector(),r.Vector(),r.Vector(),r.Vector(),r.Word()!=0};
        if (id>=operations.size() || phase>2) return 2;if (allocate) instances[id]=CreateMotionGraphOffboardTimingInstance(operations[id]);if (play) {if (!animation.Play({"TIMING_MAIN",1,0,{1,0,0,0,false}},created,error) || !created) return 2;}
        animation.BeginGraphUpdate();if (inject) {animation.SetAttribute({EncodeAnimationName("BipedStartAngle"),-123,false,-1});animation.SetAttribute({EncodeAnimationName("BipedSpeed"),-1,false,-1});}const auto ok=operations[id].Execute(instances[id],{animation,animation_phase,cadence,air,runout},std::uint8_t(phase),error);out.String(ok?"":"MotionGraph behavior "+std::to_string(id)+": "+error);
        bool done=animation.ApplyParameters(error);out.Status(done,error);done=animation.Advance(dt,animation_phase,error);out.Status(done,error);done=animation.RefreshTreeAttributes(error);out.Status(done,error);out.Float(animation_phase);
        float value=0;done=animation.CurrentTime(value,error);out.Scalar(done,value,error);done=animation.CurrentLength(value,error);out.Scalar(done,value,error);out.Word(std::uint32_t(animation.tree.tree_attributes.size()));for (const auto& a:animation.tree.tree_attributes) out.Attribute(a);
    }
    if (!r.ok || r.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}
