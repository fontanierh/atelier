#pragma once
#include "PlayerGrindInputWorld.h"
namespace atelier::skate
{
struct PlayerGrindTruckContact {Vec4 position;std::size_t primitive;};
struct PlayerGrindCandidate {Vec4 direction,centre,front,rear;std::size_t primitive;};
enum class PlayerGrindEntryKind:std::uint32_t {RideFromAbove=0,RideFromBelow=1,RideIntoCoping=2,StayInGrind=3,ChangeGrind=4,AirToGrind=5,DropIn=6};
struct PlayerGrindAdmissionDecision {PlayerGrindEntryKind kind;bool allowed;};
struct PlayerGrindAdmission
{
    std::uint32_t category,state;float speed;Vec4 velocity;const PointGraph<4>& threshold_vs_slope;
    PlayerGrindAdmissionDecision Test(std::uint32_t requested_state,Vec4 tangent,bool allows_drop_in) const;
};
float PlayerGrindApproachSlope(Vec4 tangent,Vec4 velocity);
float PlayerGrindEngagementSlope(Vec4 tangent,Vec4 velocity);
std::optional<Vec4> PlayerGrindSegmentTriangle(Vec4 start,Vec4 end,const std::array<Vec4,3>&);
std::optional<PlayerGrindTruckContact> PlayerGrindDeckContact(Mat4,std::uint32_t flags,float above,float below,float truck_distance,const std::vector<PlayerGrindPrimitive>&);
std::array<std::optional<PlayerGrindTruckContact>,2> PlayerGrindTruckContacts(Mat4,std::uint32_t flags,float truck_to_wheel,float deck_to_truck,const std::vector<PlayerGrindPrimitive>&);
std::optional<PlayerGrindCandidate> PlayerGrindBoardslideCandidate(Mat4,PlayerGrindTruckContact,PlayerGrindPrimitive,Vec4 velocity,std::uint32_t category,std::int32_t manager_frames,std::uint32_t flags,float deck_to_truck,float truck_to_wheel,const PlayerGrindAdmission&);
std::optional<PlayerGrindCandidate> PlayerGrindFiftyFiftyCandidate(Mat4,std::array<float,2> balance,const std::array<std::optional<PlayerGrindTruckContact>,2>&,const std::vector<PlayerGrindPrimitive>&);
Vec4 PlayerGrindUprightNormal(Vec4);
bool PlayerGrindWithinApproach(Vec4 direction,Vec4 velocity,float degrees);
struct PlayerGrindFamilyContact {PlayerGrindCandidate geometry;bool front;std::uint32_t kind;PlayerGrindEntryKind entry_kind;};
std::optional<PlayerGrindTruckContact> PlayerGrindInvertedContact(Mat4,std::uint32_t flags,float epsilon,float depth,const std::vector<PlayerGrindPrimitive>&);
std::array<std::optional<PlayerGrindTruckContact>,2> PlayerGrindTipContacts(Mat4,std::uint32_t flags_2484,std::uint32_t state,std::uint32_t flags_2468,float truck_distance,const std::vector<PlayerGrindPrimitive>&);
std::optional<PlayerGrindFamilyContact> PlayerGrindDarkslide(Mat4,PlayerGrindTruckContact,PlayerGrindPrimitive,Vec4 velocity,std::uint32_t category,std::uint32_t low_wheel_frames,const PlayerGrindAdmission&);
std::optional<PlayerGrindFamilyContact> PlayerGrindFiveO(Mat4,const std::array<std::optional<PlayerGrindTruckContact>,2>&,const std::vector<PlayerGrindPrimitive>&,Vec4 velocity,std::uint32_t flags_2476,std::uint32_t flags_2472,std::uint32_t ground_frames,float translation,const PlayerGrindAdmission&);
std::optional<PlayerGrindFamilyContact> PlayerGrindTipslide(Mat4,const std::array<std::optional<PlayerGrindTruckContact>,2>&,const std::vector<PlayerGrindPrimitive>&,Vec4 velocity,std::uint32_t category,std::uint32_t flags_2476,std::uint32_t flags_2472,std::uint32_t ground_frames,float balance,Vec4 reference_right,const PlayerGrindAdmission&);
bool PlayerGrindIsBackslash(Vec4 board_position,Vec4 point,std::array<Vec4,2> far_points,Vec4 support,float truck_distance,std::uint32_t state);
struct PlayerGrindContactQuery
{
    Mat4 board;PlayerGrindAdmission admission;
    std::uint32_t flags_2468,flags_2472,flags_2476,flags_2484,tip_state;
    float truck_to_wheel,deck_to_truck,test_above,test_below,translation,stability_nudge,balance;
    Vec4 reference_right;std::uint32_t ground_frames,low_wheel_frames;bool forbidden;
};
struct PlayerGrindProximity {PlayerGrindTruckContact contact;bool deck_contact;};
struct PlayerGrindContactInvestigation {std::optional<PlayerGrindFamilyContact> candidate;std::optional<PlayerGrindProximity> proximity;};
PlayerGrindContactInvestigation InvestigatePlayerGrindContact(const PlayerGrindContactQuery&,const std::vector<PlayerGrindPrimitive>&);
}
