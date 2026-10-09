#include "AnimationPhaseInput.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    detail::DataReader r;explicit Input(const std::vector<std::uint8_t>& b):r{b} {r.at=0;}
    std::uint32_t Word(){return r.Word();}float Float(){return r.Float();}std::uint64_t Wide(){const auto lo=Word();return lo|(std::uint64_t(Word())<<32);}
    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> v;for(auto& x:v)x=Word();return v;}
    template<std::size_t N>std::array<float,N> Floats(){std::array<float,N> v;for(auto& x:v)x=Float();return v;}
    template<class T,std::size_t N,class C>std::array<T,N> Array(C callback){std::array<T,N> v;for(auto& x:v)x=callback(*this);return v;}
    template<class T,class C>std::optional<T> Optional(C callback){if(Word())return callback(*this);return std::nullopt;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;void Word(std::uint32_t w){for(unsigned i=0;i<4;++i)bytes.push_back(std::uint8_t(w>>(i*8)));}void Wide(std::uint64_t w){Word(std::uint32_t(w));Word(std::uint32_t(w>>32));}void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}void String(std::string_view s){Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}void Block(const Output& row){Word(std::uint32_t(row.bytes.size()/4));bytes.insert(bytes.end(),row.bytes.begin(),row.bytes.end());}
};
// GENERATED_PROTOCOL
PhysicsPosePacket ReadPose(Input& i)
{
    PhysicsPosePacket p;p.bone_count=i.Word();const auto n=i.Word();for(std::uint32_t j=0;j<n;++j)p.hierarchy.push_back(i.Array<Vec4,4>([](Input& in){return in.Floats<4>();}));const auto m=i.Word();for(std::uint32_t j=0;j<m;++j)p.local.push_back(i.Array<Vec4,4>([](Input& in){return in.Floats<4>();}));p.timestep=i.Float();p.foot_surface_ids=i.Words<2>();p.flags=i.Word();p.board_flipped=i.Word()!=0;p.mirrored=i.Word()!=0;p.riding_switch=i.Word()!=0;p.riding_fakie=i.Word()!=0;p.weight_forwards=i.Word()!=0;p.regular_stance=i.Word()!=0;p.air_dismount_revert_frames=std::int32_t(i.Word());return p;
}
void ObservePose(Output& o,const PhysicsPosePacket& p)
{
    o.Word(p.bone_count);o.Word(std::uint32_t(p.hierarchy.size()));for(const auto& m:p.hierarchy)for(auto v:m)for(auto f:v)o.Float(f);o.Word(std::uint32_t(p.local.size()));for(const auto& m:p.local)for(auto v:m)for(auto f:v)o.Float(f);o.Float(p.timestep);for(auto v:p.foot_surface_ids)o.Word(v);o.Word(p.flags);o.Word(p.board_flipped);o.Word(p.mirrored);o.Word(p.riding_switch);o.Word(p.riding_fakie);o.Word(p.weight_forwards);o.Word(p.regular_stance);o.Word(std::uint32_t(p.air_dismount_revert_frames));
}
void Snapshot(Output& out,const AnimationProfile& profile,const AnimationPhaseOutput& phase,const PhysicsPosePacket& pose)
{
    Output row;Observe(row,profile);Observe(row,phase.reset);Observe(row,phase.Publication());Observe(row,phase.External());row.Word(phase.Mirrored());row.Word(phase.WeightForwards());row.Word(phase.Flags());Observe(row,phase.Packet());ObservePose(row,pose);out.Block(row);
}
std::vector<std::uint8_t> Read(std::string path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char**argv)
{
    if(argc!=2)return 2;SettingsDatabase data;std::string error;if(!data.Load(Read(argv[1]),error)){std::cerr<<error;return 2;}const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(bytes);Output out;const auto cases=i.Word();
    for(std::uint32_t c=0;c<cases;++c)
    {
        const auto mode=i.r.String();AnimationProfile profile;const bool loaded=profile.Load(data,mode,error);out.Word(c);out.Word(loaded);out.String(error);const auto commands=i.Word();if(!loaded){if(commands)return 2;continue;}AnimationPhaseOutput phase;PhysicsPosePacket pose;Snapshot(out,profile,phase,pose);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=i.Word();bool ok=true;error.clear();
            if(op==0)phase.reset=ReadAnimationAdditionalResetFields(i);
            else if(op==1)profile=ReadAnimationProfile(i);
            else if(op==2){pose=ReadPose(i);phase.Publish(pose,profile,i.Word());}
            else if(op==3){AnimationExternalReset reply;reply.transform=i.Array<RawVector,4>([](Input& in){return in.Words<4>();});reply.byte64=std::uint8_t(i.Word());phase.PublishExternalReset(reply);}
            else if(op==4)ok=ResetAnimationPacket(pose,phase.reset,error);
            else if(op==5)ok=profile.Load(data,i.r.String(),error);
            else return 2;
            out.Word(c);out.Word(n);out.Word(op);out.Word(ok);out.String(error);Snapshot(out,profile,phase,pose);
        }
    }
    if(!i.r.ok||i.r.at!=bytes.size())return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));
}
