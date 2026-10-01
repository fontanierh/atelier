// SPDX-License-Identifier: Apache-2.0
#include "AnimationTrees.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes} {}
    AttributeName Name() {AttributeName n;for (auto& v:n) v=Word();return n;}
    AnimationAttribute Attribute() {AnimationAttribute a;a.name=Name();a.kind=std::uint8_t(Word());a.status=std::uint8_t(Word());a.sequence_id=std::int32_t(Word());a.begin_time=Float();a.end_time=Float();for (auto& p:a.payload) if (Word()!=0) p=Word();return a;}
    std::vector<std::uint32_t> Words() {const auto n=Word();std::vector<std::uint32_t> v;for (std::uint32_t i=0;i<n;++i) v.push_back(Word());return v;}
    std::vector<float> Floats() {const auto n=Word();std::vector<float> v;for (std::uint32_t i=0;i<n;++i) v.push_back(Float());return v;}
    std::vector<std::vector<float>> Matrix() {const auto n=Word();std::vector<std::vector<float>> v;for (std::uint32_t i=0;i<n;++i) v.push_back(Floats());return v;}
    std::vector<SettableAttribute> Settable() {const auto n=Word();std::vector<SettableAttribute> v;for (std::uint32_t i=0;i<n;++i) {SettableAttribute a;a.name=Name();a.value=Float();a.normalized=Word()!=0;a.sequence_id=std::int32_t(Word());v.push_back(a);}return v;}
    TransitionSettings Transition() {TransitionSettings s;s.kind=Word();s.seconds=Float();s.under=Word();s.matching=Word();s.use_channels_from_weights=Word()!=0;return s;}
    std::shared_ptr<const AttributeMirror> Mirror() {auto mirror=std::make_shared<AttributeMirror>();const auto n=Word();for (std::uint32_t i=0;i<n;++i) {const auto a=Name(),b=Name();mirror->names.emplace_back(a,b);}return mirror;}
    std::vector<std::pair<AttributeName,AttributeName>> Construction() {const auto n=Word();std::vector<std::pair<AttributeName,AttributeName>> v;for (std::uint32_t i=0;i<n;++i) {const auto a=Name(),b=Name();v.emplace_back(a,b);}return v;}
    bool Children(std::vector<AnimationTree>& output,std::string& error) {const auto n=Word();for (std::uint32_t i=0;i<n;++i) {AnimationTree t;if (!Tree(t,error)) return false;output.push_back(std::move(t));}return true;}
    bool Tree(AnimationTree& output,std::string& error)
    {
        switch (Word())
        {
            case 0:{const auto name=String();const auto frames=Float(),fps=Float(),base=Float();const auto flags=Word(),n=Word();std::vector<PlaybackClipAttribute> attributes;
                for (std::uint32_t i=0;i<n;++i) {PlaybackClipAttribute a;a.name=Name();a.kind=std::uint8_t(Word());a.begin=Float();a.end=Float();a.payload=Words();attributes.push_back(std::move(a));}
                PlaybackClip clip(frames,fps,base,flags,std::move(attributes));clip.clock.time=Float();clip.clock.previous_time=Float();clip.clock.loops_since_evaluation=Word();output=AnimationTree::Clip(name,std::move(clip));error.clear();return true;}
            case 1:{const auto parameter=Name();std::vector<AnimationTree> children;if (!Children(children,error)) return false;return AnimationTree::PhaseBlend(parameter,std::move(children),output,error);}
            case 2:{const auto n=Word();std::vector<AttributeName> parameters;for (std::uint32_t i=0;i<n;++i) parameters.push_back(Name());std::vector<AnimationTree> children;if (!Children(children,error)) return false;const auto count=Word();std::vector<AnimationBlendSimplex> simplexes;
                for (std::uint32_t i=0;i<count;++i) {AnimationBlendSimplex s;const auto words=Words();s.children.assign(words.begin(),words.end());s.vertices=Matrix();s.normals=Matrix();s.scales=Floats();simplexes.push_back(std::move(s));}return AnimationTree::BlendSpace(std::move(parameters),std::move(children),std::move(simplexes),output,error);}
            case 3:{const auto n=Word();std::vector<SelectionParameter> parameters;for (std::uint32_t i=0;i<n;++i) {SelectionParameter p;p.name=Name();p.mode=Word();p.weight=Float();p.minimum=Float();p.maximum=Float();parameters.push_back(p);}const auto count=Word();std::vector<AnimationSelectionCandidate> candidates;
                for (std::uint32_t i=0;i<count;++i) {AnimationSelectionCandidate c;c.name=String();c.values=Floats();if (!Tree(c.tree,error)) return false;candidates.push_back(std::move(c));}return AnimationTree::SelectionSpace(std::move(parameters),std::move(candidates),output,error);}
            case 4:{AnimationTree from,to;if (!Tree(from,error)||!Tree(to,error)) return false;output=AnimationTree::Transition(std::move(from),std::move(to),Transition());error.clear();return true;}
            case 5:{AnimationTree motion;if (!Tree(motion,error)) return false;const auto posture=PosturePoseFromProfile(Word());const bool board=Word()!=0;const auto modes=Words();auto mirror=Mirror();output=AnimationTree::BindPose(std::move(motion),posture,board,modes,std::move(mirror));error.clear();return true;}
            default:return false;
        }
    }
};
static void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(char(v>>(8*i)));}
static void Float(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
static void String(std::string_view v) {Word(std::uint32_t(v.size()));std::cout.write(v.data(),v.size());}
static void Attribute(const AnimationAttribute& a) {for (auto v:a.name) Word(v);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto v:a.payload) {Word(v.has_value());if (v) Word(*v);}}
static void Attributes(const std::vector<AnimationAttribute>& a) {Word(std::uint32_t(a.size()));for (const auto& v:a) Attribute(v);}
static void Status(bool ok,const std::string& error) {Word(ok);if (!ok) String(error);}
static void Boolean(bool ok,bool value,const std::string& error) {Status(ok,error);if (ok) Word(value);}
static void Commands(const std::vector<PoseCommand>& commands)
{
    Word(std::uint32_t(commands.size()));for (const auto& c:commands)
    {
        Word(std::uint32_t(c.kind));switch (c.kind)
        {
            case PoseCommand::Kind::Clip:String(c.name);Float(c.previous_time);Float(c.time);Word(c.loops);break;
            case PoseCommand::Kind::Blend:Float(c.weight);break;
            case PoseCommand::Kind::WeightedBlend:Word(std::uint32_t(c.weights.size()));for (auto v:c.weights) Float(v);break;
            case PoseCommand::Kind::ChannelBlend:Float(c.weight);Word(c.use_channels_from_weights);break;
            case PoseCommand::Kind::Pose:String(c.name);break;case PoseCommand::Kind::Add:Word(c.motion_is_a);break;case PoseCommand::Kind::Mirror:Word(c.trajectory_mode);break;
        }
    }
}
static void Snapshot(const AnimationTree& tree)
{
    Word(std::uint32_t(tree.Kind()));Float(tree.Length());Float(tree.Time());Word(tree.HasTransition());const auto selected=tree.SelectedCandidate();Word(selected.has_value());if (selected) Word(std::uint32_t(*selected));
    const auto weights=tree.ActiveWeights();Word(std::uint32_t(weights.size()));for (const auto& w:weights) {Word(std::uint32_t(w.first));Float(w.second);}
    if (tree.Kind()==PlaybackTreeKind::Transition) {Word(tree.TransitionComplete());Float(tree.TransitionWeight());}
    if (const auto c=tree.ClipClockState()) {for (auto v:{c->frames,c->fps,c->base_speed,c->speed,c->length,c->time,c->previous_time}) Float(v);Word(c->loops_since_evaluation);Word(c->looping);Word(c->phase_controlled);}
    const auto children=tree.Children();Word(std::uint32_t(children.size()));for (const auto child:children) Snapshot(*child);
}
static bool Operations(Input& input,AnimationTree& tree,std::string& error)
{
    const auto n=input.Word();std::optional<AnimationTree> backup;
    for (std::uint32_t i=0;i<n;++i)
    {
        switch (input.Word())
        {
            case 0:tree.SetTime(input.Float());Status(true,error);break;case 1:tree.SetSpeed(input.Float());Status(true,error);break;
            case 2:{const auto dt=input.Float(),phase=input.Float();AdvanceResult p{input.Word()!=0,input.Float(),input.Float()};Status(tree.Advance(dt,phase,p,error),error);Word(p.crossed_end);Float(p.overshoot);Float(p.remaining_before_wrap);break;}
            case 3:{const auto attrs=input.Settable();bool changed=false;const bool ok=tree.SetAttributes(attrs,changed,error);Boolean(ok,changed,error);break;}
            case 4:{const auto attrs=input.Settable();Status(tree.PrepareSelectionSpaces(attrs,error),error);break;}
            case 5:{const AnimationEvaluation p{input.Float(),input.Word()!=0};const bool enabled=input.Word()!=0;std::vector<PoseCommand> c(1);c[0].kind=PoseCommand::Kind::Pose;c[0].name="SENTINEL";bool produced=false;const bool ok=tree.Evaluate(p,enabled,c,produced,error);Boolean(ok,produced,error);Commands(c);break;}
            case 6:{std::vector<AnimationAttribute> a;const bool ok=tree.Attributes(input.Word(),a,error);Status(ok,error);if (ok) Attributes(a);break;}
            case 7:{const auto name=input.Name();const auto mask=input.Word();auto a=input.Attribute();bool found=false;const bool ok=tree.QueryAttribute(name,mask,a,found,error);Boolean(ok,found,error);Attribute(a);break;}
            case 8:tree.PruneCompletedTransitions();Status(true,error);break;case 9:backup=tree;Status(true,error);break;case 10:tree=*backup;Status(true,error);break;
            case 11:{AnimationTree to;if (!input.Tree(to,error)) return false;const auto settings=input.Transition();tree=AnimationTree::Transition(std::move(tree),std::move(to),settings);Status(true,error);break;}
            default:return false;
        }
        Snapshot(tree);
    }
    return true;
}
static std::vector<std::uint8_t> Read(const std::string& path) {std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};}
static bool Load(AnimationMetadata& metadata,const std::vector<std::string>& paths,std::string& error)
{if (!metadata.Load(Read(paths[0]),error)) return false;for (std::size_t i=1;i<paths.size();++i) {AnimationMetadata other;if (!other.Load(Read(paths[i]),error)||!metadata.Merge(other,error)) return false;}return true;}
static void OwnerSnapshot(const AnimationTreeOwner& owner)
{Word(owner.current.has_value());if (owner.current) Snapshot(*owner.current);Word(owner.current_name.has_value());if (owner.current_name) String(*owner.current_name);Word(owner.posture.Profile());Word(owner.posture.IsPending());Word(owner.skater_animation_flags.has_value());if (owner.skater_animation_flags) Word(*owner.skater_animation_flags);Word(owner.property.crossed_end);Float(owner.property.overshoot);Float(owner.property.remaining_before_wrap);Attributes(owner.tree_attributes);}
int main(int argc,char** argv)
{
    if (argc!=4) return 1;AnimationMetadata stock,fixture;std::string error;if (!Load(stock,{argv[1],argv[2]},error)||!Load(fixture,{argv[3]},error)) return 2;
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);const auto n=input.Word();
    for (std::uint32_t i=0;i<n;++i)
    {
        const auto kind=input.Word();
        if (kind<=2)
        {
            AnimationTree tree;bool ok;if (kind==1) {const auto name=input.String();const auto construction=input.Construction();ok=BuildAnimationTree(stock,name,construction,tree,error);}else ok=input.Tree(tree,error);
            Status(ok,error);if (ok) {Snapshot(tree);if (!Operations(input,tree,error)) return 2;}else if (input.Word()!=0) return 2;
        }
        else if (kind==3)
        {
            AnimationTreeOwner owner(fixture);owner.construction_values=input.Construction();owner.attribute_mirror=input.Mirror();if (input.Word()!=0) owner.skater_animation_flags=input.Word();owner.posture.SetProfile(input.Word());owner.posture.SetRequested(input.Word()!=0);owner.posture_bank_valid=input.Word()!=0;
            const auto steps=input.Word();for (std::uint32_t j=0;j<steps;++j)
            {
                switch (input.Word())
                {
                    case 0:{PlaybackRequest r;r.animation=input.String();r.speed=input.Float();r.start_time=input.Float();r.transition=input.Transition();bool played=false;const bool ok=owner.Play(r,played,error);Boolean(ok,played,error);break;}
                    case 1:{const auto dt=input.Float(),phase=input.Float();Status(owner.Advance(dt,phase,error),error);break;}
                    case 2:{for (const auto& a:input.Settable()) owner.settable.SetAttribute(a);Status(owner.ApplyParameters(error),error);break;}
                    case 3:{const AnimationEvaluation p{input.Float(),input.Word()!=0};std::vector<PoseCommand> c;const bool ok=owner.EvaluatePose(p,c,error);Status(ok,error);if (ok) Commands(c);break;}
                    case 4:Status(owner.RefreshTreeAttributes(error),error);break;
                    case 5:owner.posture.SetProfile(input.Word());owner.posture.SetRequested(input.Word()!=0);Status(true,error);break;
                    case 6:if (input.Word()!=0) owner.skater_animation_flags=input.Word();else owner.skater_animation_flags.reset();Status(true,error);break;
                    default:return 2;
                }
                OwnerSnapshot(owner);
            }
        }
        else
        {
            PendingPosture pending;std::uint32_t motion=0;const auto steps=input.Word();for (std::uint32_t j=0;j<steps;++j)
            {
                switch (input.Word())
                {
                    case 0:pending.SetProfile(input.Word());Status(true,error);break;case 1:pending.SetRequested(input.Word()!=0);Status(true,error);break;
                    case 2:{const bool success=input.Word()!=0;const bool ok=pending.Apply(motion,[&](std::uint32_t& m,PosturePose p,std::string& failure){if (!success) {failure="Posture construction failed";return false;}m+=std::uint32_t(p);return true;},error);Status(ok,error);break;}
                    default:return 2;
                }
                Word(motion);Word(pending.Profile());Word(pending.IsPending());const auto pose=pending.SelectedPose();Word(pose?std::uint32_t(*pose):0);
            }
        }
    }
    if (!input.ok||input.Remaining()!=0) return 2;return std::cout?0:2;
}
