// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AssemblyContacts.h"
namespace atelier::skate
{
struct NetworkBodyPose {Vec3 position;Quat orientation;};
struct NetworkBody {NetworkBodyPose pose;Vec3 velocity,angular;};
struct NetworkBodyState {NetworkBodyPose root;std::uint64_t enabled=0;std::vector<NetworkBody> bodies;};
struct NetworkCollisionSchema
{
    std::vector<std::pair<std::size_t,BoardWorldVolume>> volumes;
    // Full host capture and format/hash construction own this identity. This
    // physical boundary retains the supplied value without regenerating it.
    std::uint64_t fingerprint=0;
    static NetworkCollisionSchema FromWorldVolumes(const std::vector<BoardWorldVolume>&,
        const std::array<BodySnapshot,7>& board,const std::array<BodySnapshot,26>& skeleton,
        std::uint64_t fingerprint);
};
struct NetworkProxyContext
{
    const std::array<BodySnapshot,7>& board;
    const std::array<BodySnapshot,26>& skeleton;
    const std::array<BodyMassProperties,7>& board_masses;
    const SkeletonBodyDefinition& definition;
    std::size_t target_count;
};
struct NetworkProxies
{
    std::vector<BodySnapshot> bodies;
    std::vector<BoardWorldVolume> volumes;
    void Append(const NetworkBodyState&,const NetworkCollisionSchema&,const NetworkProxyContext&,float age);
};
std::pair<Vec3,float> RemotePrimitiveBounds(const ContactPrimitive&);
// Board volumes precede rider volumes; every admitted remote pair uses the
// original narrow phase, with no local assembly culling or owner suppression.
std::size_t AppendRemoteContacts(std::vector<BoardCollision>& contacts,
    const std::vector<BoardWorldVolume>& board,const std::vector<BoardWorldVolume>& rider,
    const std::vector<BoardWorldVolume>& remote);
}
