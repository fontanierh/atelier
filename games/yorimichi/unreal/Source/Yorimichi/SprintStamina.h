#pragma once
#include <algorithm>

// One unit is one ring: six seconds of sprint, three seconds to refill.
struct FSprintStamina
{
    float Units=2.f, Capacity=2.f, RecoveryDelay=0.f;
    bool Exhausted=false, Sprinting=false;
    void SetCapacity(int Rings)
    {
        const float Next=float(std::clamp(Rings,1,5));
        if(Next==Capacity)return;
        Units=std::clamp(Units+Next-Capacity,0.f,Next);Capacity=Next;
        if(Units<=0)Exhausted=true;
    }
    void Tick(float Dt,bool Held,bool CanSprint,bool Paused)
    {
        Sprinting=false;
        if(Paused||Dt<=0)return;
        if(Exhausted&&Units>=Capacity&&!Held)Exhausted=false;
        Sprinting=Held&&CanSprint&&!Exhausted&&Units>0;
        if(Sprinting)
        {
            Units=std::max(0.f,Units-Dt/6.f);RecoveryDelay=.8f;
            if(Units<=0){Exhausted=true;Sprinting=false;}
        }
        else
        {
            const float RecoveryTime=std::max(0.f,Dt-RecoveryDelay);
            RecoveryDelay=std::max(0.f,RecoveryDelay-Dt);
            Units=std::min(Capacity,Units+RecoveryTime/3.f);
        }
    }
};
