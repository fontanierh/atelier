// SPDX-License-Identifier: Apache-2.0
#include "WorldContactProducer.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace
{
[[noreturn]] void Fail(const char* message) {std::cerr<<message<<'\n';std::exit(2);}
struct Reader
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word() {if (bytes.size()-at<4) Fail("Truncated world contact input");std::uint32_t v=0;for (unsigned i=0;i<4;++i) v|=std::uint32_t(bytes[at++])<<(8*i);return v;}
    float Scalar() {const auto bits=Word();float v;std::memcpy(&v,&bits,4);return v;}
    Vec3 Vector() {return {Scalar(),Scalar(),Scalar()};}
    Basis3 Basis() {Basis3 b;for (auto& c:b.columns) for (auto& v:c) v=Scalar();return b;}
    ContactMaterial Material() {return {Scalar(),Scalar(),Scalar()};}
    Triangle ReadTriangle(bool transformed)
    {
        const std::array<Vec3,3> v={Vector(),Vector(),Vector()};const float fat=Scalar();const std::array<float,3> cos={Scalar(),Scalar(),Scalar()};const auto flags=Word();
        return transformed ? TransformTriangleVolume(v,fat,cos,flags,{Basis(),Vector()}):TriangleFromVolume(v,fat,cos,flags);
    }
    ContactPrimitive Primitive()
    {
        switch (Word())
        {
        case 0:return Sphere{Vector(),Scalar()};case 1:return Capsule{Vector(),Vector(),Scalar(),Scalar()};
        case 2:return ReadTriangle(true);case 3:return RoundedBox{Vector(),Basis(),Vector(),Scalar()};default:Fail("Invalid world contact primitive");
        }
    }
    QueryMetadata Metadata()
    {
        QueryMetadata metadata;const auto n=Word();for (std::uint32_t i=0;i<n;++i) metadata.packed_surfaces.push_back(static_cast<std::uint16_t>(Word()));
        const auto meshes=Word();for (std::uint32_t i=0;i<meshes;++i)
        {
            QueryMesh mesh;mesh.triangle_range={Word(),Word()};mesh.local_bounds={Vector(),Vector()};mesh.matching_group=static_cast<std::int32_t>(Word());
            mesh.rejection_flags=Word();mesh.geometry=Word();mesh.pool=static_cast<QueryPool>(Word());metadata.meshes.push_back(mesh);
        }
        metadata.island_flags=Word();return metadata;
    }
};
void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(v>>(8*i)));}
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto cases=reader.Word();
    for (std::uint32_t index=0;index<cases;++index)
    {
        std::vector<WorldTriangle> triangles;const auto triangle_count=reader.Word();
        for (std::uint32_t i=0;i<triangle_count;++i) {const auto triangle=reader.ReadTriangle(false);const auto material=reader.Material();triangles.push_back({triangle,material,reader.Word()});}
        const bool authored=reader.Word()!=0;const auto metadata=reader.Metadata();const bool seams=reader.Word()!=0;
        const char* error=nullptr;auto world=authored ? WorldGeometry::WithQueryMetadata(std::move(triangles),metadata,error):std::optional<WorldGeometry>{WorldGeometry{std::move(triangles)}};
        if (!world) Fail(error ? error:"Invalid contact world");WorldContactProducer producer;if (seams) producer.EnableImportedFloorSeams();
        const auto frames=reader.Word();std::vector<std::uint32_t> output{frames};
        for (std::uint32_t frame=0;frame<frames;++frame)
        {
            std::vector<BoardWorldVolume> volumes;const auto n=reader.Word();
            for (std::uint32_t i=0;i<n;++i)
            {const auto id=reader.Word();const auto primitive=reader.Primitive();const auto velocity=reader.Vector();volumes.push_back({id,primitive,velocity,reader.Material()});}
            const WorldContactSettings query{reader.Scalar(),reader.Scalar(),reader.Scalar(),reader.Scalar(),reader.Word()!=0};
            const ContactRetentionSettings retention{reader.Word(),reader.Scalar(),reader.Word()!=0};const auto& contacts=producer.QueryPrimitives(*world,volumes,query,retention);
            output.push_back(producer.DroppedContacts());output.push_back(static_cast<std::uint32_t>(contacts.size()));for (const auto& row:contacts) output.insert(output.end(),row.begin(),row.end());
        }
        Word(index);Word(static_cast<std::uint32_t>(output.size()));for (auto v:output) Word(v);
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing world contact input");
}
