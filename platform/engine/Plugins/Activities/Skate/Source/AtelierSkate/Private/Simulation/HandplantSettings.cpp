#include "HandplantSettings.h"
#include "PlantMath.h"
#include "StockSettingsReader.h"
namespace atelier::skate {
bool HandplantSettings::Load(const SettingsDatabase &data, std::string &error) {
  StockSettingsReader reader(data);
  HandplantSettings value;
  std::vector<std::uint32_t> words;
  const auto graph4 = [&](std::string_view category, std::string_view name,
                          PointGraph<4> &graph) {
    if (!reader.Words(category, "default", name, 12, words, error))
      return false;
    for (std::size_t i = 0; i < 4; ++i) {
      graph.x[i] = plant_math::Float(words[4 + i]);
      graph.y[i] = plant_math::Float(words[8 + i]);
    }
    return true;
  };
  const auto graph8 = [&](std::string_view name, PointGraph<8> &graph) {
    if (!reader.Words("physics_handplantmanager", "default", name, 20, words,
                      error))
      return false;
    for (std::size_t i = 0; i < 8; ++i) {
      graph.x[i] = plant_math::Float(words[4 + i]);
      graph.y[i] = plant_math::Float(words[12 + i]);
    }
    return true;
  };
  const auto number = [&](std::string_view name, float &output) {
    return reader.Float("physics_handplantmanager", "default", name, output,
                        error);
  };
  constexpr std::string_view root = "Hash_55B5940075F78842";
  constexpr std::array<std::string_view, 7> names{
      {"Hash_FF0DE8A42210E8C0", "Hash_B90C78786ED04A7D",
       "Hash_DC7947C6DD03CDAA", "Hash_0ACB7AAE2662FBB2",
       "Hash_CF7F668AB995380D", "Hash_8348DA199CC87B7A",
       "Hash_F27F622CAE33BD50"}};
  // Keep constructor field order, including early truck-distance lookup.
  if (!reader.Float("physics_grinds", "default", "DeckCenterToTruck",
                    value.truck_distance, error))
    return false;
  for (std::size_t i = 0; i < 7; ++i)
    if (!graph4(root, names[i], value.window[i]))
      return false;
  if (!reader.Float(root, "default", "Hash_3D9138A04C6D43F6", value.depth,
                    error) ||
      !reader.Float(root, "default", "Hash_A046D0516C0BD62B", value.window_drop,
                    error) ||
      !graph8("Hash_F551DF3289124FB0", value.time_warp) ||
      !graph8("Hash_8FC9A4F9002CF9E0", value.out_heading) ||
      !graph8("Hash_F61B0FB73C39311B", value.into_rotation) ||
      !graph8("Hash_D4EF764AF4D5F1CA", value.out_rotation) ||
      !graph4("physics_handplantmanager", "Hash_5494E3F9BE572D6B",
              value.hand_radius) ||
      !number("Hash_2460D6544C3B64B7", value.curve_half_time) ||
      !number("Hash_CCD7A82CE1BBFFF2", value.entry_blend) ||
      !number("Hash_E0895C189D77CE16", value.hand_out) ||
      !number("Hash_01EB855A0ACBD84C", value.hand_into) ||
      !number("Hash_9C02B9E6998D1321", value.hand_release) ||
      !number("Hash_63303CA6C611DC79", value.minimum_speed) ||
      !number("Hash_D1622917F6DD215F", value.minimum_slope) ||
      !number("Hash_D595A32C5F02178F", value.rotation_time) ||
      !number("Hash_B5EC5A0941B407A4", value.committed_time) ||
      !number("Hash_49C91803479B9BED", value.minimum_out_speed) ||
      !number("Hash_7C8B87F7435221C4", value.hand_approach) ||
      !reader.Words("physics_handplantmanager", "default",
                    "Hash_DDE5BFBCB6A1AFD5", 1, words, error))
    return false;
  std::memcpy(&value.direction_frames, &words[0], 4);
  if (!number("Hash_A046D0516C0BD62B", value.apex_radius) ||
      !number("Hash_90CDD541098AB4B5", value.apex_angle))
    return false;
  constexpr std::array<std::string_view, 3> animation{
      {"Hash_B9012B86EB5258FE", "Hash_512342FB1D4A7D57",
       "Hash_673F3B1BD056C39E"}};
  for (std::size_t i = 0; i < 3; ++i)
    if (!reader.Float("anim_handplant", "default", animation[i],
                      value.animation[i], error))
      return false;
  *this = std::move(value);
  error.clear();
  return true;
}
} // namespace atelier::skate
