#pragma once
#include "GeometryTypes.h"
#include <functional>
#include <optional>

namespace atelier::skate
{
using ContactRecord=std::array<std::uint32_t,64>;
using ContactSink=std::function<void(const ContactRecord*,std::size_t)>;
ContactMaterial CombineContactMaterials(ContactMaterial a,ContactMaterial b);
bool CoplanarContacts(const ContactRecord& a,const ContactRecord& b);
std::size_t SelectContactPoints(const Vec3* a,const Vec3* b,std::size_t count,Vec3 normal,
                                std::array<std::uint32_t,4>& output);
struct ContactBuffer
{
    std::uint32_t count=0,flushed=0,capacity=0,dropped=0;
    float distance_squared_threshold=0;
    std::uint8_t allow_flush=1,deferred_reduction=0,full=0;
    std::array<ContactRecord,50> records{};
    std::optional<std::size_t> Allocate(const ContactSink& sink);
    bool LastIsDuplicate();
    void Reduce();
    void Flush(const ContactSink& sink);
};
}
