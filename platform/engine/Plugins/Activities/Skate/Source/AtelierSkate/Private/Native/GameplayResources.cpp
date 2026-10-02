// SPDX-License-Identifier: Apache-2.0
#include "GameplayRuntime.h"
#include <algorithm>
#include <fstream>
#include <iterator>
namespace atelier::skate
{
namespace
{
bool ReadFile(const std::filesystem::path& path,std::vector<std::uint8_t>& bytes,std::string& error)
{
    std::ifstream stream(path,std::ios::binary);
    if(!stream){error="Cannot read native skating resource "+path.filename().string();return false;}
    bytes.assign(std::istreambuf_iterator<char>(stream),{});
    if(stream.bad()){error="Failed reading native skating resource "+path.filename().string();return false;}
    return true;
}
class FileResourceSource final : public GameplayResourceSource
{
public:
    explicit FileResourceSource(std::filesystem::path root):root_(std::move(root)) {}
    bool Read(std::string_view name,std::vector<std::uint8_t>& bytes,std::string& error) const override
    {return ReadFile(root_/std::string(name),bytes,error);}
    bool EnumerateClips(std::vector<std::string>& names,std::string& error) const override
    {
        std::error_code ec;std::vector<std::filesystem::path> clips;
        std::filesystem::recursive_directory_iterator end,entry(root_/"animation/clips",ec);
        while(!ec && entry!=end)
        {
            if(entry->is_regular_file(ec) && entry->path().extension()==".skate")clips.push_back(entry->path());
            entry.increment(ec);
        }
        if(ec || clips.empty()){error="Cannot enumerate native skating clips";return false;}
        std::sort(clips.begin(),clips.end());
        names.clear();names.reserve(clips.size());
        for(const auto& path:clips)names.push_back(path.lexically_relative(root_).generic_string());
        return true;
    }
    bool Exists(std::string_view name,bool& exists,std::string& error) const override
    {
        std::error_code ec;exists=std::filesystem::exists(root_/std::string(name),ec);
        if(ec)
        {
            error=name=="custom/climbing.skate"?"Cannot inspect native skating climbing clips":
                "Cannot inspect native skating custom animation";
            return false;
        }
        return true;
    }
private:
    const std::filesystem::path root_;
};
bool LoadedGraph(const GameplayResourceSource& source,std::string_view name,AnimationLoadedGraph& graph,std::string& error)
{
    std::vector<std::uint8_t> bytes;
    return source.Read(name,bytes,error) && graph.source.Load(bytes,error)
        && graph.binding.Bind(graph.source,error) && graph.runtime.FromBinding(graph.binding,error);
}
}
bool LoadGameplayResources(const std::filesystem::path& root,
    std::shared_ptr<const GameplayResources>& output,std::string& error)
{
    const FileResourceSource source(root);
    return LoadGameplayResources(source,output,error);
}
bool LoadGameplayResources(const GameplayResourceSource& source,
    std::shared_ptr<const GameplayResources>& output,std::string& error)
{
    if(!source.VerifyIntegrity(error))return false;
    auto resources=std::make_shared<GameplayResources>();
    auto animation=std::make_shared<AnimationSource>();
    std::vector<std::uint8_t> bytes;
    if(!source.Read("settings.skate",bytes,error) || !resources->settings.Load(bytes,error))return false;
    if(!source.Read("metadata/bank-0.skate",bytes,error) || !animation->metadata.Load(bytes,error))return false;
    if(!source.ExpectedSourceIdentity().empty() && source.ExpectedSourceIdentity()!=animation->metadata.source_sha256)
    {error="Native skating source identity differs from resource snapshot";return false;}
    AnimationMetadata offboard;
    if(!source.Read("metadata/bank-1.skate",bytes,error) || !offboard.Load(bytes,error)
        || !animation->metadata.Merge(offboard,error))return false;
    PhysicsSkeletons skeletons;
    if(!source.Read("physics-skeletons.skate",bytes,error)
        || !skeletons.Load(bytes,animation->metadata.source_sha256,error))return false;
    const auto* physical=skeletons.Find("PHYS_TPOSE");
    if(!physical){error="Native skating resources require PHYS_TPOSE";return false;}
    resources->physical_skeleton=*physical;
    AnimationPoseFrames frames;
    if(!source.Read("animation/rig.skate",bytes,error) || !frames.rig.Load(bytes,error))return false;
    std::vector<std::string> clips;
    if(!source.EnumerateClips(clips,error))return false;
    for(const auto& path:clips)
    {
        auto clip=std::make_shared<AnimationClipSamples>();
        if(!source.Read(path,bytes,error) || !clip->Load(bytes,error) || !frames.RegisterClip(clip,error))return false;
    }
    animation->evaluator=std::make_shared<AnimationPoseEvaluator>(std::move(frames));
    const std::string_view authored="custom/crouch-treflip.json";
    bool has_authored=false;
    if(!source.Exists(authored,has_authored,error))return false;
    if(has_authored)
    {
        if(!source.Read(authored,bytes,error))return false;
        const std::string text(bytes.begin(),bytes.end());
        if(!animation->evaluator->SetAuthoredClips(text,error))return false;
    }
    resources->animation=std::move(animation);
    if(!LoadedGraph(source,"action.graph",resources->graphs.action,error)
        || !LoadedGraph(source,"motion.graph",resources->graphs.motion,error))return false;
    if(!source.Read("camera.graph",bytes,error) || !resources->camera_graph.Load(bytes,error)
        || !source.Read("camera.skate",resources->camera_data,error))return false;
    if(!source.Read("gestures.skate",bytes,error) || !LoadGestureData(bytes,resources->gestures,error))return false;
    const std::string_view climb="custom/climbing.skate";
    bool has_climb=false;
    if(!source.Exists(climb,has_climb,error))return false;
    if(has_climb)
    {
        ClimbingClipFile file;
        if(!source.Read(climb,bytes,error) || !ReadClimbingClipFile(bytes,file,error))return false;
        resources->climbing=std::move(file);
    }
    output=std::move(resources);error.clear();return true;
}
}
