// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardRuntime.h"
#include "SkeletonBodyDefinition.h"
#include "SkeletonPhysicalRecord.h"
namespace atelier::skate
{
class SkeletonBody
{
public:
    SkeletonBodyDefinition definition;
    SkeletonPhysicalRecord record;
    Mat4 animation_to_world;
    SkeletonBody(SkeletonBodyDefinition definition,
        const std::array<Mat4,SkeletonAnimationPartCount>& authored,Mat4 spawn,SimulationStep simulation);
    const std::array<BodySnapshot,SkeletonPartCount>& Bodies() const {return bodies_;}
    std::array<BodySnapshot,SkeletonPartCount>& BodiesMut(){return bodies_;}
    void SetPartTransform(std::size_t part,Mat4 frame);
    std::array<Mat4,SkeletonPartCount> PartTransforms() const;
    void PublishPhysicalRecord(Mat4 board);
    void ApplyPartDisplacement(std::size_t part,Vec4 displacement);
private:
    std::array<BodySnapshot,SkeletonPartCount> bodies_;
};
}
