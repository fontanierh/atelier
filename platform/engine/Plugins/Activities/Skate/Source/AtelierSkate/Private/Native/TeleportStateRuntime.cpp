#include "TeleportStateRuntime.h"
#include <cstring>
namespace atelier::skate
{
namespace
{
RawMatrix Raw(Mat4 matrix)
{RawMatrix result;for(unsigned c=0;c<4;++c)for(unsigned i=0;i<4;++i)std::memcpy(&result[c][i],&matrix[c][i],4);return result;}
}
void TeleportCoreState::Enter(){ready_=false;received_=false;on_board_=true;}
TeleportCoreState::Update TeleportCoreState::Process(std::uint32_t flags,RawMatrix matrix,std::uint8_t byte)
{
    if((flags&2)==0)return Update::RequestCheckpoint;
    received_=true;target_=matrix;ready_=true;on_board_=(byte&1)!=0;return Update::Captured;
}
std::optional<TeleportOutputFields> TeleportCoreState::Output() const
{
    if(!ready_)return std::nullopt;
    return TeleportOutputFields{target_,on_board_?100u:500u,1,1};
}
void TeleportStateRuntime::RequestManual(Mat4 matrix,bool on_board)
{vehicle_ejection_.reset();pending_reply_=TeleportTarget{Raw(matrix),on_board};manual_on_board_=on_board;}
void TeleportStateRuntime::RequestVehicleEjection(Mat4 matrix,std::array<float,3> velocity,std::array<float,3> angular)
{RequestManual(matrix,false);vehicle_ejection_=std::make_pair(velocity,angular);}
std::optional<std::pair<std::array<float,3>,std::array<float,3>>> TeleportStateRuntime::TakeVehicleEjection()
{auto result=vehicle_ejection_;vehicle_ejection_.reset();return result;}
std::optional<bool> TeleportStateRuntime::TakeManualOnBoard()
{auto result=manual_on_board_;manual_on_board_.reset();return result;}
void TeleportStateRuntime::SetCheckpoint(TeleportCheckpoint checkpoint)
{checkpoint_=checkpoint;pending_reply_.reset();}
bool TeleportStateRuntime::Update(const ProcessedPhysicsInput& input)
{return state_.Process(input.flags_2468,input.matrix_1536,input.byte_1600)==TeleportCoreState::Update::RequestCheckpoint;}
void TeleportStateRuntime::Reply(TeleportCheckpoint checkpoint)
{pending_reply_=TeleportTarget{Raw(checkpoint.transform),checkpoint.on_board};}
std::optional<AnimationExternalReset> TeleportStateRuntime::TakeReply()
{
    auto result=pending_reply_;pending_reply_.reset();if(!result)return std::nullopt;
    return AnimationExternalReset{result->transform,std::uint8_t(result->on_board)};
}
std::optional<TeleportOutputFields> TeleportStateRuntime::PublishOutput(PhysicalPlayerInput& physical) const
{
    const auto output=state_.Output();if(!output)return std::nullopt;
    physical.teleport_output=output;physical.state.identifier_8=output->next_state;physical.state.flag_61=output->state_61;return output;
}
}
