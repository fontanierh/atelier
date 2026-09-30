// SPDX-License-Identifier: Apache-2.0
#include "SkaterAnimation.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> File(const std::filesystem::path& p) {std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& b):DataReader{b} {at=8;}
    bool Boolean() {return Word()!=0;}
    Vec4 Vector() {Vec4 v;for (auto& f:v) f=Float();return v;}
    IntentMap Map() {IntentMap m;const auto n=Word();for (std::uint32_t j=0;j<n;++j) {const auto name=String();m.Insert(name,Float());}return m;}
    AnimationPhysical Physical()
    {
        AnimationPhysical p;
        if (Boolean()) p.conditions.speeds=GraphSpeedInputs{Float(),Float(),Float()};
        if (Boolean()) {const auto category=Word();const bool grinding=Boolean();p.conditions.physical_state=GraphPhysicalStateInputs{category,grinding,String()};}
        if (Boolean()) p.conditions.time_since_last_input=Float();
        if (Boolean()) p.conditions.mirrored=Boolean();if (Boolean()) p.conditions.riding_fakie=Boolean();
        if (Boolean()) {const auto angle=Float();const bool disabled=Boolean();p.conditions.push_brake=GraphPushBrakeInputs{angle,disabled,Float()};}
        if (Boolean()) p.conditions.physics_requests_dismount=Boolean();if (Boolean()) p.conditions.physical_state_16=Word();
        auto& t=p.feedback.turning;t={Float(),Float(),Float(),Float(),Float(),Float()};
        auto& c=p.feedback.crouching;c={Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float()};
        p.feedback.pumping_acceleration=Float();p.feedback.ground_acceleration=Vector();p.feedback.bumped=Boolean();for (auto& f:p.feedback.conditioned_turn) f=Float();
        p.body_tilt={Float(),Float(),Word()};
        p.fakie={Word(),Word(),Boolean(),Vector(),Vector(),Vector(),Float()};
        const bool a=Boolean(),b=Boolean();p.physical_stance={a,b};p.foot_frame={Vector(),Vector(),Vector(),Vector(),Vector(),Boolean()};
        p.board_present=Boolean();p.physical_28_byte75=Boolean();p.time_since_teleport=Float();return p;
    }
    ChannelSettings Channel() {return {std::int32_t(Word()),Boolean(),Boolean(),Float(),Float(),Boolean(),Float(),Boolean(),Boolean()};}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t word;std::memcpy(&word,&v,4);Word(word);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    void Status(bool ok,std::string_view e) {Word(ok);if (!ok) String(e);}
    void Optional(std::optional<float> value) {Word(bool(value));if (value) Float(*value);}
    void Map(const IntentMap& m,const std::vector<std::string>& names) {Word(std::uint32_t(m.Size()));for (const auto& name:names) {const auto p=m.Get(name);Optional(p?std::optional<float>(*p):std::nullopt);}}
    void Attribute(const AnimationAttribute& a) {for (auto word:a.name) Word(word);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (const auto v:a.payload) {Word(bool(v));if (v) Word(*v);}}
    void Matrices(const std::vector<Mat4>& ms) {Word(std::uint32_t(ms.size()));for (const auto& m:ms) for (const auto& c:m) for (const auto f:c) Float(f);}
    void Frame(const graph::Controller& c) {Float(c.frame.dt);Word(c.frame.current.value_or(0xffffffff));Word(c.frame.last.value_or(0xffffffff));Word(std::uint32_t(c.frame.state_times.size()));for (const auto t:c.frame.state_times) Optional(t);Word(std::uint32_t(c.active.size()));for (const auto a:c.active) {Word(a.behavior);Word(a.instance);}}
    void Reset(const AnimationAdditionalResetFields& r)
    {
        Float(r.compression);for (const auto f:r.foot_ik_influence) Float(f);
        for (const auto b:{r.next_step_position_valid,r.actor_flag_1904_bit23,r.actor_flag_1908_bit2,r.external_impulse_active,r.external_physics_input_active,r.externally_controlled,r.prevent_manual_respawn}) Word(b);
        Word(r.ignore_respawn_reset_button);Word(r.force_braking);Float(r.truck_tightness);Float(r.wheel_hardness);for (const auto& v:r.auxiliary_vectors) for (const auto f:v) Float(f);Word(r.requested_physics_mode);
    }
    void Snapshot(SkaterAnimation& a,const AnimationAdditionalResetFields& reset,const std::vector<std::string>& names)
    {
        Word(std::uint32_t(a.ticks));Word(std::uint32_t(a.ticks>>32));const auto stance=a.Stance();Word(stance.first);Word(stance.second);Word(a.CheckpointStance());Word(a.FootForward());
        Frame(a.action_controller);Frame(a.motion_controller);Word(std::uint32_t(a.action.tick));Word(std::uint32_t(a.action.tick>>32));Word(bool(a.action.is_tricking));if (a.action.is_tricking) Word(*a.action.is_tricking);
        Map(a.action.action_intents,names);Map(a.action.motion_intents,names);Map(a.animation.motion_intents,names);Map(a.animation.filtered_intents,names);
        String(a.action.Diagnostics("\n"));String(a.motion.Diagnostics("\n"));
        for (const auto b:{a.motion.flags.anticipating,a.motion.flags.landing,a.motion.flags.manualing,a.motion.flags.doing_trick,a.motion.flags.tricks_allowed,a.motion.riding.dark,a.motion.is_power_sliding,a.motion.applying_body_tilt,a.motion.keep_shove_channels}) Word(b);
        for (const auto f:{a.motion.riding.time_since_teleport,a.motion.riding.time_since_kickturn,a.motion.riding.manual_out_timer,a.motion.riding.last_good_landing_velocity,a.motion.animation_phase}) Float(f);
        for (const auto h:a.motion.busy_hands) Word(h);for (const auto w:a.motion.slide_latch.words) Word(w);
        const auto& anim=a.animation;Word(bool(anim.tree.skater_animation_flags));if (anim.tree.skater_animation_flags) Word(*anim.tree.skater_animation_flags);
        Word(anim.natural_stance);Word(anim.relative_stance);Word(anim.requested_stance);Word(anim.reset_action_intents);Word(bool(anim.grab_type));if (anim.grab_type) Word(std::uint32_t(*anim.grab_type));
        Word(anim.tree.posture.Profile());Word(anim.tree.posture.IsPending());Word(bool(anim.tree.current_name));if (anim.tree.current_name) String(*anim.tree.current_name);
        float value=0;std::string error;const bool time=a.animation.CurrentTime(value,error);Status(time,error);if (time) Float(value);const bool length=a.animation.CurrentLength(value,error);Status(length,error);if (length) Float(value);Word(a.animation.InTransition());
        Word(anim.tree.property.crossed_end);Float(anim.tree.property.overshoot);Float(anim.tree.property.remaining_before_wrap);
        for (const auto name:{"Overlay","overlay","SkitchAntic","Missing"}) {Word(anim.channels.Has(name));Float(anim.channels.Elapsed(name));Float(anim.channels.Remaining(name));Word(anim.channels.InTransition(name));}
        Word(std::uint32_t(anim.tree.tree_attributes.size()));for (const auto& v:anim.tree.tree_attributes) Attribute(v);
        Word(std::uint32_t(a.action.animation_attributes.size()));for (const auto& v:a.action.animation_attributes) Attribute(v);
        Word(std::uint32_t(anim.motion_attributes.size()));for (const auto& v:anim.motion_attributes) {for (const auto w:v.name) Word(w);Float(v.value);}
        Word(std::uint32_t(a.attributes.Size()));for (std::size_t i=0;i<a.attributes.Size();++i) Attribute(a.attributes[i]);
        Word(std::uint32_t(a.pose.size()));for (const auto& p:a.pose) for (const auto* v:{&p.scale,&p.rotation,&p.translation}) for (const auto f:*v) Float(f);
        const auto& p=a.packet;Word(p.bone_count);Matrices(p.hierarchy);Matrices(p.local);Float(p.timestep);for (const auto f:p.foot_surface_ids) Word(f);Word(p.flags);
        for (const auto b:{p.board_flipped,p.mirrored,p.riding_switch,p.riding_fakie,p.weight_forwards,p.regular_stance}) Word(b);Word(std::uint32_t(p.air_dismount_revert_frames));Reset(reset);
    }
};
bool LoadGraph(const std::filesystem::path& path,AnimationLoadedGraph& graph,std::string& error) {return graph.source.Load(File(path),error)&&graph.binding.Bind(graph.source,error)&&graph.runtime.FromBinding(graph.binding,error);}
}
int main(int argc,char** argv)
{
    if (argc!=6) return 2;const std::filesystem::path samples(argv[1]),metadata(argv[2]),fixtures(argv[3]),assets(argv[5]);const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);Output out;std::string error;
    auto source=std::make_shared<AnimationSource>();AnimationMetadata other;AnimationPoseFrames frames;SettingsDatabase settings;
    if (!source->metadata.Load(File(metadata/"bank-0.skate"),error)||!other.Load(File(metadata/"bank-1.skate"),error)||!source->metadata.Merge(other,error)||!frames.rig.Load(File(samples/"rig.skate"),error)||!settings.Load(File(argv[4]),error)) {std::cerr<<error;return 2;}
    const auto clip_count=input.Word();for (std::uint32_t i=0;i<clip_count;++i) {const auto file=input.String();auto clip=std::make_shared<AnimationClipSamples>();if (!clip->Load(File(samples/"clips"/(file+".skate")),error)||!frames.RegisterClip(clip,error)) {std::cerr<<error;return 2;}}
    source->evaluator=std::make_shared<AnimationPoseEvaluator>(std::move(frames));if (!source->evaluator->LoadAuthoredClips(assets,error)) {std::cerr<<error;return 2;}
    const auto query_count=input.Word();std::vector<std::string> names;for (std::uint32_t i=0;i<query_count;++i) names.push_back(input.String());
    const auto fixtures_count=input.Word();out.Word(fixtures_count);
    for (std::uint32_t f=0;f<fixtures_count;++f)
    {
        const auto id=input.Word();const auto pro=input.String();AnimationStockGraphs graphs;
        if (!LoadGraph(fixtures/("actor-"+std::to_string(id)+".action.native"),graphs.action,error)||!LoadGraph(fixtures/("actor-"+std::to_string(id)+".motion.native"),graphs.motion,error)) {std::cerr<<error;return 2;}
        std::unique_ptr<SkaterAnimation> actor;if (!SkaterAnimation::FromSource(settings,graphs,pro,source,actor,error)) {std::cerr<<error;return 2;}
        AnimationAdditionalResetFields reset;reset.compression=.137f;reset.foot_ik_influence={.317f,.731f};reset.next_step_position_valid=true;reset.actor_flag_1904_bit23=true;reset.actor_flag_1908_bit2=true;reset.external_impulse_active=true;reset.external_physics_input_active=true;reset.externally_controlled=true;reset.prevent_manual_respawn=true;reset.ignore_respawn_reset_button=255;reset.force_braking=true;reset.truck_tightness=.113f;reset.wheel_hardness=.719f;for (auto& v:reset.auxiliary_vectors) v={.137f,.317f,.731f,.113f};reset.requested_physics_mode=0xdeadbeef;
        const auto steps=input.Word();out.Word(steps);out.Snapshot(*actor,reset,names);
        for (std::uint32_t j=0;j<steps;++j)
        {
            bool ok=true;switch (input.Word())
            {
            case 0:{const auto dt=input.Float();const auto map=input.Map();const auto physical=input.Physical();ok=actor->Advance(graphs,dt,map,physical,reset,error);out.Status(ok,error);break;}
            case 1:{const auto natural=input.Word(),style=input.Word();actor->SetCustomisation(natural,style);out.Status(true,{});break;}
            case 2:actor->RequestCheckpointStance(input.Word());out.Status(true,{});break;
            case 3:{const auto name=input.String(),animation=input.String();const auto settings=input.Channel();bool created=false;ok=actor->animation.NewChannel(name,animation,settings,created,error);out.Status(ok,error);if (ok) out.Word(created);break;}
            case 4:{const auto name=input.String();const auto time=input.Float();const bool from_last=input.Boolean();actor->animation.channels.EndWith(name,time,from_last);out.Status(true,{});break;}
            case 5:{std::vector<Mat4> hierarchy;ok=actor->EvaluateInitialPose(hierarchy,error);out.Status(ok,error);if (ok) out.Matrices(hierarchy);break;}
            case 6:actor->animation.tree.posture.SetProfile(input.Word());out.Status(true,{});break;
            case 7:actor->action_controller.EndAllBehaviors(actor->action);actor->motion_controller.EndAllBehaviors(actor->motion);out.Status(true,{});break;
            default:return 2;
            }
            out.Snapshot(*actor,reset,names);
        }
    }
    if (!input.ok||input.Remaining()!=0) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return std::cout?0:2;
}
