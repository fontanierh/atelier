#include "OffboardGroundGeometry.h"
#include "OffboardGroundScene.h"
#include "StockSettingsReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool OffboardGroundGeometry::Load(const SettingsDatabase& data,std::string& error)
{
    float offset;StockSettingsReader reader(data);if(!reader.Float("physics_grinds","default","DeckCenterToTruck",offset,error))return false;
    pending.reset();collision_offset=offset;error.clear();return true;
}
OffboardGroundAdjustment OffboardGroundGeometry::Consume(OffboardGroundConsumeInput input)
{
    std::optional<OffboardGroundGeometryResult> geometry;
    if(pending){const auto completed=std::move(*pending);pending.reset();geometry=InterpretOffboardGroundHits(completed.first,completed.second);}
    return ConsumeOffboardGroundGeometry(input,geometry);
}
bool OffboardGroundGeometry::Submit(const WorldGeometry& world,const Mat4& native_frame,Vec4 velocity,OffboardGroundContext context,std::uint32_t flags,std::string& error)
{
    const auto frame=OffboardGroundQueryFrame(native_frame);const auto search=SearchOffboardGroundEdges(frame,context,{velocity[0],velocity[1],velocity[2]},flags);
    // The active source SceneService supplies no dynamic/vehicle/indexed edges
    // for this particular Ground Sync producer. Other consumers pass live views
    // explicitly to OffboardGroundScene.
    const std::vector<OffboardGroundEdgeBody> dynamic,vehicles;const std::vector<OffboardGroundAlternateRecord> alternates;const std::vector<OffboardGroundIndexedBody> indexed;
    const auto scene=OffboardGroundScene::Create(world,{dynamic,vehicles,alternates,indexed,false},error);if(!scene)return false;
    const auto candidates=scene->EdgeCandidates(search);const auto selected=SelectOffboardGroundEdge(search,candidates);
    if(selected)
    {
        const auto packet=PrepareOffboardGroundPacket(frame,context,*selected,collision_offset);
        if(packet){std::array<std::optional<OffboardGroundLineHit>,7> hits;if(!scene->QueryLines(*packet,hits,error))return false;pending=std::make_pair(*packet,hits);}
    }
    error.clear();return true;
}
}
