#pragma once
#include "WorldGeometry.h"
#include "Settings.h"
#include <string>
namespace atelier::skate
{
struct OffboardGroundFrame{Vec3 right{1,0,0},up{0,1,0},forward{0,0,1},position{};};
struct OffboardGroundContext{std::uint32_t selection_flags_2948;std::int32_t matching_id_2952;};
struct OffboardGroundEdge{Vec3 start,end;};
struct OffboardGroundEdgeSearch{Vec3 min,max;OffboardGroundFrame frame;OffboardGroundContext context;bool narrow_forward;};
struct OffboardGroundEdgeSelection{OffboardGroundEdge edge;Vec3 closest;};
struct OffboardGroundLine{Vec3 start,end;float radius;};
struct OffboardGroundPacket{OffboardGroundContext context;Vec3 center,up,tangent;std::array<OffboardGroundLine,7> lines;};
struct OffboardGroundLineHit{Vec3 position,face_normal;float fraction;std::uint16_t packed_surface;};
struct OffboardGroundGeometryResult{OffboardGroundFrame frame;std::uint32_t kind;bool flag26,flag27,flag28;};
struct OffboardGroundConsumeInput{OffboardGroundFrame frame_80;Vec3 contact_position_192;std::uint32_t contact_flags_368;float reach_364;Vec3 previous_input_up_416;};
struct OffboardGroundAdjustment{bool state_752=false,state_753=false,state_754=false;OffboardGroundFrame frame_768;Vec3 input_up_416;};
OffboardGroundFrame OffboardGroundQueryFrame(const Mat4&);
Mat4 OffboardGroundNativeFrame(OffboardGroundFrame);
OffboardGroundEdgeSearch SearchOffboardGroundEdges(OffboardGroundFrame,OffboardGroundContext,Vec3 state_vector_1040,std::uint32_t processed_2488);
Vec3 ClosestOffboardGroundEdgePoint(Vec3,OffboardGroundEdge);
std::optional<OffboardGroundEdgeSelection> SelectOffboardGroundEdge(OffboardGroundEdgeSearch,const std::vector<OffboardGroundEdge>&);
std::optional<OffboardGroundPacket> PrepareOffboardGroundPacket(OffboardGroundFrame,OffboardGroundContext,OffboardGroundEdgeSelection,float collision_offset);
OffboardGroundGeometryResult InterpretOffboardGroundHits(const OffboardGroundPacket&,const std::array<std::optional<OffboardGroundLineHit>,7>&);
OffboardGroundAdjustment ConsumeOffboardGroundGeometry(OffboardGroundConsumeInput,std::optional<OffboardGroundGeometryResult>);
class OffboardGroundGeometry
{
public:
    std::optional<std::pair<OffboardGroundPacket,std::array<std::optional<OffboardGroundLineHit>,7>>> pending;
    float collision_offset=0;
    bool Load(const SettingsDatabase&,std::string& error);
    void Reset(){pending.reset();}
    OffboardGroundAdjustment Consume(OffboardGroundConsumeInput);
    bool Submit(const WorldGeometry&,const Mat4& frame,Vec4 velocity,OffboardGroundContext,std::uint32_t flags_2488,std::string& error);
};
}
