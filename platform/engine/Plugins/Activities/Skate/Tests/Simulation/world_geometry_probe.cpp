#include "WorldGeometry.h"
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace
{
[[noreturn]] void Fail(const char* message) { std::cerr<<message<<'\n';std::exit(2); }
struct Reader
{
    std::vector<std::uint8_t> bytes;
    std::size_t at=0;
    std::uint32_t Word()
    {
        if (bytes.size()-at<4) Fail("Truncated world geometry input");
        std::uint32_t word=0;
        for (unsigned i=0;i<4;++i) word|=std::uint32_t(bytes[at++])<<(i*8);
        return word;
    }
    float Scalar() { const auto word=Word(); float value; std::memcpy(&value,&word,4); return value; }
    Vec3 Vector() { return {Scalar(),Scalar(),Scalar()}; }
    Bounds Box() { return {Vector(),Vector()}; }
    AffineTransform Transform()
    {
        AffineTransform transform;
        for (auto& column:transform.basis.columns) for (float& lane:column) lane=Scalar();
        transform.translation=Vector(); return transform;
    }
};
struct Writer
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t value) { words.push_back(value); }
    void Scalar(float value) { std::uint32_t word; std::memcpy(&word,&value,4); Word(word); }
    void Vector(Vec3 value) { Scalar(value.x); Scalar(value.y); Scalar(value.z); }
    void Box(Bounds value) { Vector(value.min); Vector(value.max); }
    void OptionalBox(std::optional<Bounds> value) { Word(value.has_value()); Box(value.value_or(Bounds{})); }
    void Error(const char* error)
    {
        const auto count=error ? std::strlen(error):0;
        Word(static_cast<std::uint32_t>(count));
        for (std::size_t i=0;i<count;++i) Word(static_cast<unsigned char>(error[i]));
    }
    void Transform(const AffineTransform& value)
    { for (const auto& column:value.basis.columns) for (float lane:column) Scalar(lane); Vector(value.translation); }
    void Triangle(const WorldTriangle& value)
    {
        for (Vec3 vertex:value.triangle.vertices) Vector(vertex);
        Vector(value.triangle.feature.normal);
        for (Vec3 edge:value.triangle.feature.edges) Vector(edge);
        Word(value.triangle.feature.flags);
        for (float cosine:value.triangle.feature.edge_cosines) Scalar(cosine);
        for (float length:value.triangle.edge_lengths) Scalar(length);
        Scalar(value.triangle.fatness); Scalar(value.material.static_friction);
        Scalar(value.material.dynamic_friction); Scalar(value.material.restitution); Word(value.tag);
    }
    void Metadata(const QueryMetadata& value)
    {
        Word(static_cast<std::uint32_t>(value.packed_surfaces.size()));
        for (auto surface:value.packed_surfaces) Word(surface);
        Word(static_cast<std::uint32_t>(value.meshes.size()));
        for (const auto& mesh:value.meshes)
        {
            Word(static_cast<std::uint32_t>(mesh.triangle_range.start)); Word(static_cast<std::uint32_t>(mesh.triangle_range.end));
            Transform(mesh.local_to_world); Transform(mesh.world_to_local); Box(mesh.local_bounds);
            Word(static_cast<std::uint32_t>(mesh.matching_group)); Word(mesh.rejection_flags); Word(mesh.geometry);
            Word(static_cast<std::uint32_t>(mesh.pool));
        }
        Word(static_cast<std::uint32_t>(value.static_edges.size()));
        for (const auto& edge:value.static_edges) { Vector(edge.start); Vector(edge.end); Box(edge.local_bounds); }
        Word(value.island_flags);
    }
    void Hit(WorldLineQueryResult value)
    {
        Error(value.error); Word(value.hit.has_value());
        const WorldLineHit hit=value.hit.value_or(WorldLineHit{});
        Word(hit.tag); Vector(hit.geometry.position); Vector(hit.geometry.normal); Scalar(hit.geometry.fraction);
        for (float lane:hit.geometry.volume_parameter) Scalar(lane);
    }
};
struct TriangleInput
{
    std::array<Vec3,3> vertices;
    float fatness;
    std::array<float,3> edge_cosines;
    std::uint32_t flags;
    ContactMaterial material;
    std::uint32_t tag;
};
TriangleInput ReadTriangle(Reader& reader)
{
    const std::array<Vec3,3> vertices={reader.Vector(),reader.Vector(),reader.Vector()};
    const float fatness=reader.Scalar();
    const std::array<float,3> cosines={reader.Scalar(),reader.Scalar(),reader.Scalar()};
    const auto flags=reader.Word();
    const ContactMaterial material{reader.Scalar(),reader.Scalar(),reader.Scalar()};
    return {vertices,fatness,cosines,flags,material,reader.Word()};
}
WorldTriangle Cached(const TriangleInput& input)
{ return {TriangleFromVolume(input.vertices,input.fatness,input.edge_cosines,input.flags),input.material,input.tag}; }
QueryMetadata Metadata(Reader& reader)
{
    QueryMetadata metadata;
    const auto surfaces=reader.Word();
    for (std::uint32_t i=0;i<surfaces;++i) metadata.packed_surfaces.push_back(static_cast<std::uint16_t>(reader.Word()));
    const auto meshes=reader.Word();
    for (std::uint32_t i=0;i<meshes;++i)
    {
        QueryMesh mesh;
        mesh.triangle_range={reader.Word(),reader.Word()};
        mesh.local_to_world=reader.Transform(); mesh.world_to_local=reader.Transform(); mesh.local_bounds=reader.Box();
        mesh.matching_group=static_cast<std::int32_t>(reader.Word()); mesh.rejection_flags=reader.Word(); mesh.geometry=reader.Word();
        mesh.pool=static_cast<QueryPool>(reader.Word()); metadata.meshes.push_back(mesh);
    }
    const auto edges=reader.Word();
    for (std::uint32_t i=0;i<edges;++i) metadata.static_edges.push_back({reader.Vector(),reader.Vector(),reader.Box()});
    metadata.island_flags=reader.Word(); return metadata;
}
struct Query { Vec3 start,end; float radius; std::optional<Bounds> bounds; };
void Word(std::uint32_t value) { for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(value>>(i*8))); }
}
int main()
{
    {
        Reader reader; reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});
        const auto cases=reader.Word();
        for (std::uint32_t index=0;index<cases;++index)
        {
            const auto operation=reader.Word(); Writer out;
            if (operation==0)
            {
                const auto input=ReadTriangle(reader);
                const auto result=WorldTriangle::FromVertices(input.vertices,input.material,input.tag,input.flags,input.edge_cosines,input.fatness);
                out.Word(result.has_value()); out.Triangle(result.value_or(WorldTriangle{}));
            }
            else if (operation==1)
            {
                std::vector<Vec3> points; const auto count=reader.Word();
                for (std::uint32_t i=0;i<count;++i) points.push_back(reader.Vector());
                const float padding=reader.Scalar(); const Bounds other=reader.Box();
                const auto bounds=Bounds::FromPoints(points);
                out.OptionalBox(bounds); out.Box(bounds ? bounds->Expanded(padding):Bounds{});
                out.Word(bounds && bounds->Overlaps(other));
            }
            else if (operation==2)
            {
                std::vector<WorldTriangle> triangles; const auto count=reader.Word();
                for (std::uint32_t i=0;i<count;++i) triangles.push_back(Cached(ReadTriangle(reader)));
                const bool with_metadata=reader.Word()!=0; auto metadata=Metadata(reader);
                const auto query_count=reader.Word(); std::vector<Query> queries;
                for (std::uint32_t i=0;i<query_count;++i)
                {
                    Query query{reader.Vector(),reader.Vector(),reader.Scalar(),std::nullopt};
                    const bool has_bounds=reader.Word()!=0; const Bounds bounds=reader.Box();
                    if (has_bounds) query.bounds=bounds;
                    queries.push_back(query);
                }
                const char* error=nullptr;
                auto world=with_metadata ? WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error)
                                         : std::optional<WorldGeometry>(WorldGeometry(std::move(triangles)));
                out.Error(error);
                if (world)
                {
                    out.Word(static_cast<std::uint32_t>(world->Triangles().size()));
                    for (const auto& entry:world->Triangles()) out.Triangle(entry);
                    const auto stored=world->Metadata(error); out.Error(error); out.Word(stored!=nullptr);
                    if (stored) out.Metadata(*stored);
                    out.Word(query_count);
                    for (const Query& query:queries)
                    {
                        out.OptionalBox(world->LineCandidateBounds(query.start,query.end,query.radius));
                        const auto ranges=world->CandidateRanges(query.bounds); out.Word(static_cast<std::uint32_t>(ranges.size()));
                        for (auto range:ranges) { out.Word(static_cast<std::uint32_t>(range.start)); out.Word(static_cast<std::uint32_t>(range.end)); }
                        const auto candidates=world->LineCandidates(query.start,query.end,query.radius); out.Word(static_cast<std::uint32_t>(candidates.size()));
                        for (auto candidate:candidates) out.Word(static_cast<std::uint32_t>(candidate));
                        const auto meshes=world->CandidateMeshIndices(query.bounds); out.Error(meshes.error); out.Word(static_cast<std::uint32_t>(meshes.indices.size()));
                        for (auto mesh:meshes.indices) out.Word(static_cast<std::uint32_t>(mesh));
                        out.Hit(world->QueryThinLine(query.start,query.end)); out.Hit(world->QuerySweptLine(query.start,query.end,query.radius));
                    }
                }
            }
            else Fail("Invalid world geometry operation");
            Word(index); Word(operation); Word(static_cast<std::uint32_t>(out.words.size()));
            for (auto word:out.words) Word(word);
        }
        if (reader.at!=reader.bytes.size()) Fail("Trailing world geometry input");
    }
}
