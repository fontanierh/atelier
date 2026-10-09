#include "GroundSurfaceRuntime.h"
#include "PhysicalSimulationRuntime.h"
namespace atelier::skate
{
bool ChoosePlayerGroundSurface(std::array<std::uint32_t,4> surfaces,std::array<bool,4> contacts,
    bool forced_twelve,std::uint32_t& output,std::string& error)
{
    std::array<std::uint32_t,16> votes{};
    for(unsigned i=0;i<4;++i)
    {
        const auto surface=surfaces[i];if(surface==0)continue;
        if(surface>=16){error="native surface histogram index exceeded";return false;}
        votes[surface]+=contacts[i]?4u:1u;
    }
    std::uint32_t winner=1,maximum=0;
    for(std::uint32_t surface=1;surface<14;++surface)if(votes[surface]>maximum){maximum=votes[surface];winner=surface;}
    output=forced_twelve?12u:winner;error.clear();return true;
}
bool ActivePlayerGroundSurface(const PhysicalRidingOutputs& riding,const BoardRuntime& board,std::uint32_t& output,std::string& error)
{
    std::array<bool,4> contacts;for(unsigned i=0;i<4;++i)contacts[i]=riding.ground.parts[i].in_contact;
    bool forced=false;for(const auto& report:board.ContactReports())if((report.other_surface&0x0f80)==0x0600){forced=true;break;}
    return ChoosePlayerGroundSurface(riding.wheel_lines.physics_surfaces,contacts,forced,output,error);
}
GroundSurfaceReport ReportGroundSurface(const PhysicalRidingOutputs& riding)
{
    GroundSurfaceReport report;std::array<std::uint32_t,128> votes{};std::uint32_t best=0;
    for(unsigned i=0;i<4;++i)
    {
        const bool contact=riding.ground.parts[i].in_contact;report.wheels+=contact?1u:0u;
        const auto sound=riding.wheel_lines.sound_surfaces[i]&0x7fu;
        if(sound!=0&&(votes[sound]+=contact?4u:1u)>best){best=votes[sound];report.sound=sound;}
    }
    std::array<bool,4> contacts;for(unsigned i=0;i<4;++i)contacts[i]=riding.ground.parts[i].in_contact;
    std::string error;if(!ChoosePlayerGroundSurface(riding.wheel_lines.physics_surfaces,contacts,false,report.physics,error))report.physics=1;
    return report;
}
}
