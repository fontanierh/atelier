#include "GameplayRuntime.h"
#include <algorithm>
#include <fstream>
#include <iterator>
namespace atelier::skate
{
namespace
{
bool Read(const std::filesystem::path& path,std::vector<std::uint8_t>& bytes,std::string& error)
{
    std::ifstream stream(path,std::ios::binary);
    if(!stream){error="Cannot read native skating resource "+path.filename().string();return false;}
    bytes.assign(std::istreambuf_iterator<char>(stream),{});
    if(stream.bad()){error="Failed reading native skating resource "+path.filename().string();return false;}
    return true;
}
// The runtime files from a folder or from payloads: Read(name, bytes, error).
struct FolderFiles
{
    const std::filesystem::path& root;
    bool operator()(const char* name,std::vector<std::uint8_t>& bytes,std::string& error) const
    {return Read(root/name,bytes,error);}
};
struct PayloadFiles
{
    const RuntimePayloads& payloads;
    bool operator()(const char* name,std::vector<std::uint8_t>& bytes,std::string& error) const
    {
        const auto found=payloads.find(name);
        if(found==payloads.end())
        {error="Cannot read native skating resource "+std::filesystem::path(name).filename().string();return false;}
        bytes=found->second;return true;
    }
};
template<class Files> bool LoadedGraph(const Files& files,const char* name,AnimationLoadedGraph& graph,std::string& error)
{
    std::vector<std::uint8_t> bytes;
    return files(name,bytes,error) && graph.source.Load(bytes,error)
        && graph.binding.Bind(graph.source,error) && graph.runtime.FromBinding(graph.binding,error);
}
template<class Files> bool LoadPhysicalSkeleton(const Files& files,const AnimationSource& animation,
    GameplayResources& resources,std::string& error)
{
    std::vector<std::uint8_t> bytes;PhysicsSkeletons skeletons;
    if(!files("physics-skeletons.skate",bytes,error)
        || !skeletons.Load(bytes,animation.metadata.source_sha256,error))return false;
    const auto* physical=skeletons.Find("PHYS_TPOSE");
    if(!physical){error="Native skating resources require PHYS_TPOSE";return false;}
    resources.physical_skeleton=*physical;return true;
}
template<class Files> bool LoadGraphs(const Files& files,GameplayResources& resources,std::string& error)
{
    std::vector<std::uint8_t> bytes;
    if(!LoadedGraph(files,"action.graph",resources.graphs.action,error)
        || !LoadedGraph(files,"motion.graph",resources.graphs.motion,error))return false;
    if(!files("camera.graph",bytes,error) || !resources.camera_graph.Load(bytes,error)
        || !files("camera.skate",resources.camera_data,error))return false;
    return files("gestures.skate",bytes,error) && LoadGestureData(bytes,resources.gestures,error);
}
void UseMotion(const AnimationSource& motion,AnimationSource& animation)
{
    animation.metadata=motion.metadata;
    animation.evaluator=std::make_shared<AnimationPoseEvaluator>(motion.evaluator->frames);
}
}
bool LoadGameplayResources(const std::filesystem::path& root,
    std::shared_ptr<const GameplayResources>& output,std::string& error,
    std::shared_ptr<const AnimationSource> motion)
{
    const FolderFiles files{root};
    auto resources=std::make_shared<GameplayResources>();
    auto animation=std::make_shared<AnimationSource>();
    std::vector<std::uint8_t> bytes;
    std::error_code ec;
    if(!files("settings.skate",bytes,error) || !resources->settings.Load(bytes,error))return false;
    if(motion)
    {
        if(!motion->evaluator){error="Typed motion requires a pose evaluator";return false;}
        UseMotion(*motion,*animation);
    }
    else
    {
        if(!files("metadata/bank-0.skate",bytes,error) || !animation->metadata.Load(bytes,error))return false;
        AnimationMetadata offboard;
        if(!files("metadata/bank-1.skate",bytes,error) || !offboard.Load(bytes,error)
            || !animation->metadata.Merge(offboard,error))return false;
    }
    if(!LoadPhysicalSkeleton(files,*animation,*resources,error))return false;
    if(!motion)
    {
        AnimationPoseFrames frames;
        if(!files("animation/rig.skate",bytes,error) || !frames.rig.Load(bytes,error))return false;
        std::vector<std::filesystem::path> clips;
        std::filesystem::recursive_directory_iterator end,entry(root/"animation/clips",ec);
        while(!ec && entry!=end)
        {
            if(entry->is_regular_file(ec) && entry->path().extension()==".skate")clips.push_back(entry->path());
            entry.increment(ec);
        }
        if(ec || clips.empty()){error="Cannot enumerate native skating clips";return false;}
        std::sort(clips.begin(),clips.end());
        for(const auto& path:clips)
        {
            auto clip=std::make_shared<AnimationClipSamples>();
            if(!Read(path,bytes,error) || !clip->Load(bytes,error) || !frames.RegisterClip(clip,error))return false;
        }
        animation->evaluator=std::make_shared<AnimationPoseEvaluator>(std::move(frames));
    }
    const auto authored=root/"custom/crouch-treflip.json";
    const bool has_authored=std::filesystem::exists(authored,ec);
    if(ec){error="Cannot inspect native skating custom animation";return false;}
    if(has_authored)
    {
        if(!Read(authored,bytes,error))return false;
        const std::string text(bytes.begin(),bytes.end());
        if(!animation->evaluator->SetAuthoredClips(text,error))return false;
    }
    resources->animation=std::move(animation);
    if(!LoadGraphs(files,*resources,error))return false;
    const auto climb=root/"custom/climbing.skate";
    const bool has_climb=std::filesystem::exists(climb,ec);
    if(ec){error="Cannot inspect native skating climbing clips";return false;}
    if(has_climb)
    {
        ClimbingClipFile file;
        if(!Read(climb,bytes,error) || !ReadClimbingClipFile(bytes,file,error))return false;
        resources->climbing=std::move(file);
    }
    output=std::move(resources);error.clear();return true;
}
bool LoadGameplayResources(const RuntimePayloads& payloads,const AnimationSource& motion,
    std::shared_ptr<const GameplayResources>& output,std::string& error)
{
    if(!motion.evaluator){error="Typed motion requires a pose evaluator";return false;}
    const PayloadFiles files{payloads};
    auto resources=std::make_shared<GameplayResources>();
    auto animation=std::make_shared<AnimationSource>();
    std::vector<std::uint8_t> bytes;
    if(!files("settings.skate",bytes,error) || !resources->settings.Load(bytes,error))return false;
    UseMotion(motion,*animation);
    if(!LoadPhysicalSkeleton(files,*animation,*resources,error))return false;
    resources->animation=std::move(animation);
    if(!LoadGraphs(files,*resources,error))return false;
    output=std::move(resources);error.clear();return true;
}
}
