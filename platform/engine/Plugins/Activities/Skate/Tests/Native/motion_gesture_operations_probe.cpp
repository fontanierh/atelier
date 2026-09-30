// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionGestureOperations.h"
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
    void Status(bool ok,std::string_view e) {Word(ok);String(ok?"":e);}
};
}
int main(int argc,char** argv)
{
    if (argc!=5) return 2;std::string error;AnimationMetadata metadata,other,fixture;Graph graph;GraphBinding binding;
    if (!metadata.Load(File(argv[1]),error) || !other.Load(File(argv[2]),error) || !metadata.Merge(other,error) || !fixture.Load(File(argv[3]),error) || !metadata.Merge(fixture,error) || !graph.Load(File(argv[4]),error) || !binding.Bind(graph,error)) {std::cerr<<error;return 2;}
    struct Operation {unsigned kind;GraphMotionShoveOperation shove;};std::vector<Operation> operations;
    for (const auto& op:binding.operations) {if (op.kind!=GraphOperationKind::Behavior) return 2;GraphAttributes attrs(graph.elements[op.element].attributes);GraphMotionShoveOperation shove;MotionGraphGestureOperation gesture;bool recognized;
        if (!ParseGraphMotionShoveOperation(attrs,shove,recognized,error)) return 2;if (recognized) operations.push_back({2,std::move(shove)});else {if (!ParseMotionGraphGestureOperation(attrs,gesture,recognized,error) || !recognized) return 2;operations.push_back({gesture==MotionGraphGestureOperation::Character?0u:1u,{}});}}
    std::vector<MotionGraphCharacterGestureState> gestures(operations.size());std::vector<MotionGraphShoveState> shoves(operations.size());std::optional<MotionGraphGesturePublication> publication;
    MotionAnimation animation(std::move(metadata));animation.tree.skater_animation_flags=0x08020000;animation.tree.posture_bank_valid=true;
    PlaybackContext context{false,false,true,EncodeAnimationName("Loose"),std::nullopt};const ChannelSettings settings{0,true,false,1,0,false,0,false,false},observer{0,true,false,1,0,false,0,false,true};
    bool done;if (!animation.Play({"GESTURE_HEIGHT_OBSERVER",1,0,{1,0,0,0,false}},done,error) || !done || !animation.NewChannel("GestureAngleProbe","GESTURE_ANGLE_OBSERVER",observer,done,error) || !done) {std::cerr<<error;return 2;}
    std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input r(bytes);Output out;const auto count=r.Word();out.Word(count);
    for (std::uint32_t tick=0;tick<count;++tick)
    {
        const auto id=r.Word(),phase=r.Word(),allocate=r.Word(),clear=r.Word(),seed=r.Word(),available=r.Word();const std::array<std::uint32_t,2> hands{r.Word(),r.Word()};const auto keep=r.Word(),category=r.Word(),board=r.Word(),ground=r.Word(),offboard=r.Word(),suppress=r.Word(),bypass=r.Word();
        std::array<std::uint32_t,4> selections;for (auto& v:selections) v=r.Word();const auto interaction=r.Word(),biped=r.Word(),board_ground=r.Word(),mirror=r.Word();const auto height=r.Float(),dt=r.Float();const auto direction=r.Vector();animation.motion_intents=r.Map();animation.BeginGraphUpdate();
        if (id>=operations.size() || phase>2) return 2;context.board_available=available&4?std::optional<bool>(board!=0):std::nullopt;context.is_mirrored=available&32?std::optional<bool>(mirror!=0):std::nullopt;
        if (clear) {animation.channels.ResetFromStock();if (!animation.NewChannel("GestureAngleProbe","GESTURE_ANGLE_OBSERVER",observer,done,error) || !done) return 2;}
        if (seed) {const std::array<std::string_view,3> names{{"RetrieveBoard","WipeoutPushOff","Shove"}};if (!animation.NewChannel(names[seed-1],"GESTURE_EMPTY",settings,done,error)) return 2;}
        if (allocate) {gestures[id]=MotionGraphCharacterGestureState{};shoves[id]=MotionGraphShoveState{};}
        bool success=true;const auto& op=operations[id];
        if (op.kind==0) {std::optional<MotionGraphCharacterGesturePhysical> physical;if (available&1) physical=MotionGraphCharacterGesturePhysical{ground!=0,offboard!=0,available&64?std::optional<std::array<std::uint32_t,4>>(selections):std::nullopt,suppress!=0,bypass!=0};success=ExecuteMotionGraphCharacterGesture(gestures[id],{animation,hands,physical,available&2?std::optional<std::uint32_t>(category):std::nullopt,context,available&8?std::optional<float>(height):std::nullopt,publication},std::uint8_t(phase),error);}
        else if (op.kind==1) {if (phase==0) {for (std::size_t i=0;i<operations.size();++i) if (operations[i].kind==0) gestures[i].End(animation);publication.reset();}error.clear();}
        else {std::optional<MotionGraphShovePhysical> physical;if (available&16) physical=MotionGraphShovePhysical{interaction!=0,direction,biped!=0,board_ground!=0,height};success=ExecuteGraphMotionShoveOperation(op.shove,shoves[id],{animation,physical,hands,context,keep!=0},std::uint8_t(phase),error);}
        out.String(success?"":"MotionGraph behavior "+std::to_string(id)+": "+error);bool ok=animation.ApplyParameters(error);out.Status(ok,error);ok=animation.Advance(dt,0,error);out.Status(ok,error);ok=animation.RefreshTreeAttributes(error);out.Status(ok,error);
        std::vector<PoseCommand> pose;ok=animation.EvaluatePose({0,false},pose,error);out.Status(ok,error);out.Word(bool(publication));if (publication) {out.Word(publication->gesture);out.Word(publication->down);}
        for (auto channel:{"GestureBoth","GestureRight","GestureLeft","SkitchAntic","Shove","RetrieveBoard","WipeoutPushOff"}) {out.Word(animation.channels.Has(channel));out.Float(animation.channels.Remaining(channel));out.Float(animation.channels.Elapsed(channel));out.Word(animation.channels.InTransition(channel));}
        out.Word(std::uint32_t(animation.tree.tree_attributes.size()));for (const auto& a:animation.tree.tree_attributes) out.Attribute(a);
        std::vector<std::string> clips;for (const auto& command:pose) if (command.kind==PoseCommand::Kind::Clip) clips.push_back(command.name);out.Word(std::uint32_t(clips.size()));for (const auto& clip:clips) out.String(clip);
    }
    if (!r.ok || r.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}
