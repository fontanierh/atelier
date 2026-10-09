#pragma once
#include "KnownAirRuntime.h"
namespace atelier::skate::known_air
{
float Bits(std::uint32_t);
float Select(float test,float nonnegative,float negative);
Vec4 Add(Vec4,Vec4);
Vec4 Sub(Vec4,Vec4);
Vec4 Scale(Vec4,float);
Vec4 Cross(Vec4,Vec4);
Vec4 Rotate(const Mat4&,Vec4);
std::pair<Vec4,float> Normalize(Vec4);
float Signed(Vec4,Vec4,Vec4);
float Wrap(float);
Vec4 TransformPoint(const Mat4&,Vec4);
RestoreVelocityGeometry RestoreGeometry(Vec4,Vec4);
KnownAirTrajectory Trajectory(AirTrajectory);
AirTrajectory Actual(const KnownAirTrajectory&);
Vec4 Position(const KnownAirTrajectory&,float);
Vec4 Velocity(const KnownAirTrajectory&,float);
std::int32_t WrappingAdd(std::int32_t,std::uint32_t);
// Concrete source Runtime. Every effect uses the same actual owner and first
// error retention never suppresses later core calls or partial mutations.
class Live
{
public:
    AirPhaseOwners owners;
    BoardToolkit toolkit;
    AirTrajectorySelection selection;
    Vec4 local_com,board_position;
    const KnownAirConfiguration& configuration;
    std::optional<std::string> first_error;
    Live(AirPhaseOwners o,BoardToolkit t,AirTrajectorySelection s,Vec4 com,Vec4 board,const KnownAirConfiguration& c)
        :owners(o),toolkit(t),selection(s),local_com(com),board_position(board),configuration(c){}
    static std::optional<Live> Create(AirPhaseOwners,const KnownAirConfiguration&,std::string& error);
    void Record(bool result,const std::string& error){if (!first_error&&!result) first_error=error;}
    bool Finish(std::string& error) const;
    void ResetFlip();
    void BeginFlip(bool side);
    void RequestCollision(std::uint32_t);
    void UpdateCollision();
    void StartGrind();
    std::pair<std::int32_t,Vec4> Closest(Vec4,Vec4) const;
    KnownAirPrediction Prediction() const;
    void Reckoning(Vec4,float,float,float);
    void Skeleton(Vec4);
    void Footplant(const KnownAirState&,const KnownAirFrame&);
    void Wipeout(bool);
    Vec4 BoardVelocity() const;
    void SetBoardVelocity(Vec4);
    Vec4 BoardForward() const;
};
bool Frame(AirPhaseOwners,std::uint32_t next,KnownAirFrame&,std::string& error);
KnownAirReckoningFields ReckoningFields(AirPhaseOwners);
void InitializeTrajectory(KnownAirState&,const KnownAirFrame&,const KnownAirSettings&,const KnownAirModeSettings&,Live&);
void RestoreVelocity(KnownAirState&,KnownAirFrame&,const KnownAirSettings&,Live&);
void Follow(KnownAirState&,const KnownAirFrame&,const KnownAirSettings&,const Live&);
float FlipSpeed(KnownAirState&,const KnownAirFrame&,const KnownAirSettings&,const KnownAirModeSettings&,const KnownAirReckoningFields&,Live&);
float SpinSpeed(const KnownAirState&,const KnownAirFrame&,const KnownAirSettings&,const KnownAirModeSettings&,const KnownAirReckoningFields&);
void Enter(KnownAirState&,const KnownAirFrame&,const KnownAirSettings&,const KnownAirModeSettings&,Live&);
void Update(KnownAirState&,const KnownAirFrame&,const KnownAirSettings&,const KnownAirModeSettings&,const KnownAirReckoningFields&,Live&);
void Exit(KnownAirState&,KnownAirFrame&,const KnownAirSettings&,KnownAirReckoningFields&,Live&);
void Post(KnownAirState&,const KnownAirFrame&,const KnownAirModeSettings&,const KnownAirWipeoutSettings&,KnownAirWipeoutRequest&,Live&);
KnownAirOutput Storage(const AirOutputFields&);
void Fill(const KnownAirState&,const KnownAirFrame&,KnownAirOutput&,Live&);
void Publish(const KnownAirOutput&,AirOutputFields&);
}
