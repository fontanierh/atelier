// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ScoringCore.h"
#include <string_view>
#include <utility>
namespace atelier::skate
{
struct ScoringCatalogEntry
{
    std::string_view identifier;
    std::uint32_t category;
    std::size_t score_type;
};
struct ScoringCollectorField
{
    std::uint16_t offset;
    std::string_view name;
    std::size_t byte_count;
};
extern const std::array<ScoringCatalogEntry,ScorableCount> ScoringCatalog;
extern const std::array<std::pair<std::int32_t,std::int32_t>,ScorableCount> ScoringConversionLinks;
extern const std::array<ScoringCollectorField,62> ScoringCollectorFields;
}
