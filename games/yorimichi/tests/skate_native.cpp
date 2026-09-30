#include "../../../platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Public/SkateNativeTuning.h"
#include <cassert>
#include <iostream>
#include <limits>
using namespace SkateNative;
static bool Near(float A,float B,float E=1e-5f) { return std::abs(A-B)<E; }

int main()
{
    Settings S=RetailSettings();
    for(int FPS : {30,60,144})
    {
        FixedClock Clock; Steering Control; int Steps=0;
        for(int I=0;I<FPS*4;++I)
        {
            int N=Clock.Advance(1./FPS); Steps+=N;
            for(int K=0;K<N;++K) Control.Update(S,1,0,5,1,false,.5f,false);
        }
        assert(Steps==240 && std::abs(Clock.Remainder)<1e-7);
    }
    assert(PushStrength(S,.25f,0)>PushStrength(S,.02f,0)*2);
    // Endpoint semantics, duplicate knots and the native unordered branch.
    Curve C; C.Count=4; C.X={0,.5f,.5f,1}; C.Y={0,1,2,3};
    assert(C.At(-10)==0 && C.At(10)==3 && C.At(.5f)==2);
    assert(C.At(std::numeric_limits<float>::quiet_NaN())==3);
    assert(Near(C.At(.25f),.5f));
    // Wheel activation/release, pushing suppression and speed-dependent carves.
    Steering Slow,Fast,Push,ManualSteer,Reverse;
    for(int I=0;I<120;++I)
    {
        Slow.Update(S,1,0,3,1,false,.5f,false);
        Fast.Update(S,1,0,20,1,false,.5f,false);
        Push.Update(S,1,0,3,1,false,.5f,true);
        ManualSteer.Update(S,1,0,3,1,true,.5f,false);
        Reverse.Update(S,1,0,3,-1,false,.5f,false);
    }
    assert(Slow.DeckTilt>Fast.DeckTilt*2);
    assert(Near(Push.DeckTilt,Slow.DeckTilt*S.PushSteerMin));
    assert(Near(ManualSteer.DeckTilt,Slow.DeckTilt*S.ManualSteer));
    assert(Near(Reverse.DeckTilt,-Slow.DeckTilt));
    float Previous=Slow.Targets[0];
    Slow.Update(S,0,0,3,1,false,.5f,false,false,true);
    assert(Slow.Targets[0]==Previous);
    Slow.Update(S,0,0,3,1,false,.5f,false,false,true);
    assert(Near(Slow.Targets[0],Previous*.983f));
    // One push approaches a fixed target exactly once and cannot propel above the cap.
    float Speed=0;
    const float Target=Speed+S.PushDVStart;
    for(int I=0;I<60;++I) Speed+=PushDelta(S,Target,Speed,Speed);
    assert(Near(Speed,S.PushDVStart));
    assert(PushDelta(S,12,10,10)==0);
    assert(Near(PushDelta(S,9,8.4f,8.4f),.1f));
    assert(PushDelta(S,3,4,4)==0);
    assert(RetailSettings(Difficulty::Easy).PushDVStart>S.PushDVStart);
    assert(RetailSettings(Difficulty::Hardcore).GrindLockDistance<S.GrindLockDistance);
    // No free energy from pumping on a plane, including an exaggerated crouch cycle.
    Pumping Flat;
    for(int I=0;I<180;++I)
        assert(Flat.Update(S,{float(I)*.1f,0,0},{0,0,1},.7f+.2f*std::sin(I*.1f),0,true)==0);
    // Rising COM in a concave transition produces a bounded impulse; frozen COM does not.
    Pumping Ramp,Static;
    float Total=0,StaticTotal=0;
    for(int I=0;I<100;++I)
    {
        float A=-.7f+I*.01f;
        Vec P{5*std::sin(A),0,5*(1-std::cos(A))},N{-std::sin(A),0,std::cos(A)};
        float DV=Ramp.Update(S,P,N,.3f+I*.008f,0,true);
        assert(DV<=S.PumpMaxAcceleration*Step+1e-6f);
        Total+=DV; StaticTotal+=Static.Update(S,P,N,.7f,0,true);
    }
    assert(Total>0 && StaticTotal==0);
    // The manual controller actually moves the deck and converges without random input.
    Manual M; float Pitch=0;
    for(int I=0;I<300;++I) Pitch+=M.Update(S,.53f,Pitch,4,I*Step,true,false);
    assert(std::isfinite(Pitch) && Pitch>.1f && Pitch<S.ManualMaxAngle*Pi/180);
    assert(M.Update(S,0,Pitch,4,5,true,false)==0 && M.Elapsed==0);
    // Launch retains tangential travel and subtracts COM height from the desired apex.
    Vec Soft=GroundJump(S,{5,0,0},{0,0,1},5,0,.65f);
    Vec Hard=GroundJump(S,{5,0,0},{0,0,1},5,1,.65f);
    assert(Soft.X==5 && Hard.X==5 && Hard.Z>Soft.Z && Hard.Z<6);
    assert(Near(Hard.Z*Hard.Z/(2*S.Gravity),S.JumpMax-.65f));
    auto Clean=LandingQuality(S,{0,0,1},{5,0,-4},{1,0,0},0,false);
    auto Fakie=LandingQuality(S,{0,0,1},{-5,0,-4},{1,0,0},0,true);
    auto Sketchy=LandingQuality(S,{0,0,1},{4,3,-4},{1,0,0},0,false);
    assert(Clean.Kind==0 && Fakie.Kind==0 && Sketchy.Kind!=0 && Near(Sketchy.SideSpeed,3));
    assert(GrindPin(-.05f,0)<0 && GrindPin(.05f,0)>0);
    assert(GrindFriction(-1,1,1)==0);
    // Full retail pattern catalog, including variants with duplicate names.
    Gestures G; G.Patterns=RetailPatterns(); assert(G.Patterns.size()==78);
    auto Gesture=[&](std::initializer_list<Point> Path)
    {
        G.Reset(); G.Update({}); GestureResult Found;
        for(Point P:Path) { auto R=G.Update(P); if(R.Index>=0) Found=R; }
        return Found;
    };
    auto Ollie=Gesture({{0,1},{0,-1}});
    assert(Ollie.Index>=0 && G.Patterns[Ollie.Index].Name=="Ollie" && Near(Ollie.Strength,1));
    auto Nollie=Gesture({{0,-1},{0,1}});
    assert(Nollie.Index>=0 && G.Patterns[Nollie.Index].Name=="Nollie");
    auto Kick=Gesture({{-.028571f,.691429f},{.908571f,-.417143f}});
    assert(Kick.Index>=0 && G.Patterns[Kick.Index].Name=="Kickflip");
    // Holding the loaded point does not age the native gesture; excess misses cancel it.
    G.Reset(); G.Update({});
    for(int I=0;I<300;++I) assert(G.Update({0,1}).Index<0);
    auto Held=G.Update({0,-1}); assert(Held.Index>=0 && Near(Held.Strength,1));
    G.Reset(); G.Update({}); G.Update({0,1});
    for(int I=0;I<20;++I) G.Update({});
    assert(G.Update({0,-1}).Index<0);
    std::cout << "PASS: retail steering, trucks, propulsion, pumping, manual, jump, landing, grind and gestures\n";
}
