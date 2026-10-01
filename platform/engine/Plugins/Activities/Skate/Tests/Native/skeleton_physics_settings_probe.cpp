// SPDX-License-Identifier: Apache-2.0
// Checker prepends tested body, collision and constraint record adapters.
#include "SkeletonPhysicsSettings.h"
#include <fstream>
#include <iterator>
namespace
{
std::vector<std::uint8_t> File(const char* path){std::ifstream f(path,std::ios::binary);return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(f),{});}
std::string Text(){const auto n=Word();std::string s;for(std::uint32_t i=0;i<n;++i)s+=char(Word());return s;}
std::vector<Mat4> Hierarchy(){const auto n=Word();std::vector<Mat4> h;for(std::uint32_t i=0;i<n;++i)h.push_back(Matrix());return h;}
std::array<std::size_t,24> Indices(){std::array<std::size_t,24> a;for(auto& i:a)i=Word();return a;}
void OutJoints(const SkeletonJoints& j){for(const auto& r:j.records){Out(static_cast<std::uint32_t>(r.parent));Out(static_cast<std::uint32_t>(r.child));Out(r.parameters);Out(r.frames);}}
}
int main(int argc,char** argv)
{
    if(argc!=4)return 2;std::string error;SettingsDatabase data;PhysicsSkeletons bank;
    if(!data.Load(File(argv[1]),error)||!bank.Load(File(argv[2]),argv[3],error)){std::cerr<<error;return 2;}
    const auto* physical=bank.Find("PHYS_TPOSE");if(!physical)return 2;
    const auto count=Word();for(std::uint32_t index=0;index<count;++index)
    {
        const auto op=Word();Out(index);Out(op);const auto mark=output.size();Out(0u);const auto start=output.size();
        if(op==0)
        {
            const bool hat=Word()!=0;const auto key=Text();const auto mapped=Matrices<24>();const auto spawn=Matrix();const auto sim=Simulation();
            const auto body=LoadSkeletonBody(data,*physical,mapped,spawn,sim,hat ? std::optional<std::string_view>(key):std::nullopt,error);Out(std::uint32_t(body.has_value()));
            if(body){Out(body->definition);Out(*body);}else Out(error);
        }
        else if(op==1)
        {
            const bool all=Word()!=0;const auto settings=LoadSkeletonCollisionSettings(data,*physical,error);Out(std::uint32_t(settings.has_value()));
            if(settings){const SkeletonCollisionMode mode(*settings,all);OutMode(mode);const auto feedback=LoadSkeletonFeedbackSettings(data,*settings,error);Out(std::uint32_t(feedback.has_value()));if(feedback)OutFeedback(SkeletonCollisionFeedback(*feedback));else Out(error);}else Out(error);
        }
        else if(op==2)
        {
            const auto hierarchy=Hierarchy();const auto n=Word();std::vector<std::int32_t> parents;for(std::uint32_t i=0;i<n;++i)parents.push_back(static_cast<std::int32_t>(Word()));const auto indices=Indices();
            const auto joints=LoadSkeletonJoints(data,*physical,hierarchy,parents,indices,error);Out(std::uint32_t(joints.has_value()));if(joints)OutJoints(*joints);else Out(error);
            const bool drives=Word()!=0;
            if(drives)
            {
                const auto drive_hierarchy=Hierarchy();const auto drive_indices=Indices();const auto mapped=Matrices<24>();const auto alignment=Matrix(),spawn=Matrix();const auto sim=Simulation();
                if(joints){const auto value=LoadSkeletonDrives(data,*physical,drive_hierarchy,drive_indices,mapped,*joints,alignment,spawn,sim,error);Out(std::uint32_t(value.has_value()));if(value)OutDrives(*value);else Out(error);}else Out(2u);
            }
        }
        else return 2;
        output[mark]=static_cast<std::uint32_t>(output.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(const auto w:output){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
