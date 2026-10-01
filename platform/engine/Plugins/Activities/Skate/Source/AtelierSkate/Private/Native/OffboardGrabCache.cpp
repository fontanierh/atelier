// SPDX-License-Identifier: Apache-2.0
#include "OffboardGrabCache.h"
namespace atelier::skate
{
void OffboardGrabCache::Invalidate()
{
    // Original82D749D0 preserves record payloads, requested descriptors,
    // interactable batches/completions and both captured positions.
    queries.clear();
    query_result.reset();
    validation.reset();
    data_ready={false,false};
    flags_12836&=0x3f;
}
void OffboardGrabCache::EnterReset()
{
    Invalidate();
    interactable_result.reset();
}
}
