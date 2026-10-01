// SPDX-License-Identifier: Apache-2.0
#include "SimulationClock.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace atelier::skate;
namespace {
std::uint32_t Word(){std::uint32_t v;if(std::fread(&v,4,1,stdin)!=1)std::abort();return v;}
float Float(){const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
void Out(std::uint32_t v){std::fwrite(&v,4,1,stdout);}
void Wide(std::uint64_t v){Out(std::uint32_t(v));Out(std::uint32_t(v>>32));}
void Status(bool okay,std::string_view error){Out(std::uint32_t(okay));Out(std::uint32_t(error.size()));std::fwrite(error.data(),1,error.size(),stdout);}
void Owner(const SimulationClock& c){Out(c.TicksUntilReset());Wide(c.PeriodNanoseconds());}
}
int main(){const auto cases=Word();Out(cases);for(unsigned c=0;c<cases;++c){SimulationClock clock;Owner(clock);const auto commands=Word();Out(commands);for(unsigned n=0;n<commands;++n){const auto op=Word();Out(op);std::string error;bool okay=true;switch(op){case 0:clock=SimulationClock{};break;case 1:{const auto timestep=Float();const auto ticks=Word();okay=clock.Apply({timestep,ticks},error);break;}case 2:clock.FinishTick();break;case 3:{const auto count=Word();std::vector<camera::SimulationRateRequest> requests;for(unsigned k=0;k<count;++k){const auto timestep=Float();const auto ticks=Word();requests.push_back({timestep,ticks});}okay=clock.ApplyRequests(requests,error);break;}case 4:{const auto count=Word();for(unsigned k=0;k<count;++k)clock.FinishTick();break;}default:return 2;}Status(okay,error);Owner(clock);}}return std::ferror(stdout)?2:0;}
