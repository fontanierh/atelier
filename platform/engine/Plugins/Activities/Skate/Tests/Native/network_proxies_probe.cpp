// SPDX-License-Identifier: Apache-2.0
// Checker prepends accepted body/collision/volume transport adapters.
#include "NetworkProxies.h"
namespace
{
std::uint64_t Wide(){const auto lo=Word(),hi=Word();return std::uint64_t(lo)|(std::uint64_t(hi)<<32);}
void OutWide(std::uint64_t w){Out(std::uint32_t(w));Out(std::uint32_t(w>>32));}
InertiaDynamics ReadInertia(){return {Vector(),Float(),Float(),Float(),Float(),Float(),Float()};}
NetworkBodyPose ReadNetworkPose(){const auto p=Vector();return {p,Floats<4>()};}
NetworkBodyState ReadNetworkState()
{
    NetworkBodyState f;f.root=ReadNetworkPose();f.enabled=Wide();const auto n=Word();
    for(std::uint32_t i=0;i<n;++i){const auto pose=ReadNetworkPose();const auto velocity=Vector(),angular=Vector();f.bodies.push_back({pose,velocity,angular});}return f;
}
void OutSchema(const NetworkCollisionSchema& schema)
{OutWide(schema.fingerprint);Out(std::uint32_t(schema.volumes.size()));for(const auto& entry:schema.volumes){Out(std::uint32_t(entry.first));OutVolumes({entry.second});}}
void OutProxies(const NetworkProxies& p){Out(std::uint32_t(p.bodies.size()));for(const auto& b:p.bodies)Out(b);OutVolumes(p.volumes);}
NetworkProxies ReadProxies(){NetworkProxies p;const auto n=Word();for(std::uint32_t i=0;i<n;++i)p.bodies.push_back(ReadBody());p.volumes=ReadVolumes();return p;}
}
int main()
{
    const auto cases=Word();for(std::uint32_t index=0;index<cases;++index)
    {
        const auto op=Word();Out(index);Out(op);const auto mark=output.size();Out(0u);const auto start=output.size();
        if(op==0){const auto [center,radius]=RemotePrimitiveBounds(ReadPrimitive());Out(center);Out(radius);}
        else if(op==1 || op==2)
        {
            std::string error;const auto definition=Definition(error);if(!definition)std::abort();std::array<BodySnapshot,7> board;for(auto& b:board)b=ReadBody();std::array<BodySnapshot,26> skeleton;for(auto& b:skeleton)b=ReadBody();
            std::array<BodyMassProperties,7> masses{};for(auto& m:masses)m.dynamics=ReadInertia();const auto target_count=Word();const auto board_volumes=ReadVolumes(),rider_volumes=ReadVolumes();const auto fingerprint=Wide();
            auto all=board_volumes;all.insert(all.end(),rider_volumes.begin(),rider_volumes.end());const auto schema=NetworkCollisionSchema::FromWorldVolumes(all,board,skeleton,fingerprint);OutSchema(schema);
            if(op==2)
            {
                const NetworkProxyContext context{board,skeleton,masses,*definition,target_count};auto proxies=ReadProxies();OutProxies(proxies);const auto n=Word();Out(n);
                for(std::uint32_t j=0;j<n;++j)
                {
                    const auto cmd=Word();Out(cmd);
                    if(cmd==0){const auto frame=ReadNetworkState();const float age=Float();proxies.Append(frame,schema,context,age);}
                    else if(cmd==1)proxies={};
                    else if(cmd==2){const auto nv=Word();std::vector<BoardCollision> contacts;for(std::uint32_t k=0;k<nv;++k)contacts.push_back(ReadCollision());Out(std::uint32_t(AppendRemoteContacts(contacts,board_volumes,rider_volumes,proxies.volumes)));OutCollisions(contacts);}
                    else return 2;
                    OutProxies(proxies);
                }
            }
            // Original proxy publication does not rewrite the local owner.
            for(const auto& b:board)Out(b);for(const auto& b:skeleton)Out(b);Out(*definition);
        }
        else if(op==3)
        {
            const auto board=ReadVolumes(),rider=ReadVolumes(),remote=ReadVolumes();const auto n=Word();std::vector<BoardCollision> contacts;for(std::uint32_t j=0;j<n;++j)contacts.push_back(ReadCollision());
            Out(std::uint32_t(AppendRemoteContacts(contacts,board,rider,remote)));OutCollisions(contacts);
        }
        else return 2;
        output[mark]=std::uint32_t(output.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(const auto w:output){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
