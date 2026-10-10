#include "GraphMotionPushOperations.h"
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
    MotionGraphPushState State() {MotionGraphPushState s;s.out_factor=Float();s.current_push_dv=Float();s.current={Float(),Float(),Float()};s.target={Float(),Float(),Float()};s.continue_push=Word()!=0;return s;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    void Name(AttributeName n) {for (auto v:n) Word(v);}
    void State(const std::optional<MotionGraphPushState>& s) {Word(bool(s));if (s) {Float(s->out_factor);Float(s->current_push_dv);for (auto v:{s->current.hstr_vel_b,s->current.lstr_vel_b,s->current.vel_e,s->target.hstr_vel_b,s->target.lstr_vel_b,s->target.vel_e}) Float(v);Word(s->continue_push);}}
    void Attribute(const AnimationAttribute& a) {Name(a.name);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto v:a.payload) {Word(bool(v));if (v) Word(*v);}}
    void Status(bool ok,std::string_view e) {Word(ok);String(ok?"":e);}
};
}
int main(int argc,char** argv)
{
    if (argc!=6) return 2;std::string error;AnimationMetadata metadata,other,fixture;Graph graph;GraphBinding binding;SettingsDatabase data;
    if (!metadata.Load(File(argv[1]),error) || !other.Load(File(argv[2]),error) || !metadata.Merge(other,error) || !fixture.Load(File(argv[3]),error) || !metadata.Merge(fixture,error) || !graph.Load(File(argv[4]),error) || !binding.Bind(graph,error) || !data.Load(File(argv[5]),error)) {std::cerr<<error;return 2;}
    GraphMotionPushSettings settings;if (!settings.Load(data,metadata,error)) {std::cerr<<error;return 2;}
    std::vector<GraphMotionPushOperation> operations;for (const auto& op:binding.operations) {GraphMotionPushOperation out;bool recognized;if (op.kind!=GraphOperationKind::Behavior || !ParseGraphMotionPushOperation(GraphAttributes(graph.elements[op.element].attributes),out,recognized,error) || !recognized) {std::cerr<<error;return 2;}operations.push_back(std::move(out));}
    std::vector<GraphMotionPushInstance> instances(operations.size());std::optional<MotionGraphPushState> shared=MotionGraphPushState{};
    MotionAnimation animation(std::move(metadata));animation.tree.skater_animation_flags=0x08020000;animation.tree.posture_bank_valid=true;
    const ChannelSettings channel_settings{0,true,false,1,0,false,0,false,true};bool created;
    for (unsigned i=0;i<5;++i) if (!animation.NewChannel("PushProbe"+std::to_string(i),"PUSH_OBSERVER_"+std::to_string(i),channel_settings,created,error) || !created) {std::cerr<<error;return 2;}
    std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input r(bytes);Output out;const auto count=r.Word();out.Word(count);
    for (std::uint32_t tick=0;tick<count;++tick)
    {
        const auto id=r.Word(),phase=r.Word(),allocate=r.Word(),mode=r.Word(),physical_kind=r.Word(),is_switch=r.Word();const auto speed=r.Float(),teleport=r.Float(),dt=r.Float();
        if (mode==1) shared=MotionGraphPushState{};else if (mode==2) shared.reset();else if (mode==3) shared=r.State();
        std::optional<MotionGraphPushPhysical> physical;if (physical_kind) {physical=MotionGraphPushPhysical{speed,is_switch!=0,std::nullopt};if (physical_kind==2) physical->foot_frame=MotionGraphFootFrame{r.Vector(),r.Vector(),r.Vector(),r.Vector(),r.Vector(),r.Word()!=0};}
        animation.motion_intents=r.Map();animation.BeginGraphUpdate();if (id>=operations.size() || phase>2) return 2;if (allocate) instances[id]=GraphMotionPushInstance{};
        const bool success=operations[id].Execute(instances[id],{settings,shared,animation,physical,teleport,dt},std::uint8_t(phase),error);out.String(success?"":"MotionGraph behavior "+std::to_string(id)+": "+error);
        bool ok=animation.ApplyParameters(error);out.Status(ok,error);ok=animation.Advance(dt,0,error);out.Status(ok,error);ok=animation.RefreshTreeAttributes(error);out.Status(ok,error);
        out.State(shared);out.Word(std::uint32_t(animation.tree.tree_attributes.size()));for (const auto& a:animation.tree.tree_attributes) out.Attribute(a);
    }
    if (!r.ok || r.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}
