#pragma once
#include "Intents.h"
#include <cstddef>
#include <string>

namespace atelier::skate
{
enum class GestureGroup : std::uint32_t { Square, Nose, Tail, Nose90, Tail90, NoseN90, TailN90 };
bool ParseGestureGroup(std::string_view name,GestureGroup& output,std::string& error);
bool HasGestureIntent(GestureGroup,const IntentMap&);
struct GestureMappingRow
{
    std::string_view key, normal, mirrored;
    std::uint32_t dark_catch;
};
struct GestureMappingView { const GestureMappingRow* data; std::size_t size; };
GestureMappingView GestureMappingRows(GestureGroup);
std::optional<std::string_view> SelectGestureTrick(GestureGroup,const IntentMap& action,bool mirrored);
struct GestureTrickState
{
    bool first_update = true;
    std::optional<std::string> selected;
    std::optional<std::string_view> successor;
    void Begin(GestureGroup,std::optional<std::string_view> override_name,const IntentMap& action,IntentMap& motion,bool mirrored);
    void Update(IntentMap& motion);
    void End(IntentMap& motion) const;
};
}
