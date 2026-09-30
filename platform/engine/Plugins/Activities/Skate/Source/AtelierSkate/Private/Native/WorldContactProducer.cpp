// SPDX-License-Identifier: Apache-2.0
#include "WorldContactProducer.h"
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
                if (imported_floor_seams_ && ImportedInternalFloorEdge(index,entry,pair.b,manifold->normal,candidates,triangles,triangle_bounds)) continue;
                const auto slot=buffer_.Allocate(publish);
                if (!slot) {buffer_.Flush(publish);return contacts_;}
                buffer_.records[*slot]=Seed(volume.body_contact_id,pair,manifold->normal,material,entry.tag);
                if (buffer_.LastIsDuplicate()) --buffer_.count;
            }
        }
    }
    buffer_.Flush(publish);return contacts_;
}
}
