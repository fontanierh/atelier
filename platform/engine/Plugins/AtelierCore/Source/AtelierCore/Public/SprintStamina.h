#pragma once
#include <algorithm>

// One unit is one ring: by default six seconds of sprint and three seconds to refill (a character may set its own).
struct FSprintStamina
{
    float Units=2.f, Capacity=2.f, RecoveryDelay=0.f;
    float SprintSeconds=6.f, RefillSeconds=3.f, Delay=.8f;
    bool Exhausted=false, Sprinting=false;
    void SetCapacity(int Rings)
    {
        const float Next=float(std::clamp(Rings,1,5));
        if(Next==Capacity)return;
        Units=std::clamp(Units+Next-Capacity,0.f,Next);Capacity=Next;
        if(Units<=0)Exhausted=true;
    }
    // Paused: nothing drains or refills (a menu, or a character in the air or in the water, who refills only on foot).
    void Tick(float Dt,bool Held,bool CanSprint,bool Paused)
    {
        Sprinting=false;
        if(Paused||Dt<=0)return;
        if(Exhausted&&Units>=Capacity&&!Held)Exhausted=false;
        Sprinting=Held&&CanSprint&&!Exhausted&&Units>0;
        if(Sprinting)
        {
            Units=std::max(0.f,Units-Dt/SprintSeconds);RecoveryDelay=Delay;
            if(Units<=0){Exhausted=true;Sprinting=false;}
        }
        else
        {
            const float RecoveryTime=std::max(0.f,Dt-RecoveryDelay);
            RecoveryDelay=std::max(0.f,RecoveryDelay-Dt);
            Units=std::min(Capacity,Units+RecoveryTime/RefillSeconds);
        }
    }
    // Spend Rings at once, or per frame for a rate (climbing, gliding, swimming, a charge). False when exhausted;
    // spending the last of it exhausts until the rings are full again.
    bool Use(float Rings)
    {
        if(Exhausted||Units<=0)return false;
        Units=std::max(0.f,Units-Rings);RecoveryDelay=std::max(RecoveryDelay,Delay);
        if(Units<=0)Exhausted=true;
        return true;
    }
};
