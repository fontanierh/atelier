// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonBody.h"
#include <optional>
namespace atelier::skate
{
struct WipeoutMaterialTenResponse
{
    Vec4 previous_velocity{},normal{0,1,0,0},target_velocity{};
    float time=0;std::uint32_t phase=0;bool finished=false;
    void Reset(){*this=WipeoutMaterialTenResponse{};}
    void Update(SkeletonBody&,Vec4 velocity,std::optional<Vec4> contact);
private:void Select(bool contact);
};
struct WipeoutMaterialElevenResponse
{
    Vec4 normal{0,1,0,0},previous_velocity{},velocity{};
    std::int32_t frames_since_contact=100,active_frames=0;
    bool contact_latched=false,active=false;
    void Reset(){const bool retained=active;*this=WipeoutMaterialElevenResponse{};active=retained;}
    void Update(SkeletonBody&,Vec4 com_velocity,std::optional<Vec4> contact,Vec4 effective_axis,std::array<float,2> controls);
private:
    void ApplyResponse(SkeletonBody&) const;
    void ApplyControl(SkeletonBody&,Vec4 effective_axis,std::array<float,2> controls) const;
};
struct WipeoutContactResponse
{
    WipeoutMaterialTenResponse material10;
    WipeoutMaterialElevenResponse material11;
    void Reset(){material10.Reset();material11.Reset();}
};
}
