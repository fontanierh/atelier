#include "AnimationPose.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iterator>
#include <mutex>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float f;std::memcpy(&f,&bits,4);return f;}
std::string Upper(std::string_view input) {std::string s(input);for (auto& c:s) if (c>='a'&&c<='z') c=char(c-'a'+'A');return s;}
bool Fail(std::string& error,std::string message) {error=std::move(message);return false;}
void Reflect(Sqt& pose) {pose.rotation[0]*=-1;pose.rotation[1]*=-1;pose.translation[2]*=-1;}
bool SampleReplacementBone(const AnimationClipReplacement& clip,float time,std::size_t bone,Sqt& output,std::string& error)
{
    FrameSelection s;if (!SelectAnimationFrames(time,Float(clip.stock->fps_bits),clip.frames.size(),true,0,s,error)) return false;
    auto a=DecodeSampleWords(clip.frames[s.first][bone]);output=s.first==s.second?a:BlendPoseSample(a,DecodeSampleWords(clip.frames[s.second][bone]),s.coefficient);
    output.translation[3]=Float(clip.stock->channel_weights[bone]);return true;
}
}
Sqt AnimationTrajectoryDelta(Sqt current,Sqt previous,std::optional<AnimationLoopTransform> loop)
{
    const auto l=loop.value_or(AnimationLoopTransform{});const Quat inverse{-previous.rotation[0],-previous.rotation[1],-previous.rotation[2],previous.rotation[3]};
    const auto d=QuaternionRotate(current.rotation,l.translation);std::array<float,3> displacement{};
    for (std::size_t i=0;i<3;++i) displacement[i]=(d[i]+current.translation[i])-previous.translation[i];
    const auto t=QuaternionRotate(inverse,displacement);return {current.scale,QuaternionMultiply(QuaternionMultiply(l.rotation,current.rotation),inverse),{t[0],t[1],t[2],current.translation[3]}};
}
Sqt AddAnimationPose(Sqt a,Sqt b,bool motion_is_a)
{
    const auto r=QuaternionRotate(b.rotation,{a.translation[0],a.translation[1],a.translation[2]});Sqt out;
    for (std::size_t i=0;i<4;++i) out.scale[i]=b.scale[i]*a.scale[i];out.rotation=QuaternionMultiply(b.rotation,a.rotation);
    out.translation={r[0]+b.translation[0],r[1]+b.translation[1],r[2]+b.translation[2],motion_is_a?a.translation[3]:b.translation[3]};return out;
}
bool MirrorAnimationPose(std::vector<Sqt>& pose,const std::vector<std::int32_t>& parents,const std::vector<std::int32_t>& partners,std::uint32_t mode,std::string& error)
{
    if (pose.size()!=parents.size()||pose.size()!=partners.size()) return Fail(error,"Mirror pose and hierarchy dimensions differ");
    for (std::size_t i=0;i<partners.size();++i)
    {
        const auto p=partners[i];if (p< -1||p>=std::int32_t(pose.size())) return Fail(error,"Invalid mirror partner for bone"+std::to_string(i));
        if (p<std::int32_t(i)) continue;
        if (mode==1&&(i==0||parents[i]==0)) {if (i!=0) pose[i].rotation=QuaternionMultiply(pose[i].rotation,{0,1,0,0});pose[i].rotation[1]*=-1;pose[i].rotation[2]*=-1;pose[i].translation[0]*=-1;}
        else Reflect(pose[i]);
        if (p>std::int32_t(i)) {std::swap(pose[i],pose[std::size_t(p)]);Reflect(pose[i]);}
    }error.clear();return true;
}
bool AnimationPoseFrames::RegisterClip(std::shared_ptr<const AnimationClipSamples> clip,std::string& error)
{
    const auto previous=clips.find(clip->name);if (previous!=clips.end()&&previous->second->bank!=clip->bank) return Fail(error,"Ambiguous clip "+clip->name+" in multiple animation banks");
    clips[clip->name]=std::move(clip);error.clear();return true;
}
const AnimationClipSamples* AnimationPoseFrames::Clip(std::string_view name,std::string& error) const
{const auto i=clips.find(Upper(name));if (i==clips.end()) {error="Missing stock animation clip "+std::string(name);return nullptr;}error.clear();return i->second.get();}
const AnimationReferencePose* AnimationPoseFrames::NamedPose(std::string_view name,std::string& error) const
{const auto* p=rig.NamedPose(0,name);if (!p) {error="Missing reference pose "+std::string(name)+" in bank 0";return nullptr;}error.clear();return p;}
bool AnimationPoseEvaluator::SetAuthoredClips(std::string_view text,std::string& error)
{AuthoredAnimationDocument d;AnimationClipReplacements r;if (!ParseAuthoredAnimationDocument(text,d,error)||!BakeAuthoredAnimationClips(d,frames,r,error)) return false;authored_=std::move(r);error.clear();return true;}
bool AnimationPoseEvaluator::LoadAuthoredClips(const std::filesystem::path& root,std::string& error)
{
    const auto path=root/"private/custom/crouch-treflip.json";std::error_code ec;
    if (!std::filesystem::exists(path,ec)&&!ec) {authored_.clear();error.clear();return true;}
    std::ifstream file(path);if (!file) return Fail(error,path.string()+": Cannot read authored animation clips");
    const std::string text{std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()};if (!SetAuthoredClips(text,error)) {error=path.string()+": "+error;return false;}return true;
}
bool AnimationPoseEvaluator::InstallModClips(std::string_view owner,std::string_view text,std::string& error)
{
    AuthoredAnimationDocument d;AnimationClipReplacements clips;if (!ParseAuthoredAnimationDocument(text,d,error)||!BakeAuthoredAnimationClips(d,frames,clips,error)) return false;
    const std::unique_lock<std::shared_mutex> lock(mods_mutex_);for (const auto& entry:mod_clips_) if (entry.first!=owner) for (const auto& c:clips) if (entry.second.count(c.first)) return Fail(error,"Animation slots conflict with mod "+entry.first);
    mod_clips_[std::string(owner)]=std::move(clips);error.clear();return true;
}
void AnimationPoseEvaluator::RemoveModClips(std::string_view owner) {const std::unique_lock<std::shared_mutex> lock(mods_mutex_);mod_clips_.erase(std::string(owner));}
void AnimationPoseEvaluator::ClearModClips() {const std::unique_lock<std::shared_mutex> lock(mods_mutex_);mod_clips_.clear();}
bool AnimationPoseEvaluator::Evaluate(const std::vector<PoseCommand>& commands,std::vector<Sqt>& output,std::string& error) const
{
    const std::shared_lock<std::shared_mutex> lock(mods_mutex_);std::vector<std::vector<Sqt>> stack;
    for (const auto& c:commands) switch (c.kind)
    {
        case PoseCommand::Kind::Pose:
        {const auto* p=frames.NamedPose(c.name,error);if (!p) return false;std::vector<Sqt> s;for (const auto& words:p->samples) s.push_back(DecodeSampleWords(words));stack.push_back(std::move(s));break;}
        case PoseCommand::Kind::Add:
        {if (stack.empty()) return Fail(error,"Animation add has no reference subtree");auto other=std::move(stack.back());stack.pop_back();if (stack.empty()) return Fail(error,"Animation add has no motion subtree");auto& motion=stack.back();if (motion.size()!=other.size()) return Fail(error,"Animation add bone counts differ");for (std::size_t b=0;b<motion.size();++b) motion[b]=c.motion_is_a?AddAnimationPose(motion[b],other[b],true):AddAnimationPose(other[b],motion[b],false);break;}
        case PoseCommand::Kind::Mirror:
        {if (stack.empty()) return Fail(error,"Animation mirror has no subtree");std::vector<std::int32_t> parents,partners;for (const auto& b:frames.rig.bones) {parents.push_back(b.parent);partners.push_back(b.mirror);}if (!MirrorAnimationPose(stack.back(),parents,partners,c.trajectory_mode,error)) return false;break;}
        case PoseCommand::Kind::Clip:
        {
            const auto* stock=frames.Clip(c.name,error);if (!stock) return false;const AnimationClipReplacement* replacement=nullptr;
            for (const auto& entry:mod_clips_) {const auto i=entry.second.find(stock->name);if (i!=entry.second.end()) {replacement=&i->second;break;}}
            if (!replacement) {const auto i=authored_.find(stock->name);if (i!=authored_.end()) replacement=&i->second;}
            std::vector<Sqt> pose;Sqt previous;
            if (replacement) {for (std::size_t b=0;b<stock->bone_count;++b) {Sqt sample;if (!SampleReplacementBone(*replacement,c.time,b,sample,error)) return false;pose.push_back(sample);}}
            else if (!SampleAnimationClip(*stock,c.time,pose,error)) return false;
            if (frames.rig.has_trajectory)
            {
                if (replacement) {if (!SampleReplacementBone(*replacement,c.previous_time,0,previous,error)) return false;}else if (!SampleAnimationBone(*stock,c.previous_time,0,previous,error)) return false;
                std::optional<AnimationLoopTransform> loop;if (c.loops!=0) {AnimationLoopTransform l;for (std::size_t j=0;j<4;++j) l.rotation[j]=Float(stock->loop_rotation[j]);for (std::size_t j=0;j<3;++j) l.translation[j]=Float(stock->loop_translation[j]);loop=l;}
                pose[0]=AnimationTrajectoryDelta(pose[0],previous,loop);
            }stack.push_back(std::move(pose));break;
        }
        case PoseCommand::Kind::WeightedBlend:
        {if (stack.size()<c.weights.size()) return Fail(error,"Weighted blend pose stack underflow");const auto start=stack.size()-c.weights.size();std::vector<std::vector<Sqt>> inputs(stack.begin()+std::ptrdiff_t(start),stack.end());std::vector<Sqt> pose;if (!WeightedBlendPoses(inputs,c.weights,pose,error)) {error="Weighted blend: "+error;return false;}stack.resize(start);stack.push_back(std::move(pose));break;}
        case PoseCommand::Kind::Blend:case PoseCommand::Kind::ChannelBlend:
        {if (stack.empty()) return Fail(error,"Animation blend has no second subtree");auto second=std::move(stack.back());stack.pop_back();if (stack.empty()) return Fail(error,"Animation blend has no first subtree");auto& first=stack.back();if (first.size()!=second.size()) return Fail(error,"Animation subtree bone counts differ");for (std::size_t b=0;b<first.size();++b) first[b]=c.kind==PoseCommand::Kind::ChannelBlend?ChannelBlendPoseSample(first[b],second[b],c.weight,c.use_channels_from_weights):BlendPoseSample(first[b],second[b],c.weight);break;}
    }
    if (stack.size()!=1) return Fail(error,"Animation evaluation left"+std::to_string(stack.size())+" poses");output=std::move(stack.back());error.clear();return true;
}
bool AnimationPoseEvaluator::Hierarchy(const std::vector<Sqt>& pose,std::vector<Mat4>& output,std::string& error) const
{
    if (pose.size()!=frames.rig.bones.size()) return Fail(error,"Animation pose and hierarchy bone counts differ");
    if (pose.empty()) return Fail(error,"Invalid stock animation hierarchy: ShortInput");
    std::vector<Mat4> globals;for (const auto& p:pose) globals.push_back(SqtToMatrix(p));
    for (std::size_t b=0;b<pose.size();++b) {const auto parent=frames.rig.bones[b].parent;if (parent!=-1&&parent!=0&&(parent<0||std::size_t(parent)>=globals.size())) return Fail(error,"Invalid stock animation hierarchy: InvalidParent { bone: "+std::to_string(b)+", parent: "+std::to_string(parent)+" }");}
    for (std::size_t b=0;b<pose.size();++b) {const auto p=frames.rig.bones[b].parent;if (p!=-1&&p!=0) globals[b]=ConcatenateAffine(globals[b],globals[std::size_t(p)]);}
    output=std::move(globals);error.clear();return true;
}
}
