// SPDX-License-Identifier: Apache-2.0
#include "OffboardGrabMath.h"
namespace atelier::skate
{
std::optional<OffboardGrabRegistry> OffboardGrabRegistry::Create(const WorldGeometry& world,std::vector<GrabObject> objects,std::vector<GrabMeshAssembly> bindings,std::string& error)
{
    const char* diagnostic=nullptr;const auto metadata=world.Metadata(diagnostic);if(!metadata){error=diagnostic;return std::nullopt;}
    for(std::size_t n=0;n<objects.size();++n)
    {
        const auto& object=objects[n];if(object.id==0){error="Interactable object ID zero is reserved for none";return std::nullopt;}if(object.provider==GrabProvider::Dmo&&object.selection_variant>1){error="Dmo body selection is a single bit";return std::nullopt;}
        for(const auto& spline:object.splines){if(spline.descriptor.kind!=1&&spline.descriptor.kind!=2){error="Unknown native grab descriptor kind";return std::nullopt;}OffboardGrabRecord r;if(!object.Record(spline,r,error))return std::nullopt;}
        for(std::size_t prior=0;prior<n;++prior)if(objects[prior].id==object.id){error="Duplicate authored interactable object ID";return std::nullopt;}
    }
    for(std::size_t n=0;n<bindings.size();++n)
    {
        bool found=false;for(const auto& m:metadata->meshes)found|=m.geometry==bindings[n].mesh;if(bindings[n].assembly==0||!found){error="Grab collision binding must name an existing mesh and nonzero physical assembly";return std::nullopt;}
        for(std::size_t prior=0;prior<n;++prior)if(bindings[prior].mesh==bindings[n].mesh){error="One canonical collision mesh cannot name two assemblies";return std::nullopt;}
    }
    OffboardGrabRegistry registry;registry.objects=std::move(objects);registry.bindings_=std::move(bindings);error.clear();return registry;
}
std::optional<std::uint32_t> OffboardGrabRegistry::Assembly(std::uint32_t mesh) const
{for(const auto& b:bindings_)if(b.mesh==mesh)return b.assembly;return std::nullopt;}
std::optional<std::uint32_t> OffboardGrabRegistry::EligibleObject(OffboardGrabHit hit) const
{if(hit.fraction==0||!hit.assembly)return std::nullopt;for(const auto& o:objects)if(!o.disabled&&o.assembly&&o.assembly->identity==*hit.assembly)return o.id;return std::nullopt;}
bool OffboardGrabScene::Resolve(OffboardGrabDescriptor descriptor,std::optional<OffboardGrabRecord>& output,std::string& error) const
{output.reset();if(descriptor.kind!=1&&descriptor.kind!=2){error.clear();return true;}for(const auto& object:registry_->objects)for(const auto& spline:object.splines)if(offboard_grab_math::Same(spline.descriptor,descriptor)){OffboardGrabRecord r;if(!object.Record(spline,r,error))return false;output=std::move(r);error.clear();return true;}error.clear();return true;}
}
