#include "AnimationSamples.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
using namespace atelier::skate;
static void Word(std::ostream& out,std::uint32_t value) { for (unsigned i=0;i<4;++i) out.put(char(value>>(8*i))); }
static void Wide(std::ostream& out,std::uint64_t value) { Word(out,std::uint32_t(value));Word(out,std::uint32_t(value>>32)); }
static void String(std::ostream& out,std::string_view value) { Word(out,std::uint32_t(value.size()));out.write(value.data(),value.size()); }
static std::vector<std::uint8_t> Read(const std::string& path)
{
    std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};
}
static void Dump(std::ostream& out,const AnimationClipSamples& clip)
{
    out.write("ATCLRAW1",8);String(out,clip.name);Word(out,clip.bank);Wide(out,clip.record);Word(out,clip.fps_bits);
    for (auto value:clip.loop_translation) Word(out,value);
    for (auto value:clip.loop_rotation) Word(out,value);
    Word(out,clip.channel_animation);Word(out,std::uint32_t(clip.channel_weights.size()));
    for (auto value:clip.channel_weights) Word(out,value);
    Word(out,clip.frame_count);Word(out,clip.bone_count);
    for (std::uint32_t frame=0;frame<clip.frame_count;++frame)
        for (std::uint32_t bone=0;bone<clip.bone_count;++bone)
            for (auto value:clip.Sample(frame,bone)) Word(out,value);
}
static void DumpRig(std::ostream& out,const AnimationRig& rig)
{
    out.write("ATSKEL01",8);Word(out,std::uint32_t(rig.bones.size()));Word(out,rig.has_trajectory);
    for (const auto& bone:rig.bones) {String(out,bone.name);Word(out,std::uint32_t(bone.parent));Word(out,std::uint32_t(bone.mirror));}
    Word(out,std::uint32_t(rig.poses.size()));
    for (const auto& pose:rig.poses)
    {
        Word(out,pose.bank);String(out,pose.name);Wide(out,pose.record);Word(out,std::uint32_t(pose.samples.size()));
        for (const auto& sample:pose.samples) for (auto value:sample) Word(out,value);
    }
}
int main(int argc,char** argv)
{
    if (argc!=4) return 1;
    const std::string mode=argv[1],path=argv[2],reference=argv[3];std::string error;
    if (mode=="clip")
    {
        AnimationClipSamples clip;if (!clip.Load(Read(path),error)) {std::cerr<<error<<'\n';return 2;}
        Dump(std::cout,clip);return std::cout?0:2;
    }
    if (mode=="rig")
    {
        AnimationRig rig;if (!rig.Load(Read(path),error)) {std::cerr<<error<<'\n';return 2;}
        for (const auto& pose:rig.poses)
        {
            if (rig.Pose(pose.bank,pose.record)!=&pose) return 3;
            const AnimationReferencePose* expected=nullptr;
            for (const auto& candidate:rig.poses)
                if (candidate.bank==pose.bank && candidate.name==pose.name) expected=&candidate;
            auto name=pose.name;for (auto& c:name) if (c>='A'&&c<='Z') c=char(c-'A'+'a');
            if (rig.NamedPose(pose.bank,name)!=expected) return 3;
        }
        if (rig.NamedPose(0,"missing_pose") || rig.Pose(99,0)) return 3;
        DumpRig(std::cout,rig);return std::cout?0:2;
    }
    if (mode!="all") return 1;
    std::string name;std::size_t count=0;
    while (std::getline(std::cin,name))
    {
        AnimationClipSamples clip;
        if (!clip.Load(Read(path+"/clips/"+name+".skate"),error)) {std::cerr<<name<<": "<<error<<'\n';return 2;}
        std::ostringstream out(std::ios::binary);Dump(out,clip);
        const auto bytes=Read(reference+"/clips/"+name+".raw");
        const auto actual=out.str();
        if (actual.size()!=bytes.size() || !std::equal(bytes.begin(),bytes.end(),actual.begin(),
            [](std::uint8_t a,char b){return a==std::uint8_t(b);}))
        {std::cerr<<"Animation sample differs: "<<name<<'\n';return 3;}
        ++count;
    }
    std::cout<<count<<'\n';
}
