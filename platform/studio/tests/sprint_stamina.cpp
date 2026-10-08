#include "../../engine/Plugins/AtelierCore/Source/AtelierCore/Public/SprintStamina.h"
#include <cassert>
#include <cmath>
#include <iostream>
void step(FSprintStamina& S,float Seconds,bool Held,bool Moving,bool Paused=false){for(int i=0;i<int(Seconds*120);++i)S.Tick(1.f/120,Held,Moving,Paused);}
int main(){
 FSprintStamina S;assert(S.Capacity==2&&S.Units==2);
 step(S,6,true,true);assert(std::abs(S.Units-1)<.002&&S.Sprinting);
 step(S,6.1,true,true);assert(S.Exhausted&&!S.Sprinting&&S.Units<.05);
 step(S,8,true,true);assert(S.Units==2&&S.Exhausted&&!S.Sprinting);
 step(S,.1,false,true);assert(!S.Exhausted);step(S,1,true,true);assert(S.Sprinting);
 float U=S.Units;step(S,5,true,true,true);assert(S.Units==U&&!S.Sprinting);
 step(S,8,true,false);assert(S.Units==2&&!S.Sprinting);
 S.SetCapacity(5);assert(S.Units==5);step(S,29,true,true);assert(!S.Exhausted);step(S,1.1,true,true);assert(S.Exhausted);
 S.SetCapacity(1);assert(S.Units<=1);step(S,5,false,false);assert(S.Units==1&&!S.Exhausted);
 step(S,1,true,true);U=S.Units;step(S,.5,false,true);assert(S.Units==U);step(S,1,false,true);assert(S.Units>U);
 S.SetCapacity(99);assert(S.Capacity==5);S.SetCapacity(-1);assert(S.Capacity==1);
 FSprintStamina Reduced;step(Reduced,7,true,true);Reduced.SetCapacity(1);assert(Reduced.Units==0&&Reduced.Exhausted);step(Reduced,4,true,true);assert(!Reduced.Sprinting&&Reduced.Exhausted);
 std::cout<<"PASS: ring duration, exhaustion latch, release, recovery delay, pause, idle, capacity limits\n";
}
