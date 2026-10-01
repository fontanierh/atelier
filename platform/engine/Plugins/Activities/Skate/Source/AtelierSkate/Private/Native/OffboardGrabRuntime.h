// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardGrabScene.h"
#include "OffboardGroundGeometry.h"
namespace atelier::skate
{
struct OffboardGrabPublication
{
    std::array<std::optional<OffboardGrabRecord>,2> records;
    std::optional<std::optional<std::uint32_t>> object;
};
class OffboardGrabRuntime
{
public:
    explicit OffboardGrabRuntime(OffboardGrabCache& cache):cache_(cache){}
    void Query(OffboardGrabQuery);
    void RequestPrimary(OffboardGrabDescriptor);
    void RequestInteractable(Mat4,OffboardGroundContext);
    bool ExecuteQueries(const OffboardGrabScene&,std::string& error);
    bool Sync(const OffboardGrabScene&,OffboardGroundContext,std::string& error);
    std::optional<OffboardGrabRecord> Best(Vec4 position) const{return BestGrabSpline(cache_.validated,position);}
    void Invalidate(){cache_.Invalidate();}
    void EnterReset(){cache_.EnterReset();}
    OffboardGrabPublication Publish();
    const OffboardGrabCache& Cache() const{return cache_;}
private:
    OffboardGrabCache& cache_;
};
}
