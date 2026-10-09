#include "GraphGestureOperations.h"
#include <cassert>
#include <limits>

namespace atelier::skate
{
namespace
{
// Original gesture_mapping_data.rs: all 270 authored insertion rows, in order.
constexpr std::array<GestureMappingRow,30> mapping_0{{
    {"Ollie","Ollie","Ollie",1},
    {"PopShuvit","PopShuvit","FSPopShuvit",1},
    {"FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"VarialKickflip","VarialKickflip","VarialHeelflip",1},
    {"VarialHeelflip","VarialHeelflip","VarialKickflip",2},
    {"Hardflip","Hardflip","InwardHeelflip",1},
    {"InwardHeelflip","InwardHeelflip","Hardflip",2},
    {"360PopShuvit","360PopShuvit","FS360PopShuvit",1},
    {"FS360PopShuvit","FS360PopShuvit","360PopShuvit",2},
    {"360Flip","360Flip","Laserflip",0},
    {"Laserflip","Laserflip","360Flip",0},
    {"360Hardflip","360Hardflip","360InwardHeelflip",0},
    {"360InwardHeelflip","360InwardHeelflip","360Hardflip",0},
    {"Kickflip","Kickflip","Heelflip",0},
    {"Heelflip","Heelflip","Kickflip",0},
    {"Nollie","Nollie","Nollie",3},
    {"N_PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"N_FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"N_VarialKickflip","N_VarialKickflip","N_VarialHeelflip",3},
    {"N_VarialHeelflip","N_VarialHeelflip","N_VarialKickflip",4},
    {"N_Hardflip","N_Hardflip","N_InwardHeelflip",3},
    {"N_InwardHeelflip","N_InwardHeelflip","N_Hardflip",4},
    {"N_360PopShuvit","N_360PopShuvit","N_FS360PopShuvit",3},
    {"N_FS360PopShuvit","N_FS360PopShuvit","N_360PopShuvit",4},
    {"N_360Flip","N_360Flip","N_Laserflip",0},
    {"N_Laserflip","N_Laserflip","N_360Flip",0},
    {"N_360Hardflip","N_360Hardflip","N_360InwardHeelflip",0},
    {"N_360InwardHeelflip","N_360InwardHeelflip","N_360Hardflip",0},
    {"N_Kickflip","N_Kickflip","N_Heelflip",0},
    {"N_Heelflip","N_Heelflip","N_Kickflip",0},
}};
constexpr std::array<GestureMappingRow,30> mapping_1{{
    {"Nollie","Nollie","Nollie",3},
    {"N_PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"N_FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"N_VarialKickflip","N_VarialKickflip","N_VarialHeelflip",3},
    {"N_VarialHeelflip","N_VarialHeelflip","N_VarialKickflip",4},
    {"N_Hardflip","N_Hardflip","N_InwardHeelflip",3},
    {"N_InwardHeelflip","N_InwardHeelflip","N_Hardflip",4},
    {"N_360PopShuvit","N_360PopShuvit","N_FS360PopShuvit",3},
    {"N_FS360PopShuvit","N_FS360PopShuvit","N_360PopShuvit",4},
    {"N_360Flip","N_360Flip","N_Laserflip",0},
    {"N_Laserflip","N_Laserflip","N_360Flip",0},
    {"N_360Hardflip","N_360Hardflip","N_360InwardHeelflip",0},
    {"N_360InwardHeelflip","N_360InwardHeelflip","N_360Hardflip",0},
    {"N_Kickflip","N_Kickflip","N_Heelflip",0},
    {"N_Heelflip","N_Heelflip","N_Kickflip",0},
    {"Ollie","Nollie","Nollie",3},
    {"PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"VarialKickflip","Nollie","Nollie",3},
    {"VarialHeelflip","Nollie","Nollie",4},
    {"Hardflip","Nollie","Nollie",3},
    {"InwardHeelflip","Nollie","Nollie",4},
    {"360PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"FS360PopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"360Flip","Nollie","Nollie",3},
    {"Laserflip","Nollie","Nollie",4},
    {"360Hardflip","Nollie","Nollie",3},
    {"360InwardHeelflip","Nollie","Nollie",4},
    {"Kickflip","Nollie","Nollie",3},
    {"Heelflip","Nollie","Nollie",4},
}};
constexpr std::array<GestureMappingRow,30> mapping_2{{
    {"Ollie","Ollie","Ollie",1},
    {"PopShuvit","PopShuvit","FSPopShuvit",1},
    {"FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"VarialKickflip","VarialKickflip","VarialHeelflip",1},
    {"VarialHeelflip","VarialHeelflip","VarialKickflip",2},
    {"Hardflip","Hardflip","InwardHeelflip",1},
    {"InwardHeelflip","InwardHeelflip","Hardflip",2},
    {"360PopShuvit","360PopShuvit","FS360PopShuvit",1},
    {"FS360PopShuvit","FS360PopShuvit","360PopShuvit",2},
    {"360Flip","360Flip","Laserflip",0},
    {"Laserflip","Laserflip","360Flip",0},
    {"360Hardflip","360Hardflip","360InwardHeelflip",0},
    {"360InwardHeelflip","360InwardHeelflip","360Hardflip",0},
    {"Kickflip","Kickflip","Heelflip",0},
    {"Heelflip","Heelflip","Kickflip",0},
    {"Nollie","Ollie","Ollie",1},
    {"N_PopShuvit","PopShuvit","FSPopShuvit",1},
    {"N_FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"N_VarialKickflip","Ollie","Ollie",1},
    {"N_VarialHeelflip","Ollie","Ollie",2},
    {"N_Hardflip","Ollie","Ollie",1},
    {"N_InwardHeelflip","Ollie","Ollie",2},
    {"N_360PopShuvit","PopShuvit","FSPopShuvit",1},
    {"N_FS360PopShuvit","FSPopShuvit","PopShuvit",2},
    {"N_360Flip","Ollie","Ollie",1},
    {"N_Laserflip","Ollie","Ollie",2},
    {"N_360Hardflip","Ollie","Ollie",1},
    {"N_360InwardHeelflip","Ollie","Ollie",2},
    {"N_Kickflip","Ollie","Ollie",1},
    {"N_Heelflip","Ollie","Ollie",2},
}};
constexpr std::array<GestureMappingRow,45> mapping_3{{
    {"90_Nollie","Nollie","Nollie",3},
    {"90_N_PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"90_N_FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"90_N_VarialKickflip","N_VarialKickflip","N_VarialHeelflip",3},
    {"90_N_VarialHeelflip","N_VarialHeelflip","N_VarialKickflip",4},
    {"90_N_Hardflip","N_Hardflip","N_InwardHeelflip",3},
    {"90_N_InwardHeelflip","N_InwardHeelflip","N_Hardflip",4},
    {"90_N_360PopShuvit","N_360PopShuvit","N_FS360PopShuvit",3},
    {"90_N_FS360PopShuvit","N_FS360PopShuvit","N_360PopShuvit",4},
    {"90_N_360Flip","N_360Flip","N_Laserflip",0},
    {"90_N_Laserflip","N_Laserflip","N_360Flip",0},
    {"90_N_360Hardflip","N_360Hardflip","N_360InwardHeelflip",0},
    {"90_N_360InwardHeelflip","N_360InwardHeelflip","N_360Hardflip",0},
    {"90_N_Kickflip","N_Kickflip","N_Heelflip",0},
    {"90_N_Heelflip","N_Heelflip","N_Kickflip",0},
    {"Nollie","Nollie","Nollie",3},
    {"N_PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"N_FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"N_VarialKickflip","N_VarialKickflip","N_VarialHeelflip",3},
    {"N_VarialHeelflip","N_VarialHeelflip","N_VarialKickflip",4},
    {"N_Hardflip","N_Hardflip","N_InwardHeelflip",3},
    {"N_InwardHeelflip","N_InwardHeelflip","N_Hardflip",4},
    {"N_360PopShuvit","N_360PopShuvit","N_FS360PopShuvit",3},
    {"N_FS360PopShuvit","N_FS360PopShuvit","N_360PopShuvit",4},
    {"N_360Flip","N_360Flip","N_Laserflip",0},
    {"N_Laserflip","N_Laserflip","N_360Flip",0},
    {"N_360Hardflip","N_360Hardflip","N_360InwardHeelflip",0},
    {"N_360InwardHeelflip","N_360InwardHeelflip","N_360Hardflip",0},
    {"N_Kickflip","N_Kickflip","N_Heelflip",0},
    {"N_Heelflip","N_Heelflip","N_Kickflip",0},
    {"Ollie","Nollie","Nollie",3},
    {"PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"VarialKickflip","Nollie","Nollie",3},
    {"VarialHeelflip","Nollie","Nollie",4},
    {"Hardflip","Nollie","Nollie",3},
    {"InwardHeelflip","Nollie","Nollie",4},
    {"360PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"FS360PopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"360Flip","Nollie","Nollie",3},
    {"Laserflip","Nollie","Nollie",4},
    {"360Hardflip","Nollie","Nollie",3},
    {"360InwardHeelflip","Nollie","Nollie",4},
    {"Kickflip","Nollie","Nollie",3},
    {"Heelflip","Nollie","Nollie",4},
}};
constexpr std::array<GestureMappingRow,45> mapping_4{{
    {"90_Ollie","Ollie","Ollie",1},
    {"90_PopShuvit","PopShuvit","FSPopShuvit",1},
    {"90_FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"90_VarialKickflip","VarialKickflip","VarialHeelflip",1},
    {"90_VarialHeelflip","VarialHeelflip","VarialKickflip",2},
    {"90_Hardflip","Hardflip","InwardHeelflip",1},
    {"90_InwardHeelflip","InwardHeelflip","Hardflip",2},
    {"90_360PopShuvit","360PopShuvit","FS360PopShuvit",1},
    {"90_FS360PopShuvit","FS360PopShuvit","360PopShuvit",2},
    {"90_360Flip","360Flip","Laserflip",0},
    {"90_Laserflip","Laserflip","360Flip",0},
    {"90_360Hardflip","360Hardflip","360InwardHeelflip",0},
    {"90_360InwardHeelflip","360InwardHeelflip","360Hardflip",0},
    {"90_Kickflip","Kickflip","Heelflip",0},
    {"90_Heelflip","Heelflip","Kickflip",0},
    {"Ollie","Ollie","Ollie",1},
    {"PopShuvit","PopShuvit","FSPopShuvit",1},
    {"FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"VarialKickflip","VarialKickflip","VarialHeelflip",1},
    {"VarialHeelflip","VarialHeelflip","VarialKickflip",2},
    {"Hardflip","Hardflip","InwardHeelflip",1},
    {"InwardHeelflip","InwardHeelflip","Hardflip",2},
    {"360PopShuvit","360PopShuvit","FS360PopShuvit",1},
    {"FS360PopShuvit","FS360PopShuvit","360PopShuvit",2},
    {"360Flip","360Flip","Laserflip",0},
    {"Laserflip","Laserflip","360Flip",0},
    {"360Hardflip","360Hardflip","360InwardHeelflip",0},
    {"360InwardHeelflip","360InwardHeelflip","360Hardflip",0},
    {"Kickflip","Kickflip","Heelflip",0},
    {"Heelflip","Heelflip","Kickflip",0},
    {"Nollie","Ollie","Ollie",1},
    {"N_PopShuvit","PopShuvit","FSPopShuvit",1},
    {"N_FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"N_VarialKickflip","Ollie","Ollie",1},
    {"N_VarialHeelflip","Ollie","Ollie",2},
    {"N_Hardflip","Ollie","Ollie",1},
    {"N_InwardHeelflip","Ollie","Ollie",2},
    {"N_360PopShuvit","PopShuvit","FSPopShuvit",1},
    {"N_FS360PopShuvit","FSPopShuvit","PopShuvit",2},
    {"N_360Flip","Ollie","Ollie",1},
    {"N_Laserflip","Ollie","Ollie",2},
    {"N_360Hardflip","Ollie","Ollie",1},
    {"N_360InwardHeelflip","Ollie","Ollie",2},
    {"N_Kickflip","Ollie","Ollie",1},
    {"N_Heelflip","Ollie","Ollie",2},
}};
constexpr std::array<GestureMappingRow,45> mapping_5{{
    {"N90_Nollie","Nollie","Nollie",3},
    {"N90_N_PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"N90_N_FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"N90_N_VarialKickflip","N_VarialKickflip","N_VarialHeelflip",3},
    {"N90_N_VarialHeelflip","N_VarialHeelflip","N_VarialKickflip",4},
    {"N90_N_Hardflip","N_Hardflip","N_InwardHeelflip",3},
    {"N90_N_InwardHeelflip","N_InwardHeelflip","N_Hardflip",4},
    {"N90_N_360PopShuvit","N_360PopShuvit","N_FS360PopShuvit",3},
    {"N90_N_FS360PopShuvit","N_FS360PopShuvit","N_360PopShuvit",4},
    {"N90_N_360Flip","N_360Flip","N_Laserflip",0},
    {"N90_N_Laserflip","N_Laserflip","N_360Flip",0},
    {"N90_N_360Hardflip","N_360Hardflip","N_360InwardHeelflip",0},
    {"N90_N_360InwardHeelflip","N_360InwardHeelflip","N_360Hardflip",0},
    {"N90_N_Kickflip","N_Kickflip","N_Heelflip",0},
    {"N90_N_Heelflip","N_Heelflip","N_Kickflip",0},
    {"Nollie","Nollie","Nollie",3},
    {"N_PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"N_FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"N_VarialKickflip","N_VarialKickflip","N_VarialHeelflip",3},
    {"N_VarialHeelflip","N_VarialHeelflip","N_VarialKickflip",4},
    {"N_Hardflip","N_Hardflip","N_InwardHeelflip",3},
    {"N_InwardHeelflip","N_InwardHeelflip","N_Hardflip",4},
    {"N_360PopShuvit","N_360PopShuvit","N_FS360PopShuvit",3},
    {"N_FS360PopShuvit","N_FS360PopShuvit","N_360PopShuvit",4},
    {"N_360Flip","N_360Flip","N_Laserflip",0},
    {"N_Laserflip","N_Laserflip","N_360Flip",0},
    {"N_360Hardflip","N_360Hardflip","N_360InwardHeelflip",0},
    {"N_360InwardHeelflip","N_360InwardHeelflip","N_360Hardflip",0},
    {"N_Kickflip","N_Kickflip","N_Heelflip",0},
    {"N_Heelflip","N_Heelflip","N_Kickflip",0},
    {"Ollie","Nollie","Nollie",3},
    {"PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"FSPopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"VarialKickflip","Nollie","Nollie",3},
    {"VarialHeelflip","Nollie","Nollie",4},
    {"Hardflip","Nollie","Nollie",3},
    {"InwardHeelflip","Nollie","Nollie",4},
    {"360PopShuvit","N_PopShuvit","N_FSPopShuvit",3},
    {"FS360PopShuvit","N_FSPopShuvit","N_PopShuvit",4},
    {"360Flip","Nollie","Nollie",3},
    {"Laserflip","Nollie","Nollie",4},
    {"360Hardflip","Nollie","Nollie",3},
    {"360InwardHeelflip","Nollie","Nollie",4},
    {"Kickflip","Nollie","Nollie",3},
    {"Heelflip","Nollie","Nollie",4},
}};
constexpr std::array<GestureMappingRow,45> mapping_6{{
    {"N90_Ollie","Ollie","Ollie",1},
    {"N90_PopShuvit","PopShuvit","FSPopShuvit",1},
    {"N90_FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"N90_VarialKickflip","VarialKickflip","VarialHeelflip",1},
    {"N90_VarialHeelflip","VarialHeelflip","VarialKickflip",2},
    {"N90_Hardflip","Hardflip","InwardHeelflip",1},
    {"N90_InwardHeelflip","InwardHeelflip","Hardflip",2},
    {"N90_360PopShuvit","360PopShuvit","FS360PopShuvit",1},
    {"N90_FS360PopShuvit","FS360PopShuvit","360PopShuvit",2},
    {"N90_360Flip","360Flip","Laserflip",0},
    {"N90_Laserflip","Laserflip","360Flip",0},
    {"N90_360Hardflip","360Hardflip","360InwardHeelflip",0},
    {"N90_360InwardHeelflip","360InwardHeelflip","360Hardflip",0},
    {"N90_Kickflip","Kickflip","Heelflip",0},
    {"N90_Heelflip","Heelflip","Kickflip",0},
    {"Ollie","Ollie","Ollie",1},
    {"PopShuvit","PopShuvit","FSPopShuvit",1},
    {"FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"VarialKickflip","VarialKickflip","VarialHeelflip",1},
    {"VarialHeelflip","VarialHeelflip","VarialKickflip",2},
    {"Hardflip","Hardflip","InwardHeelflip",1},
    {"InwardHeelflip","InwardHeelflip","Hardflip",2},
    {"360PopShuvit","360PopShuvit","FS360PopShuvit",1},
    {"FS360PopShuvit","FS360PopShuvit","360PopShuvit",2},
    {"360Flip","360Flip","Laserflip",0},
    {"Laserflip","Laserflip","360Flip",0},
    {"360Hardflip","360Hardflip","360InwardHeelflip",0},
    {"360InwardHeelflip","360InwardHeelflip","360Hardflip",0},
    {"Kickflip","Kickflip","Heelflip",0},
    {"Heelflip","Heelflip","Kickflip",0},
    {"Nollie","Ollie","Ollie",1},
    {"N_PopShuvit","PopShuvit","FSPopShuvit",1},
    {"N_FSPopShuvit","FSPopShuvit","PopShuvit",2},
    {"N_VarialKickflip","Ollie","Ollie",1},
    {"N_VarialHeelflip","Ollie","Ollie",2},
    {"N_Hardflip","Ollie","Ollie",1},
    {"N_InwardHeelflip","Ollie","Ollie",2},
    {"N_360PopShuvit","PopShuvit","FSPopShuvit",1},
    {"N_FS360PopShuvit","FSPopShuvit","PopShuvit",2},
    {"N_360Flip","Ollie","Ollie",1},
    {"N_Laserflip","Ollie","Ollie",2},
    {"N_360Hardflip","Ollie","Ollie",1},
    {"N_360InwardHeelflip","Ollie","Ollie",2},
    {"N_Kickflip","Ollie","Ollie",1},
    {"N_Heelflip","Ollie","Ollie",2},
}};
constexpr std::array<std::string_view,30> common{{
    "Ollie",
    "PopShuvit",
    "FSPopShuvit",
    "VarialKickflip",
    "VarialHeelflip",
    "Hardflip",
    "InwardHeelflip",
    "360PopShuvit",
    "FS360PopShuvit",
    "360Flip",
    "Laserflip",
    "360Hardflip",
    "360InwardHeelflip",
    "Kickflip",
    "Heelflip",
    "Nollie",
    "N_PopShuvit",
    "N_FSPopShuvit",
    "N_VarialKickflip",
    "N_VarialHeelflip",
    "N_Hardflip",
    "N_InwardHeelflip",
    "N_360PopShuvit",
    "N_FS360PopShuvit",
    "N_360Flip",
    "N_Laserflip",
    "N_360Hardflip",
    "N_360InwardHeelflip",
    "N_Kickflip",
    "N_Heelflip",
}};
constexpr std::array<std::string_view,15> nose_90{{
    "90_Nollie",
    "90_N_PopShuvit",
    "90_N_FSPopShuvit",
    "90_N_VarialKickflip",
    "90_N_VarialHeelflip",
    "90_N_Hardflip",
    "90_N_InwardHeelflip",
    "90_N_360PopShuvit",
    "90_N_FS360PopShuvit",
    "90_N_360Flip",
    "90_N_Laserflip",
    "90_N_360Hardflip",
    "90_N_360InwardHeelflip",
    "90_N_Kickflip",
    "90_N_Heelflip",
}};
constexpr std::array<std::string_view,15> tail_90{{
    "90_Ollie",
    "90_PopShuvit",
    "90_FSPopShuvit",
    "90_VarialKickflip",
    "90_VarialHeelflip",
    "90_Hardflip",
    "90_InwardHeelflip",
    "90_360PopShuvit",
    "90_FS360PopShuvit",
    "90_360Flip",
    "90_Laserflip",
    "90_360Hardflip",
    "90_360InwardHeelflip",
    "90_Kickflip",
    "90_Heelflip",
}};
constexpr std::array<std::string_view,15> nose_n90{{
    "N90_Nollie",
    "N90_N_PopShuvit",
    "N90_N_FSPopShuvit",
    "N90_N_VarialKickflip",
    "N90_N_VarialHeelflip",
    "N90_N_Hardflip",
    "N90_N_InwardHeelflip",
    "N90_N_360PopShuvit",
    "N90_N_FS360PopShuvit",
    "N90_N_360Flip",
    "N90_N_Laserflip",
    "N90_N_360Hardflip",
    "N90_N_360InwardHeelflip",
    "N90_N_Kickflip",
    "N90_N_Heelflip",
}};
constexpr std::array<std::string_view,15> tail_n90{{
    "N90_Ollie",
    "N90_PopShuvit",
    "N90_FSPopShuvit",
    "N90_VarialKickflip",
    "N90_VarialHeelflip",
    "N90_Hardflip",
    "N90_InwardHeelflip",
    "N90_360PopShuvit",
    "N90_FS360PopShuvit",
    "N90_360Flip",
    "N90_Laserflip",
    "N90_360Hardflip",
    "N90_360InwardHeelflip",
    "N90_Kickflip",
    "N90_Heelflip",
}};
}
bool ParseGestureGroup(std::string_view name,GestureGroup& output,std::string& error)
{
    constexpr std::array<std::string_view,7> names{"Square","Nose","Tail","90Nose","90Tail","N90Nose","N90Tail"};
    for (std::size_t i = 0; i < names.size(); ++i) if (name == names[i]) { output = static_cast<GestureGroup>(i); return true; }
    error = "HasGestureIntent has undefined group `"+std::string(name)+"`"; return false;
}
bool HasGestureIntent(GestureGroup group,const IntentMap& action)
{
    for (auto name : common) if (action.Contains(name)) return true;
    const auto any = [&](const auto& names) { for (auto name : names) if (action.Contains(name)) return true; return false; };
    switch (group)
    {
    case GestureGroup::Square: case GestureGroup::Nose: case GestureGroup::Tail: return false;
    case GestureGroup::Nose90: return any(nose_90);
    case GestureGroup::Tail90: return any(tail_90);
    case GestureGroup::NoseN90: return any(nose_n90);
    case GestureGroup::TailN90: return any(tail_n90);
    }
    assert(false); return false;
}
GestureMappingView GestureMappingRows(GestureGroup group)
{
    switch (group)
    {
    case GestureGroup::Square: return {mapping_0.data(),mapping_0.size()};
    case GestureGroup::Nose: return {mapping_1.data(),mapping_1.size()};
    case GestureGroup::Tail: return {mapping_2.data(),mapping_2.size()};
    case GestureGroup::Nose90: return {mapping_3.data(),mapping_3.size()};
    case GestureGroup::Tail90: return {mapping_4.data(),mapping_4.size()};
    case GestureGroup::NoseN90: return {mapping_5.data(),mapping_5.size()};
    case GestureGroup::TailN90: return {mapping_6.data(),mapping_6.size()};
    }
    assert(false); return {nullptr,0};
}
std::optional<std::string_view> SelectGestureTrick(GestureGroup group,const IntentMap& action,bool mirrored)
{
    const auto rows = GestureMappingRows(group); const GestureMappingRow* selected = nullptr;
    auto bucket = std::numeric_limits<std::size_t>::max();
    for (auto index = rows.size; index > 0; --index)
    {
        const auto& row = rows.data[index-1]; std::uint32_t sum = 0;
        for (auto word : EncodeIntentKey(row.key)) sum += word;
        const auto current = static_cast<std::size_t>(sum)%43;
        if (current < bucket && action.Contains(row.key)) { selected = &row; bucket = current; }
    }
    if (!selected) return std::nullopt;
    mirrored = mirrored && !action.Contains("DontMirrorTrick");
    if (action.Contains("DarkCatch") && selected->dark_catch != 0)
    {
        const auto kind = selected->dark_catch;
        if ((kind == 2 && !mirrored) || (kind == 1 && mirrored)) return "Heelflip";
        if ((kind == 3 && mirrored) || (kind == 4 && !mirrored)) return "N_Heelflip";
        if ((kind == 3 && !mirrored) || (kind == 4 && mirrored)) return "N_Kickflip";
        return "Kickflip";
    }
    return mirrored ? selected->mirrored : selected->normal;
}
void GestureTrickState::Begin(GestureGroup group,std::optional<std::string_view> override_name,const IntentMap& action,IntentMap& motion,bool mirrored)
{
    const auto chosen = SelectGestureTrick(group,action,mirrored); if (!chosen) return;
    auto name = std::string(override_name.value_or(*chosen)); if (action.Contains("Underflip")) name = "U_"+name;
    successor = name == "Kickflip" ? std::optional<std::string_view>("KickflipHold") :
        name == "Heelflip" ? std::optional<std::string_view>("HeelflipHold") :
        name == "N_Kickflip" ? std::optional<std::string_view>("N_KickflipHold") :
        name == "N_Heelflip" ? std::optional<std::string_view>("N_HeelflipHold") : std::nullopt;
    selected = name; motion.Insert(name,0);
}
void GestureTrickState::Update(IntentMap& motion)
{
    if (!first_update && selected && successor) { motion.Remove(*selected); motion.Insert(*successor,0); }
    first_update = false;
}
void GestureTrickState::End(IntentMap& motion) const
{
    motion.Remove("DarkCatch");
    if (selected) { if (successor) motion.Remove(*successor); motion.Remove(*selected); }
}
}
