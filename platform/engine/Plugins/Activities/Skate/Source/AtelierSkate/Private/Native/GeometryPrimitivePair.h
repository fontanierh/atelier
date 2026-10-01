// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "WorldPrimitiveContact.h"
namespace atelier::skate
{
struct PrimitivePairSettings
{
    float padding_a=0,padding_b=0,additional_padding=0;
    float edge_cos_bend_normal_threshold=0,convexity_epsilon=0;
    static PrimitivePairSettings SkaterSelfCollision();
};
// Original simulation GP-pair query: A/B point ownership and ordered features
// survive padding contacts. The published normal faces from B toward A.
std::optional<PrimitiveContactManifold> PrimitivePairContacts(const ContactPrimitive& a,
    const ContactPrimitive& b,PrimitivePairSettings settings);
}
