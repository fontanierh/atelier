#include "JapanSailState.h"
namespace
{
bool SailStateRange(float V,float Lo,float Hi){return FMath::IsFinite(V)&&V>=Lo&&V<=Hi;}
}
bool FJapanSailState::IsValid() const
{
    return SailStateRange(Yaw,-180.f,180.f)&&SailStateRange(Speed,0.f,650.1f)&&SailStateRange(Steering,-1.01f,1.01f)&&
        SailStateRange(SailAmount,0.f,1.f)&&(SailTarget==0.f||SailTarget==1.f);
}
bool FJapanSailState::SerializeCheckpoint(FArchive& Ar)
{
    uint8 EquippedByte=Equipped?1:0;
    if(Ar.IsSaving()&&!IsValid()){Ar.SetError();return false;}
    Ar<<EquippedByte<<Serial<<Yaw<<Speed<<Steering<<SailAmount<<SailTarget;
    if(Ar.IsLoading())Equipped=EquippedByte!=0;
    if(EquippedByte>1||!IsValid())Ar.SetError();
    return !Ar.IsError();
}
