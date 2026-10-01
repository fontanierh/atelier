// SPDX-License-Identifier: Apache-2.0
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
bool LoadedGraph(const std::filesystem::path& path,AnimationLoadedGraph& graph,std::string& error)
{
    std::vector<std::uint8_t> bytes;
    return Read(path,bytes,error) && graph.source.Load(bytes,error)
        && graph.binding.Bind(graph.source,error) && graph.runtime.FromBinding(graph.binding,error);
}
}
bool LoadGameplayResources(const std::filesystem::path& root,
    std::shared_ptr<const GameplayResources>& output,std::string& error)
{
    auto resources=std::make_shared<GameplayResources>();
    auto animation=std::make_shared<AnimationSource>();
    std::vector<std::uint8_t> bytes;
    if(!Read(root/"settings.skate",bytes,error) || !resources->settings.Load(bytes,error))return false;
    if(!Read(root/"metadata/bank-0.skate",bytes,error) || !animation->metadata.Load(bytes,error))return false;
    AnimationMetadata offboard;
    if(!Read(root/"metadata/bank-1.skate",bytes,error) || !offboard.Load(bytes,error)
        || !animation->metadata.Merge(offboard,error))return false;
    PhysicsSkeletons skeletons;
    if(!Read(root/"physics-skeletons.skate",bytes,error)
        || !skeletons.Load(bytes,animation->metadata.source_sha256,error))return false;
    const auto* physical=skeletons.Find("PHYS_TPOSE");
    if(!physical){error="Native skating resources require PHYS_TPOSE";return false;}
    resources->physical_skeleton=*physical;
    AnimationPoseFrames frames;
    if(!Read(root/"animation/rig.skate",bytes,error) || !frames.rig.Load(bytes,error))return false;
    std::error_code ec;std::vector<std::filesystem::path> clips;
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
    if(!LoadedGraph(root/"action.graph",resources->graphs.action,error)
        || !LoadedGraph(root/"motion.graph",resources->graphs.motion,error))return false;
    if(!Read(root/"camera.graph",bytes,error) || !resources->camera_graph.Load(bytes,error)
        || !Read(root/"camera.skate",resources->camera_data,error))return false;
    if(!Read(root/"gestures.skate",bytes,error) || !LoadGestureData(bytes,resources->gestures,error))return false;
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
}
