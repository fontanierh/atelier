// SPDX-License-Identifier: Apache-2.0
#include "PlayerGrindInput.h"
#include "PlayerGrindInputDetail.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace player_grind_detail;
bool PlayerGrindInputState::PreUpdate(const ProcessedPhysicsInput& p,const PlayerGrindStaticProvider& provider,
    const WorldGeometry& world,PlayerGrindPreContext c,PlayerGrindInputHost& host,std::optional<PlayerGrindPending>& output,std::string& error)
{
    previous_direction=Float4(investigation.direction_1136);investigation={};Permission(p,c.air_counter);
    std::vector<std::size_t> indices;
    if((p.flags_2476&0x01000000u)==0){std::array<float,3> min,max;for(std::size_t i=0;i<3;++i){min[i]=c.board[3][i]-1.2f;max[i]=c.board[3][i]+1.2f;}
        if(!provider.Query(min,max,indices,error))return false;}
    const auto mode=MaterialMode(p,!indices.empty(),c.air_targeting_grind_9653);
    if(!host.ApplyMaterialMode(mode,error))return false;AdvanceHistory(p);
    std::vector<PlayerGrindPrimitive> edges;for(auto index:indices)edges.push_back(provider.Primitives()[index]);
    const auto result=InvestigatePlayerGrindContact({c.board,
        {p.category_2512,p.state_2508,p.scalar_2652,Float4(p.vectors_400_416[0]),settings_.slope_threshold},
        p.flags_2468,p.flags_2472,p.flags_2476,p.flags_2484,c.tip_state,settings_.truck_to_wheel,settings_.deck_to_truck,
        settings_.test_above,settings_.test_below,c.translation_2796,c.stability_nudge_2800,c.balance_2720,
        Float4(p.vectors_464_480_496_512_528[0]),grounded_frames,low_wheel_frames,
        disabled||(grind_history!=0&&p.grind_words_2532_2536[1]!=2)},edges);
    GrindInvestigationFields fields;std::optional<std::array<std::uint64_t,2>> metadata;std::optional<PlayerGrindGeometryWork> geometry;
    if(result.candidate){const auto& contact=*result.candidate;const auto& g=contact.geometry;const auto& edge=edges[g.primitive];
        const auto native=provider.Metadata(indices[g.primitive]);if(!native){error="Selected static grind primitive lacks metadata";return false;}
        metadata=native->spline_guids;fields.valid_1488=true;fields.family_1248=contact.kind;fields.entry_kind_1252=std::uint32_t(contact.entry_kind);
        fields.tangent_1104=Raw4(g.direction);fields.point_1120=Raw4(g.centre);
        fields.direction_1136=Raw4(PlayerGrindDirectedTangent(edge.start,edge.end,Float4(p.vectors_400_416[0]),previous_direction));
        fields.primitive_start_1264=Raw4(edge.start);fields.primitive_end_1280=Raw4(edge.end);fields.owner_1296=edge.owner;
        fields.primitive_flags_1300=native->flags&0x80000000u;fields.flags_1516=contact.front?0x20000000u:0;
        if(contact.kind==0){fields.front_contact_1200=Raw4(g.front);fields.rear_contact_1216=Raw4(g.rear);}
        else if(contact.kind==3)fields.front_contact_1200=Raw4(g.centre);
        PlayerGrindSurfaceInput input{edge.start,edge.end,g.centre,p.state_2508==402?std::optional<Vec4>(c.board[3]):std::nullopt,settings_.deck_to_truck};
        geometry=PlayerGrindGeometryWork{input,PreparePlayerGrindSurface(input),{}};
    }else{previous_proximity=bool(result.proximity);
        if(result.proximity){const auto& proximity=*result.proximity;const auto& edge=edges[proximity.contact.primitive];
            const auto native=provider.Metadata(indices[proximity.contact.primitive]);if(!native){error="Static grind proximity lacks metadata";return false;}
            fields.vector_1232=Raw4(proximity.contact.position);fields.second_start_1312=Raw4(edge.start);fields.second_end_1328=Raw4(edge.end);
            fields.second_owner_1344=edge.owner;fields.second_flags_1348=native->flags&0x80000000u;
            fields.flags_1516=0x08000000u|(proximity.deck_contact?0x04000000u:0);}}
    previous_velocity=p.vectors_400_416[0];friction_vs_time=settings_.friction.Evaluate(elapsed);fields.friction_1496=friction_vs_time;investigation=fields;
    if(geometry&&geometry->plan){const auto& probes=geometry->plan->probes;for(std::size_t index=0;index<probes.size();++index)
        if(!host.SurfaceProbe(world,{p.actor_query_2948,p.actor_query_2952},index,probes[index],geometry->hits[index],error))return false;}
    output.emplace(fields,std::move(geometry),metadata);return true;
}
}
