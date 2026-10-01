// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardPhysicsSettings.h"
#include "WorldContactProducer.h"

namespace atelier::skate
{
std::vector<BoardWorldVolume> BoardWorldVolumes(const BoardRuntime&,const BoardCollisionSettings&);
class BoardWorldContacts
{
public:
    void EnableImportedFloorSeams(){producer_.EnableImportedFloorSeams();}
    const std::vector<BoardCollision>& Query(const WorldGeometry&,const std::vector<BoardWorldVolume>&,
        WorldContactSettings,ContactRetentionSettings);
    const std::vector<BoardCollision>& Contacts() const{return contacts_;}
    std::uint32_t DroppedContacts() const{return producer_.DroppedContacts();}
private:
    WorldContactProducer producer_;
    std::vector<BoardCollision> contacts_;
};
}
