#pragma once
#include "OffboardGrabCache.h"
#include "WorldGeometry.h"
#include <string>
namespace atelier::skate
{
struct GrabRatesData{std::uint32_t identity;Vec4 vector_48,transform_position_48;};
struct GrabPartData{std::uint32_t identity;std::optional<GrabRatesData> rates;std::array<float,10> coefficients_0_to_36;};
struct GrabAssemblyData{std::uint32_t identity;std::optional<GrabPartData> first_part;};
struct GrabRecordInput
{
    OffboardGrabDescriptor descriptor;std::shared_ptr<const OffboardGrabGeometry> geometry;Mat4 frame;
    Vec4 object_vector_128;const GrabAssemblyData* assembly;std::uint32_t word_272;
};
enum class GrabProvider{Dmo,LivingWorld};
struct GrabSpline{OffboardGrabDescriptor descriptor;std::shared_ptr<const OffboardGrabGeometry> geometry;std::uint32_t word_272;};
struct GrabObject
{
    std::uint32_t id;GrabProvider provider;std::uint8_t selection_variant;std::int32_t matching_group;bool record_enabled;
    bool disabled,assembly_ready;std::optional<GrabAssemblyData> assembly;Mat4 frame;Vec4 object_vector_128;std::vector<GrabSpline> splines;
    bool Record(const GrabSpline&,OffboardGrabRecord&,std::string& error) const;
};
struct GrabMeshAssembly{std::uint32_t mesh,assembly;};
bool BuildGrabRecord(GrabRecordInput,OffboardGrabRecord&,std::string& error);
OffboardGrabDescriptor GrabRecordDescriptor(const OffboardGrabRecord&);
std::array<Vec4,2> GrabRecordEndpoints(const OffboardGrabRecord&);
std::optional<std::uint32_t> GrabRecordAssembly(const OffboardGrabRecord&);
bool GrabRecordValid(const OffboardGrabRecord&);
Vec4 GrabRecordVector(const OffboardGrabRecord&,std::size_t offset);
float GrabRecordScalar(const OffboardGrabRecord&,std::size_t offset);
void SetGrabRecordVector(OffboardGrabRecord&,std::size_t offset,Vec4);
Vec4 ClosestGrabPoint(Vec4 position,std::array<Vec4,2> endpoints);
bool QualifyGrabRecord(const OffboardGrabRecord&,Vec4 position,const Mat4& bounds_frame,Vec4 bounds_extents,float margin,float angle_a,float angle_b);
std::optional<OffboardGrabRecord> BestGrabSpline(const std::vector<OffboardGrabRecord>&,Vec4 position);
class OffboardGrabRegistry
{
public:
    std::vector<GrabObject> objects;
    static std::optional<OffboardGrabRegistry> Create(const WorldGeometry&,std::vector<GrabObject>,std::vector<GrabMeshAssembly>,std::string& error);
    std::optional<std::uint32_t> Assembly(std::uint32_t mesh) const;
    std::optional<std::uint32_t> EligibleObject(OffboardGrabHit) const;
    const std::vector<GrabMeshAssembly>& Bindings() const{return bindings_;}
private:
    std::vector<GrabMeshAssembly> bindings_;
};
// Each operation borrows the current world and actual authored registry. The
// retained cache never keeps this scene through a terrain/provider replacement.
class OffboardGrabScene
{
public:
    OffboardGrabScene(const WorldGeometry& world,const OffboardGrabRegistry& registry):world_(&world),registry_(&registry){}
    bool Query(const OffboardGrabQuery&,std::vector<OffboardGrabRecord>&,std::string& error) const;
    bool Resolve(OffboardGrabDescriptor,std::optional<OffboardGrabRecord>&,std::string& error) const;
    bool Line(OffboardGrabLine,std::optional<OffboardGrabHit>&,std::string& error) const;
    std::optional<std::uint32_t> EligibleObject(OffboardGrabHit hit) const{return registry_->EligibleObject(hit);}
private:
    const WorldGeometry* world_;const OffboardGrabRegistry* registry_;
};
}
