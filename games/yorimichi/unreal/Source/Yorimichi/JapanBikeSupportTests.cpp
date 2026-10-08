#include "JapanBikeSupport.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Engine/StaticMesh.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanBikeSupportTest,"Yorimichi.Network.BikeSupport",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)

bool FJapanBikeSupportTest::RunTest(const FString&)
{
    const TArray<FVector> Tetrahedron={FVector(0,0,0),FVector(10,0,0),FVector(0,10,0),FVector(0,0,10),FVector(1,1,1)};
    TArray<FVector> TetrahedronHull;
    TestTrue(TEXT("Unreal-wound hull faces contain their interior points"),JapanBikeSupport::Build(Tetrahedron,TetrahedronHull));
    TestEqual(TEXT("Interior point is not needed for support"),TetrahedronHull.Num(),4);
    // A finite-width wheel fixture. Its side hub, not the upright radius, supports
    // the 84-degree crash. The independent oracle scans every source point.
    TArray<FVector> Vertices;
    for(int32 Ring=0;Ring<72;++Ring)
        for(int32 Cross=0;Cross<12;++Cross)
        {
            const double A=2.*PI*Ring/72.,B=2.*PI*Cross/12.;
            const double Radius=21.+2.*FMath::Cos(B);
            Vertices.Add(FVector(Radius*FMath::Cos(A),3.5*FMath::Sin(B),Radius*FMath::Sin(A)));
        }
    Vertices.Add(FVector(0,6,0));Vertices.Add(FVector(0,-6,0));
    TArray<FVector> Points;
    if(!TestTrue(TEXT("A wheel builds a bounded support hull"),JapanBikeSupport::Build(Vertices,Points)))return false;
    TestTrue(TEXT("Cached hull is smaller than the input and bounded"),Points.Num()<Vertices.Num()&&Points.Num()<=1024);
    auto Flat=[](const FVector&,double& Height){Height=0.;return true;};
    const FTransform Upright(FQuat::Identity,FVector(0,0,23));
    TestTrue(TEXT("Upright wheel rests at its actual radius"),FMath::Abs(JapanBikeSupport::Gap(Points,Upright,Flat))<.051);
    const FTransform Side(FRotator(0,0,84),FVector(0,0,8));
    const double SideGap=JapanBikeSupport::Gap(Points,Side,Flat);
    const double OldGap=Side.TransformPosition(FVector::ZeroVector).Z-Vertices[0].Size();
    TestTrue(TEXT("Upright-radius metric reproduces a false penetration over five centimetres"),OldGap<-5.&&SideGap-OldGap>10.);
    TestTrue(TEXT("Side support accounts for wheel thickness"),SideGap>0.&&SideGap<5.);
    FTransform Raised=Side;Raised.AddToTranslation(FVector(0,0,6));
    TestTrue(TEXT("A genuinely unsupported wheel still exceeds the unchanged gate"),JapanBikeSupport::Gap(Points,Raised,Flat)>5.);
    FTransform Sunk=Side;Sunk.AddToTranslation(FVector(0,0,-8));
    TestTrue(TEXT("A genuinely sunk wheel still exceeds the unchanged gate"),JapanBikeSupport::Gap(Points,Sunk,Flat)<-5.);
    for(const FTransform Transform:{Side,FTransform(FRotator(17,31,84),FVector(100,-40,18),FVector(1.2,.8,1.1))})
    {
        double Oracle=JapanBikeSupport::InvalidGap;
        for(const FVector& Local:Vertices)
        {
            const FVector P=Transform.TransformPosition(Local);
            Oracle=FMath::Min(Oracle,P.Z-(.2*P.X-.1*P.Y));
        }
        const double Measured=JapanBikeSupport::Gap(Points,Transform,[](const FVector& P,double& Height)
            {Height=.2*P.X-.1*P.Y;return true;});
        TestTrue(TEXT("Steering, scale and slope use support under every point"),FMath::Abs(Oracle-Measured)<.1);
    }
    // On a slope, the minimum clearance need not belong to the lowest world-Z vertex.
    const TArray<FVector> SlopePoints={FVector(0,0,1),FVector(10,0,2)};
    TestEqual(TEXT("Each support point uses its own ground height"),
        JapanBikeSupport::Gap(SlopePoints,FTransform::Identity,[](const FVector& P,double& Height){Height=.5*P.X;return true;}),-3.);
    TestEqual(TEXT("Missing ground cannot silently pass"),JapanBikeSupport::Gap(Points,Side,
        [](const FVector&,double&){return false;}),JapanBikeSupport::InvalidGap);
    TestEqual(TEXT("Missing mesh cannot silently pass"),JapanBikeSupport::Gap({},Side,Flat),JapanBikeSupport::InvalidGap);
    TArray<FVector> Empty;
    TestFalse(TEXT("Empty hull source is rejected"),JapanBikeSupport::Build({},Empty));
    TestFalse(TEXT("Missing mesh is rejected"),JapanBikeSupport::Load(nullptr,Empty));
    for(const TCHAR* Name:{TEXT("/Game/Japan/Assets/BK_WheelFront.BK_WheelFront"),TEXT("/Game/Japan/Assets/BK_WheelRear.BK_WheelRear")})
    {
        auto* Mesh=LoadObject<UStaticMesh>(nullptr,Name);
        TestTrue(TEXT("Installed wheel retains CPU geometry for cooked support QA"),Mesh&&Mesh->bAllowCPUAccess);
        const double Began=FPlatformTime::Seconds();
        TestTrue(TEXT("Installed wheel builds a usable bounded support hull"),JapanBikeSupport::Load(Mesh,Empty));
        AddInfo(FString::Printf(TEXT("BikeSupport mesh=%s points=%d build_ms=%.3f"),Name,Empty.Num(),(FPlatformTime::Seconds()-Began)*1000.));
    }
    return true;
}
#endif
