#include "GraphMotionFeedbackOperations.h"
#include "SkaterAnimation.h"
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
    bool Bool() {return Word()!=0;}
    Vec4 Vector() {Vec4 v;for (auto& f:v) f=Float();return v;}
    IntentMap Map() {IntentMap out;const auto n=Word();for (std::uint32_t i=0;i<n;++i) {const auto name=String();out.Insert(name,Float());}return out;}
    AnimationCrouchingPhysical Crouch() {return {Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float()};}
    AnimationBodyTiltPhysical Tilt() {return {Float(),Float(),Word()};}
    AnimationFakiePhysical Fakie() {return {Word(),Word(),Bool(),Vector(),Vector(),Vector(),Float()};}
};
std::vector<std::uint8_t> File(const char* path) {std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(char(v>>(i*8)));}
void Float(float f) {std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
void String(std::string_view s) {Word(std::uint32_t(s.size()));std::cout.write(s.data(),s.size());}
void Status(bool ok,const std::string& error) {Word(ok);if (!ok) String(error);}
void Attribute(const AnimationAttribute& a) {for (auto w:a.name) Word(w);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto w:a.payload) {Word(bool(w));if (w) Word(*w);}}
void Commands(const std::vector<PoseCommand>& commands)
{
    Word(std::uint32_t(commands.size()));
    for (const auto& c:commands)
    {
        Word(std::uint32_t(c.kind));switch (c.kind)
        {
        case PoseCommand::Kind::Clip:String(c.name);Float(c.previous_time);Float(c.time);Word(c.loops);break;
        case PoseCommand::Kind::Blend:Float(c.weight);break;
        case PoseCommand::Kind::WeightedBlend:Word(std::uint32_t(c.weights.size()));for (auto w:c.weights) Float(w);break;
        case PoseCommand::Kind::ChannelBlend:Float(c.weight);Word(c.use_channels_from_weights);break;
        case PoseCommand::Kind::Pose:String(c.name);break;
        case PoseCommand::Kind::Add:Word(c.motion_is_a);break;
        case PoseCommand::Kind::Mirror:Word(c.trajectory_mode);break;
        }
    }
}
}
int main(int argc,char** argv)
{
    if (argc!=6) return 2;
    AnimationMetadata metadata,other,fixture;Graph graph;SettingsDatabase data;std::string error;
    if (!metadata.Load(File(argv[1]),error)||!other.Load(File(argv[2]),error)||!metadata.Merge(other,error)||!fixture.Load(File(argv[3]),error)||!metadata.Merge(fixture,error)||!graph.Load(File(argv[4]),error)||!data.Load(File(argv[5]),error)) {std::cerr<<error;return 2;}
    GraphBinding binding;if (!binding.Bind(graph,error)) {std::cerr<<error;return 2;}
    std::vector<GraphMotionFeedbackOperation> operations;
    std::vector<GraphMotionFeedbackInstance> instances;
    for (const auto& source:binding.operations)
    {
        if (source.kind!=GraphOperationKind::Behavior) return 2;
        GraphMotionFeedbackOperation op;bool recognized;
        if (!ParseGraphMotionFeedbackOperation(GraphAttributes(graph.elements[source.element].attributes),op,recognized,error)||!recognized) {std::cerr<<error;return 2;}
        instances.push_back(CreateGraphMotionFeedbackInstance(op));operations.push_back(std::move(op));
    }
    MotionAnimation animation(std::move(metadata));GraphMotionFeedbackSettings settings;
    if (!LoadGraphMotionFeedbackSettings(data,settings,error)||!animation.tree.SetHierarchy({"LeftToeBase","RightToeBase"},{1,0},error)) {std::cerr<<error;return 2;}
    animation.tree.posture_bank_valid=true;animation.tree.skater_animation_flags=0x08020000;
    PlaybackRequest request;request.animation="R_STAND_IDLE2_N_0_CYC";request.speed=1;request.transition.kind=1;bool played;
    if (!animation.Play(request,played,error)) {std::cerr<<error;return 2;}
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);
    const auto names_count=input.Word();std::vector<std::string> names;
    for (std::uint32_t i=0;i<names_count;++i) names.push_back(input.String());
    for (std::size_t i=0;i<names.size();++i)
    {
        const ChannelSettings channel{0,true,false,1,0,false,0,false,false};bool created;
        if (!animation.NewChannel("OBS"+std::to_string(i),"OBS_TREE"+std::to_string(i),channel,created,error)) {std::cerr<<error;return 2;}
    }
    GraphMotionFeedbackOwner owner;SlideLatch latch;const auto steps=input.Word();Word(steps);
    graph::Frame frame;frame.current=0;frame.state_times={0.0f};
    for (std::uint32_t tick=0;tick<steps;++tick)
    {
        frame.dt=input.Float();const auto intents=input.Map();const auto mask=input.Word();const auto flags=input.Word();const bool mirrored=input.Bool(),doing=input.Bool(),sliding=input.Bool(),tilting=input.Bool();
        for (auto& w:latch.words) w=input.Word();
        const SetTurningPhysical turn{input.Float(),input.Float(),input.Float(),input.Float(),input.Float(),input.Float()};
        const auto crouch=input.Crouch();const auto tilt=input.Tilt();const auto fakie=input.Fakie();const auto pump=input.Float();const std::array<float,2> deck{input.Float(),input.Float()};
        animation.tree.skater_animation_flags=(mask&128)?std::optional<std::uint32_t>(flags):std::nullopt;animation.BeginGraphUpdate();animation.AcceptMotionEffects(intents);
        GraphMotionFeedbackContext context{animation,owner,latch,settings};context.turning=(mask&1)?&turn:nullptr;context.crouching=(mask&2)?&crouch:nullptr;context.body_tilt=(mask&4)?&tilt:nullptr;context.fakie=(mask&8)?&fakie:nullptr;context.pumping_acceleration=(mask&16)?&pump:nullptr;context.deck_yaw_pitch=(mask&32)?&deck:nullptr;context.mirrored=(mask&64)?std::optional<bool>(mirrored):std::nullopt;context.doing_trick=doing;context.is_power_sliding=sliding;context.applying_body_tilt=tilting;
        const auto calls=input.Word();Word(calls);
        for (std::uint32_t i=0;i<calls;++i)
        {
            const auto id=input.Word(),phase=input.Word();if (id>=operations.size()) return 2;
            if (phase==0) instances[id]=CreateGraphMotionFeedbackInstance(operations[id]);
            const bool ok=ExecuteGraphMotionFeedbackOperation(operations[id],instances[id],std::uint8_t(phase),frame,context,error);
            Status(ok,ok?"":"MotionGraph behavior "+std::to_string(id)+": "+error);
        }
        Word(owner.allow_pumping);Word(bool(animation.tree.skater_animation_flags));if (animation.tree.skater_animation_flags) Word(*animation.tree.skater_animation_flags);for (auto w:latch.words) Word(w);
        Word(std::uint32_t(animation.motion_attributes.size()));for (const auto& a:animation.motion_attributes) {for (auto w:a.name) Word(w);Float(a.value);}
        Status(animation.ApplyParameters(error),error);Status(animation.Advance(frame.dt,0.137f,error),error);Status(animation.RefreshTreeAttributes(error),error);
        for (const auto& name:names)
        {
            auto a=MotionGraphAttribute{EncodeAnimationName(name),0}.ToAnimation();bool found;const bool ok=animation.channels.QueryAttribute(a.name,15,a,found,error);Status(ok,error);Word(found);Attribute(a);
        }
        for (const auto name:{"PUMP0","PUMP1","PUMP2","PUMP3","PUMP4"}) {Word(animation.channels.Has(name));Float(animation.channels.Elapsed(name));Float(animation.channels.Remaining(name));Word(animation.channels.InTransition(name));}
        Word(std::uint32_t(animation.tree.tree_attributes.size()));for (const auto& a:animation.tree.tree_attributes) Attribute(a);
        const auto property=animation.tree.property;Word(property.crossed_end);Float(property.overshoot);Float(property.remaining_before_wrap);
        std::vector<PoseCommand> commands;const bool evaluated=animation.EvaluatePose({0.01f,true},commands,error);Status(evaluated,error);if (evaluated) Commands(commands);
    }
    if (!input.ok||input.Remaining()!=0) return 2;
    return std::cout?0:2;
}
