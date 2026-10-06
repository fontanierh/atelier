// SPDX-License-Identifier: Apache-2.0
#include "WorldContactProducer.h"
#include "NativeMath.h"
#include <algorithm>
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
std::uint32_t Word(float value) {std::uint32_t word;std::memcpy(&word,&value,4);return word;}
float Signum(float value) {return std::isnan(value) ? value:std::copysign(1.0f,value);}
bool PointInFloorTriangle(Vec3 point,const std::array<Vec3,3>& vertices)
{
    auto cross=[](Vec3 a,Vec3 b,Vec3 p){return (b.x-a.x)*(p.z-a.z)-(b.z-a.z)*(p.x-a.x);};
    const float winding=Signum(cross(vertices[0],vertices[1],vertices[2]));
    for (std::size_t i=0;i<3;++i)
    {
        const auto a=vertices[i],b=vertices[(i+1)%3];
        if (!(winding*cross(a,b,point)>=-0.001f*std::hypot(b.x-a.x,b.z-a.z))) return false;
    }
    return true;
}
bool FloorAt(Vec3 probe,std::optional<std::size_t> excluded,std::optional<Vec3> reference,
             const std::vector<std::size_t>& candidates,const std::vector<WorldTriangle>& triangles,const std::vector<Bounds>& bounds)
{
    for (auto index:candidates)
    {
        if (excluded && *excluded==index) continue;
        const auto& other=triangles[index];const auto normal=other.triangle.feature.normal;
        if (normal.y<0.98f || (reference && (reference->x*normal.x+reference->y*normal.y)+reference->z*normal.z<0.999f)) continue;
        const auto b=bounds[index];
        if (probe.x<b.min.x-0.001f || probe.x>b.max.x+0.001f || probe.z<b.min.z-0.001f || probe.z>b.max.z+0.001f) continue;
        const auto& p=other.triangle.vertices;const float gap=std::fabs((normal.x*(probe.x-p[0].x)+normal.y*(probe.y-p[0].y))+normal.z*(probe.z-p[0].z));
        if (gap<=0.002f && PointInFloorTriangle(probe,p)) return true;
    }
    return false;
}
bool ImportedInternalFloorEdge(std::size_t source_index,const WorldTriangle& source,Vec3 contact,Vec3 contact_normal,
                               const std::vector<std::size_t>& candidates,const std::vector<WorldTriangle>& triangles,const std::vector<Bounds>& bounds)
{
    const auto face=source.triangle.feature.normal;const float lateral=std::hypot(contact_normal.x,contact_normal.z);
    if (lateral<0.05f) return false;
    auto probe=[&](float sign){return Vec3{contact.x+((sign*0.005f)*contact_normal.x)/lateral,contact.y,contact.z+((sign*0.005f)*contact_normal.z)/lateral};};
    if (face.y>=0.98f && contact_normal.y>0.05f)
    {
        auto beyond=probe(1);const auto origin=source.triangle.vertices[0];
        beyond.y=origin.y-(face.x*(beyond.x-origin.x)+face.z*(beyond.z-origin.z))/face.y;
        return !PointInFloorTriangle(beyond,source.triangle.vertices)
            && FloorAt(beyond,source_index,face,candidates,triangles,bounds);
    }
    if (std::fabs(face.y)>0.2f) return false;
    for (auto p:source.triangle.vertices) if (p.y>contact.y+0.01f) return false;
    return FloorAt(probe(-1),std::nullopt,std::nullopt,candidates,triangles,bounds)
        && FloorAt(probe(1),std::nullopt,std::nullopt,candidates,triangles,bounds);
}
// Imported worlds are built from game meshes, not authored skate collision: plank decks with gaps, panel seams and
// trim lips a few millimetres proud. A rigid wheel meeting such an edge gets a contact normal tilted back against its
// travel and stops dead, where a urethane wheel rolls over it; and the trucks and deck, though well clear of it, get
// predictive contacts against its face that stop the board just the same. An edge within SmallEdgeStep of the wheels'
// bottoms is ridden over: a wheel contact on it that opposes the wheel's travel pushes straight up under the wheel
// instead, so the wheel steps up onto it, and the other volumes' contacts against its side, from the wheels' bottoms up,
// are dropped. Heights are measured along the board's up (seams on a ramp), else along the world's (a board pitched by
// the last bump, whose up leans over the next edge). Taller edges, contacts from above and edges a wheel is rolling
// off keep their own normal. A ramp is not an edge, though near the wheels it can look like one: a transition's face
// meets the front wheels tilted back against their travel, and a board landing pitched meets it with its trucks. So a
// wheel steps up where it touches an edge or corner, or the flat of a face no taller than SmallEdgeStep in the world
// (a plank's bevel), never a ramp's; and the other volumes pass only faces that rise no higher than SmallEdgeStep over
// the wheels' bottoms in the world, as a plank's side or a lip does.
constexpr float SmallEdgeStep=0.012f,RiderGapDepth=0.05f;
enum class SmallEdge {None,StepUp,Drop};
SmallEdge RideOverSmallEdge(const BoardWorldVolume& volume,const Triangle& face,Vec3 up,float floor,float lowest,ContactPair& pair,Vec3& normal)
{
    const float height=Dot3(pair.b,up)-floor,along=Dot3(normal,up);
    if (height>SmallEdgeStep) return SmallEdge::None;
    // The trucks and deck (body ids 4 up; 0-3 are the wheels) stand above the wheels' bottoms, so nothing there or lower
    // is theirs to meet before a wheel's.
    const auto* wheel=std::get_if<Sphere>(&volume.primitive);
    if (!wheel || volume.body_contact_id>=4)
    {
        if (!(height>=lowest && along>-0.9f && along<0.9f)) return SmallEdge::None;
        for (const auto& corner:face.vertices) if (corner.y-volume.world_floor>SmallEdgeStep) return SmallEdge::None;
        return SmallEdge::Drop;
    }
    if (height<-SmallEdgeStep) return SmallEdge::None;
    if (along>=0.999f || along<=0.0f) return SmallEdge::None;
    if (std::fabs(Dot3(normal,face.feature.normal))>0.9999f)
    {
        float low=face.vertices[0].y,high=low;
        for (const auto& corner:face.vertices) {low=std::min(low,corner.y);high=std::max(high,corner.y);}
        if (high-low>SmallEdgeStep) return SmallEdge::None;
    }
    const float step=wheel->radius-Dot3(Subtract(wheel->center,pair.b),up);
    if (step>SmallEdgeStep) return SmallEdge::None;
    const auto across=Subtract(normal,Scale(up,along));
    if (Dot3(across,volume.linear_velocity)>=0.0f) return SmallEdge::None;
    // The wheel stands on the edge's height right under its centre, where a rolling wheel's surface is still: a point
    // ahead of it, where the edge is, moves along the normal as the wheel turns and would brake it.
    normal=up;pair.a=Subtract(wheel->center,Scale(up,wheel->radius));pair.b=Madd(up,step,pair.a);
    return SmallEdge::StepUp;
}
SmallEdge RideOverSmallEdge(const BoardWorldVolume& volume,const Triangle& face,ContactPair& pair,Vec3& normal)
{
    // A pushing foot slides over the edges the wheels roll over, rather than catching in a gap between planks, however
    // far down into the gap it reaches.
    if (volume.rider_floor) return RideOverSmallEdge(volume,face,Vec3{0,1,0},volume.world_floor,-RiderGapDepth,pair,normal);
    if (Dot3(volume.support_up,volume.support_up)<0.5f) return SmallEdge::None;
    // Along the world's up a board can lie wheels-up, so there only edges near the wheels' height count.
    const float unbounded=-std::numeric_limits<float>::infinity();
    const auto deck=RideOverSmallEdge(volume,face,volume.support_up,volume.support_floor,unbounded,pair,normal);
    return deck!=SmallEdge::None ? deck:RideOverSmallEdge(volume,face,Vec3{0,1,0},volume.world_floor,-SmallEdgeStep,pair,normal);
}
ContactRecord Seed(std::uint32_t id,ContactPair pair,Vec3 normal,ContactMaterial material,std::uint32_t tag)
{
    ContactRecord row{};const std::array<Vec3,3> vectors={pair.a,pair.b,normal};
    for (unsigned i=0;i<3;++i) {const auto v=vectors[i];row[4*i]=Word(v.x);row[4*i+1]=Word(v.y);row[4*i+2]=Word(v.z);}
    row[3]=id;row[7]=0xffffffffu;row[11]=Word(material.restitution);row[15]=Word(material.static_friction);row[19]=Word(material.dynamic_friction);row[23]=tag;return row;
}
}
const std::vector<ContactRecord>& WorldContactProducer::QueryPrimitives(const WorldGeometry& world,
    const std::vector<BoardWorldVolume>& volumes,WorldContactSettings query,ContactRetentionSettings retention)
{
    contacts_.clear();buffer_.count=0;buffer_.flushed=0;buffer_.dropped=0;buffer_.full=0;
    buffer_.capacity=retention.capacity;buffer_.distance_squared_threshold=retention.duplicate_distance_squared;buffer_.deferred_reduction=retention.deferred_reduction;
    const float padding=std::isfinite(query.volume_padding) && std::isfinite(query.maximum_separating_distance)
        ? VectorMax(query.volume_padding,0)+VectorMax(query.maximum_separating_distance,0):std::numeric_limits<float>::infinity();
    std::vector<std::optional<Bounds>> volume_bounds;std::vector<Vec3> cluster_points;bool complete=true;
    for (const auto& volume:volumes)
    {
        auto bounds=PrimitiveBounds(volume.primitive);if (bounds) bounds=ConservativeBounds(*bounds,padding+world.MaximumFatness());
        volume_bounds.push_back(bounds);
        if (bounds) {cluster_points.push_back(bounds->min);cluster_points.push_back(bounds->max);} else complete=false;
    }
    auto bounds=complete ? Bounds::FromPoints(cluster_points):std::nullopt;if (bounds) bounds=bounds->Expanded(padding);
    std::vector<std::size_t> candidates;
    for (auto range:world.CandidateRanges(bounds)) for (auto i=range.start;i<range.end;++i) candidates.push_back(i);
    const auto& triangles=world.Triangles();const auto& triangle_bounds=world.TriangleBounds();const char* error=nullptr;
    const bool metadata=world.Metadata(error)!=nullptr;
    ContactSink publish=[&](const ContactRecord* records,std::size_t count){contacts_.insert(contacts_.end(),records,records+count);};
    for (auto index:candidates)
    {
        const auto& entry=triangles[index];
        for (std::size_t i=0;i<volumes.size();++i)
        {
            const auto& volume=volumes[i];
            if (metadata && volume_bounds[i] && !triangle_bounds[index].Overlaps(*volume_bounds[i])) continue;
            const auto manifold=PrimitiveTriangleWorldContacts(volume.primitive,entry.triangle,volume.linear_velocity,query);if (!manifold) continue;
            const auto material=CombineContactMaterials(volume.material,entry.material);
            for (std::size_t point=0;point<manifold->count;++point)
            {
                const auto pair=manifold->points[point];
                const bool rejected=imported_floor_seams_ && ImportedInternalFloorEdge(index,entry,pair.b,manifold->normal,candidates,triangles,triangle_bounds);
                auto seeded=pair;auto normal=manifold->normal;
                if (rejected || (imported_floor_seams_ && RideOverSmallEdge(volume,entry.triangle,seeded,normal)==SmallEdge::Drop)) continue;
                const auto slot=buffer_.Allocate(publish);
                if (!slot) {buffer_.Flush(publish);return contacts_;}
                buffer_.records[*slot]=Seed(volume.body_contact_id,seeded,normal,material,entry.tag);
                if (buffer_.LastIsDuplicate()) --buffer_.count;
            }
        }
    }
    buffer_.Flush(publish);return contacts_;
}
}
