#include "MotionGraphHost.h"
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
    Vec4 Vector() {Vec4 v;for (auto& x:v) x=Float();return v;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
    void Optional(std::optional<float> value) {Word(bool(value));if (value) Float(*value);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    void Map(const IntentMap& m,const std::vector<std::string>& names)
    {Word(std::uint32_t(m.Size()));for (const auto& name:names) {const auto p=m.Get(name);Optional(p?std::optional<float>(*p):std::nullopt);}}
    void Attribute(const AnimationAttribute& a)
    {for (auto v:a.name) Word(v);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto v:a.payload) {Word(bool(v));if (v) Word(*v);}}
    void Scalar(bool ok,float value,std::string_view error) {Word(ok);if (ok) Float(value);else String(error);}
};
}
int main(int argc,char** argv)
{
    if (argc!=5) return 2;std::string error;AnimationMetadata metadata,other;
    if (!metadata.Load(File(argv[1]),error) || !other.Load(File(argv[2]),error) || !metadata.Merge(other,error)) {std::cerr<<error;return 2;}
    Graph graph;if (!graph.Load(File(argv[3]),error)) {std::cerr<<error;return 2;}
    GraphBinding binding;CompiledGraph compiled;SettingsDatabase settings;
    if (!binding.Bind(graph,error) || !compiled.FromBinding(binding,error) || !settings.Load(File(argv[4]),error)) {std::cerr<<error;return 2;}
    MotionAnimation animation(std::move(metadata));MotionGraphHost host(animation);
    host.playback_context={false,false,true,EncodeAnimationName("Loose"),std::nullopt};
    if (!host.FromGraph(graph,binding,compiled,settings,error) || !animation.tree.SetHierarchy({"LeftToeBase","RightToeBase"},{1,0},error)) {std::cerr<<error;return 2;}
    animation.tree.posture_bank_valid=true;animation.tree.skater_animation_flags=0x08020000;
    graph::Controller controller(binding.states.size());std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);Output out;
    const auto count=input.Word();std::vector<std::string> names;for (std::uint32_t i=0;i<count;++i) names.push_back(input.String());
    const auto steps=input.Word();out.Word(steps);
    for (std::uint32_t tick=0;tick<steps;++tick)
    {
        const bool ending=input.Word()!=0;const auto dt=input.Float();const auto action=input.Map(),motion=input.Map();
        animation.tree.skater_animation_flags=input.Word();host.playback_context.is_mirrored=input.Word()!=0;host.playback_context.is_switch=input.Word()!=0;
        host.physical.conditions.physical_state=GraphPhysicalStateInputs{input.Word(),false,""};
        const bool gameplay=input.Word()!=0;const auto state=input.Word();const bool dropping=input.Word()!=0;
        MotionGraphGameplayInputs p{};p.state=state;p.dropping_board=dropping;host.physical.gameplay=gameplay?std::optional<MotionGraphGameplayInputs>(p):std::nullopt;
        host.physical.foot_frame=MotionGraphFootFrame{input.Vector(),input.Vector(),input.Vector(),input.Vector(),input.Vector(),input.Word()!=0};
        for (auto& word:host.slide_latch.words) word=input.Word();host.hold_fakie=input.Word()!=0;
        host.push_state->out_factor=input.Float();host.push_state->continue_push=input.Word()!=0;
        host.time_tags=std::map<std::string,float>{{"probe",input.Float()}};
        animation.BeginGraphUpdate();host.AcceptActionGraph({tick,ActionGraphOutput::FromHost(tick,action,motion,{})});
        if (ending) controller.EndAllBehaviors(host);else controller.Update(compiled.program,dt,host);
        out.Word(std::uint32_t(compiled.operations.conditions.size()));for (std::size_t i=0;i<compiled.operations.conditions.size();++i) out.Word(host.ConditionActivation(std::uint32_t(i),controller.frame));
        const auto graph_error=host.Diagnostics("|");out.String(graph_error);
        const bool applied=animation.ApplyParameters(error);out.Word(applied);out.String(applied?"":error);
        const bool advanced=animation.Advance(dt,host.animation_phase,error);out.Word(advanced);out.String(advanced?"":error);
        const bool refreshed=animation.RefreshTreeAttributes(error);out.Word(refreshed);out.String(refreshed?"":error);
        const auto& frame=controller.frame;out.Float(frame.dt);out.Word(frame.current.value_or(0xffffffff));out.Word(frame.last.value_or(0xffffffff));
        out.Word(std::uint32_t(frame.state_times.size()));for (auto time:frame.state_times) out.Optional(time);
        out.Word(std::uint32_t(controller.active.size()));for (auto active:controller.active) {out.Word(active.behavior);out.Word(active.instance);}
        out.Map(animation.motion_intents,names);out.Map(animation.filtered_intents,names);
        for (bool value:{host.flags.anticipating,host.flags.landing,host.flags.manualing,host.flags.doing_trick,host.flags.tricks_allowed,host.riding.dark,host.is_power_sliding,host.applying_body_tilt,host.keep_shove_channels}) out.Word(value);
        for (auto value:{host.riding.time_since_teleport,host.riding.time_since_kickturn,host.riding.manual_out_timer,host.riding.last_good_landing_velocity}) out.Float(value);
        for (auto hand:host.busy_hands) out.Word(hand);for (auto word:host.slide_latch.words) out.Word(word);
        out.Word(bool(animation.grab_type));if (animation.grab_type) out.Word(std::uint32_t(*animation.grab_type));
        out.Word(*animation.tree.skater_animation_flags);out.Word(animation.relative_stance);out.Word(animation.reset_action_intents);
        out.Word(std::uint32_t(animation.motion_attributes.size()));for (const auto& a:animation.motion_attributes) {for (auto word:a.name) out.Word(word);out.Float(a.value);}
        out.Word(std::uint32_t(animation.tree.tree_attributes.size()));for (const auto& a:animation.tree.tree_attributes) out.Attribute(a);
        const auto property=animation.tree.property;out.Word(property.crossed_end);out.Float(property.overshoot);out.Float(property.remaining_before_wrap);
        float value=0;bool ok=animation.CurrentTime(value,error);out.Scalar(ok,value,error);ok=animation.CurrentLength(value,error);out.Scalar(ok,value,error);out.Word(animation.InTransition());
    }
    if (!input.ok || input.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}
