// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "WorldGeometry.h"
#include "WorldPrimitiveContact.h"
#include "ContactRetention.h"

namespace atelier::skate
{
struct ContactRetentionSettings
{
    std::uint32_t capacity=0;
    float duplicate_distance_squared=0;
    bool deferred_reduction=false;
};
struct BoardWorldVolume
{
    // Board body IDs 0..6, attached body IDs index+8; static world is UINT32_MAX.
    std::uint32_t body_contact_id=0;
    ContactPrimitive primitive{};
    Vec3 linear_velocity{};
    ContactMaterial material{};
};
class WorldContactProducer
{
public:
    void EnableImportedFloorSeams() { imported_floor_seams_=true; }
    // Published seeds retain world-triangle then moving-volume order. Body
    // workspaces remain zero for enrichment after the frame's force queue.
    const std::vector<ContactRecord>& QueryPrimitives(const WorldGeometry& world,
        const std::vector<BoardWorldVolume>& volumes,WorldContactSettings query,ContactRetentionSettings retention);
    const std::vector<ContactRecord>& Contacts() const { return contacts_; }
    std::uint32_t DroppedContacts() const { return buffer_.dropped; }
private:
    bool imported_floor_seams_=false;
    std::vector<ContactRecord> contacts_;
    ContactBuffer buffer_;
};
}
