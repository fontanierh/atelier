#include "FootplantSettings.h"
#include "PlantMath.h"
#include "StockSettingsReader.h"
namespace atelier::skate {
bool FootplantSettings::Load(const SettingsDatabase &data, std::string &error) {
  FootplantSettings next;
  const StockSettingsReader read(data);
  constexpr std::string_view category = "physics_footplantmanager";
  if (!read.Curve8Layout20(category, "default", "Hash_8A8887218466ED15",
                           next.radial_speed_scale, error))
    return false;
  std::vector<std::uint32_t> words;
  if (!read.Words(category, "default", "DeckBB", 4, words, error))
    return false;
  for (std::size_t i = 0; i < 4; ++i)
    next.deck_bounds[i] = plant_math::Float(words[i]);
  const auto scalar = [&](std::string_view name, float &out) {
    return read.Float(category, "default", name, out, error);
  };
  if (!scalar("MaxLegAngleError", next.max_leg_angle_error) ||
      !scalar("LegLengthOnLanding", next.leg_length_on_landing) ||
      !scalar("FootVolumeYOffset", next.foot_volume_y_offset) ||
      !scalar("DeckBBYOffset", next.deck_bounds_y_offset) ||
      !scalar("Hash_149A5D0D4768D2B1", next.max_horizontal_speed) ||
      !scalar("Hash_52436D9F4FE56BCB", next.max_descending_speed) ||
      !scalar("Hash_C5F92168DFAFD0B8", next.release_outward_speed) ||
      !scalar("Hash_628C228DCC7B6ED5", next.end_handle) ||
      !scalar("Hash_4F45DA86685CF029", next.end_angle) ||
      !scalar("Hash_0DE0027B9913C5D5", next.end_leg_length) ||
      !scalar("Hash_5C4341EF35F4B2B0", next.start_handle) ||
      !scalar("Hash_D6224B710A36D643", next.min_duration) ||
      !scalar("Hash_68C05A7FCC6BB718", next.max_duration))
    return false;
  *this = std::move(next);
  error.clear();
  return true;
}
} // namespace atelier::skate
