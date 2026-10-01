// SPDX-License-Identifier: Apache-2.0
#include "OffboardContactPrivate.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void OffboardContactToolkit::BeginInput(){if(readiness!=0)--readiness;Refresh();}
void OffboardContactToolkit::ResetHistory(){Refresh();readiness=0;history={};}
bool OffboardContactToolkit::Submit(OffboardToolkitInput input,std::int32_t group,const OffboardContactScene& scene,std::string& error)
{
    auto batch=layout.Prepare(input,group);OffboardQueryResults results;if(!scene.Execute(batch,results,error))return false;
    readiness=0;pending=std::make_pair(std::move(batch),std::move(results));error.clear();return true;
}
std::optional<OffboardCollectedContacts> OffboardContactToolkit::Refresh()
{
    using namespace offboard_contact;prefix={};readiness=30;if(!pending)return std::nullopt;
    auto completed=std::move(*pending);pending.reset();const auto input=completed.first.input;OffboardContactPrefix current;
    current.ConsumeSupport(input,completed.second.trajectories,candidate.flags);
    auto samples=Collect(completed.first,layout,completed.second);InsertObstacles(input,samples);CorrectNormals(input,samples);
    const auto simplified=Simplify(input,samples.ground);current.distance_172=simplified.first;
    const auto profile=BuildProfile(input,samples.ground,simplified.second);auto candidates=Generate(input,profile,current,simplified.first,candidate.flags);
    Publish(input,profile,samples,candidates,simplified.first,candidate,history,current);prefix=current;
    return OffboardCollectedContacts{std::move(completed.first),std::move(completed.second),current,std::move(samples)};
}
}
