#include "WandererCharacter.h"
#include "AtelierExit.h"
#include "SkateComponent.h"
#include "JapanWorld.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Engine.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "DynamicResolutionState.h"
#include "SceneTexturesConfig.h"
#include "RenderingThread.h"
#include "PixelFormat.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/IConsoleManager.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "ProfilingDebugging/CsvProfiler.h"

CSV_DEFINE_CATEGORY(JapanBenchmark,true);

// Read the actual render-thread allocation after each condition has settled,
// rather than assuming that a requested format survived platform/alpha fallback.
static void LogBenchmarkSceneFormat(int32 Phase)
{
    ENQUEUE_RENDER_COMMAND(JapanBenchmarkSceneFormat)([Phase](FRHICommandListImmediate&)
    {
        const auto& Config=FSceneTexturesConfig::Get();
        UE_LOG(LogTemp,Display,TEXT("BENCHMARK buffer phase=%d format=%s bytes=%d extent=%dx%d"),
            Phase,GPixelFormats[Config.ColorFormat].Name,GPixelFormats[Config.ColorFormat].BlockBytes,
            Config.Extent.X,Config.Extent.Y);
    });
}

// A real-time capture, with no screenshots or file writes inside the measured
// interval. It runs only with -benchmarkview=spawn|forest|coast|traverse.
void AWandererCharacter::AdvanceBenchmark(float Dt)
{
    if (bBenchmarkFinished) return;
    if (BenchmarkTime == 0.f)
    {
        FParse::Value(FCommandLine::Get(),TEXT("benchmarkbefore="),BenchmarkCompareBefore);
        FParse::Value(FCommandLine::Get(),TEXT("benchmarkafter="),BenchmarkCompareAfter);
        if (!BenchmarkCompareAfter.IsEmpty())
        {
            TArray<FString> Commands; BenchmarkCompareBefore.ParseIntoArray(Commands,TEXT(","));
            for (const FString& Command:Commands) CastChecked<APlayerController>(Controller)->ConsoleCommand(Command,true);
        }
        if (FParse::Param(FCommandLine::Get(),TEXT("benchmarkhidehud")))
            if (auto* PC = Cast<APlayerController>(Controller); PC && PC->GetHUD()) PC->GetHUD()->bShowHUD = false;
        if (BenchmarkView == TEXT("north_overview"))
        {
            // The reconciled mountain review camera, measured in real time.
            SetActorLocation(AJapanWorld::ToUE(985,230,28)+FVector(0,0,100),false,nullptr,ETeleportType::TeleportPhysics);
            const FVector Camera=AJapanWorld::ToUE(920,110,95);
            const FVector Focus=AJapanWorld::ToUE(900,650,110);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Camera,(Focus-Camera).Rotation());
            FollowCamera->SetFieldOfView(65);
        }
        if (BenchmarkView == TEXT("park") || BenchmarkView == TEXT("station"))
        {
            const bool Park=BenchmarkView == TEXT("park");
            SetActorLocation(AJapanWorld::ToUE(Park?1030:1185,Park?284:263,Park?32.425:30.5)+FVector(0,0,100),false,nullptr,ETeleportType::TeleportPhysics);
            const FVector Camera=Park?AJapanWorld::ToUE(980,239,54):AJapanWorld::ToUE(1185,250,35);
            const FVector Focus=Park?AJapanWorld::ToUE(1040,285,31):AJapanWorld::ToUE(1185,290,35);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Camera,(Focus-Camera).Rotation());
            FollowCamera->SetFieldOfView(70);
        }
        if (BenchmarkView == TEXT("harbor"))
        {
            const FVector Camera=AJapanWorld::ToUE(620,-116,5);
            const FVector Focus=AJapanWorld::ToUE(665,-168,2);
            SetActorLocation(AJapanWorld::ToUE(630,-116,4)+FVector(0,0,100),false,nullptr,ETeleportType::TeleportPhysics);
            GetMesh()->SetVisibility(false,true);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Camera,(Focus-Camera).Rotation());
            FollowCamera->SetFieldOfView(65);
        }
        if (BenchmarkView == TEXT("lake"))
        {
            // The forest-lake still camera, so water material work can be priced in real time.
            SetActorLocation(AJapanWorld::ToUE(-110,222,83)+FVector(0,0,100),false,nullptr,ETeleportType::TeleportPhysics);
            const FVector Camera=AJapanWorld::ToUE(-110,222,83);
            const FVector Focus=AJapanWorld::ToUE(-76,233,76);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Camera,(Focus-Camera).Rotation());
            FollowCamera->SetFieldOfView(72);
        }
        if (BenchmarkView == TEXT("arcade") || BenchmarkView == TEXT("plaza") || BenchmarkView == TEXT("city"))
        {
            // Same ground-level cameras as the accepted art review; no aerial stand-in
            // for the city walking budget. The separate road_walk view measures motion.
            const bool Arcade=BenchmarkView==TEXT("arcade"), Plaza=BenchmarkView==TEXT("plaza");
            const FVector Camera=Arcade?AJapanWorld::ToUE(635,75,17):Plaza?AJapanWorld::ToUE(681,138,22.2):AJapanWorld::ToUE(860,233,30.2);
            const FVector Focus=Arcade?AJapanWorld::ToUE(702,75,17):Plaza?AJapanWorld::ToUE(730,175,26):AJapanWorld::ToUE(990,233,30.2);
            SetActorLocation(Camera+FVector(0,0,200),false,nullptr,ETeleportType::TeleportPhysics);
            GetMesh()->SetVisibility(false,true);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Camera,(Focus-Camera).Rotation());
            FollowCamera->SetFieldOfView(70);
        }
        if (BenchmarkView == TEXT("portrait"))
        {
            const FVector Focus = GetActorLocation()+FVector(0,0,35);
            const FVector Camera = Focus+GetActorForwardVector()*210.f+GetActorRightVector()*100.f+FVector(0,0,10);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Camera,(Focus-Camera).Rotation());
        }
        if (BenchmarkView == TEXT("custom"))
        {
            // Freeze a real traversal hotspot without replacing world-shot exports.
            // This is a scenery diagnostic, not a replacement for moving-character QA.
            FString CameraText; TArray<FString> Values;
            FParse::Value(FCommandLine::Get(),TEXT("benchmarkcamera="),CameraText,false);
            CameraText.ParseIntoArray(Values,TEXT(","),false);
            double V[6] = {};
            bool Valid = Values.Num()==6;
            if (Valid) for (int32 I=0;I<6;++I)
                Valid &= LexTryParseString(V[I],*Values[I]) && FMath::IsFinite(V[I]);
            if (!Valid || V[5]<5. || V[5]>170.)
            {
                UE_LOG(LogTemp,Error,TEXT("Custom benchmark requires finite X,Y,Z,Pitch,Yaw,FOV; FOV 5..170"));
                AtelierRequestExit(2); return;
            }
            const FVector Camera(V[0],V[1],V[2]);
            SetActorLocation(Camera+FVector(0,0,200),false,nullptr,ETeleportType::TeleportPhysics);
            GetMesh()->SetVisibility(false,true);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Camera,FRotator(V[3],V[4],0));
            PreferredFOV=V[5];
            FollowCamera->SetFieldOfView(PreferredFOV);
            UE_LOG(LogTemp,Display,TEXT("BENCHMARK custom camera: %s (player hidden)"),*CameraText);
        }
        if (BenchmarkView == TEXT("forest") || BenchmarkView == TEXT("coast") || BenchmarkView == TEXT("village"))
        {
            const int32 Index = BenchmarkView == TEXT("village") ? 17 : (BenchmarkView == TEXT("forest") ? 4 : 11);
            if (!Landscape->Shots.IsValidIndex(Index))
            {
                UE_LOG(LogTemp,Error,TEXT("Benchmark view missing from world export"));
                AtelierRequestExit(2); return;
            }
            const FWorldShot& Shot = Landscape->Shots[Index];
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FollowCamera->SetWorldLocationAndRotation(Shot.Location,Shot.Rotation);
        }
        if (BenchmarkView == TEXT("road_walk"))
        {
            GetRoadSteering();
            if (SkateReviewRoad.Num() < 2)
            { AtelierRequestExit(2); return; }
            int32 RequestedIndex=0;FParse::Value(FCommandLine::Get(),TEXT("benchmarkroadindex="),RequestedIndex);
            const int32 Start=FMath::Clamp(RequestedIndex,0,SkateReviewRoad.Num()-2);
            SetActorLocation(SkateReviewRoad[Start]+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+8),false,nullptr,ETeleportType::TeleportPhysics);
            ReviewForward = (SkateReviewRoad[Start+1]-SkateReviewRoad[Start]).GetSafeNormal2D();
            SetActorRotation(ReviewForward.Rotation());
            GetCharacterMovement()->StopMovementImmediately();
            Controller->SetControlRotation(FRotator(-12.f,ReviewForward.Rotation().Yaw,0.f));
        }
        UE_LOG(LogTemp,Display,TEXT("BENCHMARK warmup: %s, %.1f measured seconds"),*BenchmarkView,BenchmarkSeconds);
    }
    const float Previous = BenchmarkTime;
    BenchmarkTime += Dt;
    constexpr float Warmup = 8.f;
    if (Previous < 6.f && BenchmarkTime >= 6.f && !BenchmarkDirectory.IsEmpty())
    {
        FScreenshotRequest::RequestScreenshot(BenchmarkDirectory/TEXT("view.png"),false,false);
        LogBenchmarkSceneFormat(0);
    }
    if (!bBenchmarkCapturing && BenchmarkTime >= Warmup)
    {
        for (const TCHAR* Name : {TEXT("r.ScreenPercentage"),TEXT("r.VelocityOutputPass"),TEXT("r.EarlyZPass"),
             TEXT("r.EarlyZPassOnlyMaterialMasking"),TEXT("r.StencilForLODDither"),TEXT("r.InstanceCulling.OcclusionCull"),
             TEXT("sg.GlobalIlluminationQuality"),TEXT("r.Lumen.FinalGatherMethod"),TEXT("r.Shadow.CSM.MaxCascades"),
             TEXT("r.Shadow.MaxCSMResolution"),TEXT("r.Shadow.DistanceScale"),TEXT("r.DistanceFieldShadowing"),TEXT("t.MaxFPS"),
             TEXT("r.DynamicRes.OperationMode"),TEXT("r.DynamicRes.MinScreenPercentage"),TEXT("r.DynamicRes.MaxScreenPercentage"),
             TEXT("r.DynamicRes.FrameTimeBudget"),TEXT("foliage.LODDistanceScale"),TEXT("r.AntiAliasingMethod"),
             TEXT("r.TSR.History.ScreenPercentage"),TEXT("r.TSR.History.UpdateQuality"),TEXT("r.TSR.ThinGeometryDetection"),
             TEXT("r.TSR.ThinGeometryDetection.Coverage.ShadingRange"),TEXT("r.TSR.RejectionAntiAliasingQuality")})
            if (auto* V = IConsoleManager::Get().FindConsoleVariable(Name))
                UE_LOG(LogTemp,Display,TEXT("BENCHMARK setting %s=%s"),Name,*V->GetString());
        FCsvProfiler::Get()->BeginCapture();
        bBenchmarkCapturing = true;
        SkateReviewStuckSince=-1.; // Warmup was intentionally stationary, not a route stall.
    }
    if (!bBenchmarkCapturing) return;
    const float T = BenchmarkTime-Warmup;
    const bool bCompare=!BenchmarkCompareAfter.IsEmpty();
    constexpr float CompareSettle=8.f;
    const int32 ComparePhase=bCompare?FMath::Min(5,FMath::FloorToInt((T+CompareSettle)/(BenchmarkSeconds+CompareSettle))):0;
    const float PhaseSeconds=bCompare?T-ComparePhase*(BenchmarkSeconds+CompareSettle)+CompareSettle:T;
    if (bCompare && ComparePhase!=BenchmarkComparePhase)
    {
        BenchmarkComparePhase=ComparePhase;
        const FString CommandsText=ComparePhase%2?BenchmarkCompareAfter:BenchmarkCompareBefore;
        TArray<FString> Commands; CommandsText.ParseIntoArray(Commands,TEXT(","));
        for (const FString& Command:Commands) CastChecked<APlayerController>(Controller)->ConsoleCommand(Command,true);
        UE_LOG(LogTemp,Display,TEXT("BENCHMARK comparison phase %d: %s"),ComparePhase,*CommandsText);
    }
    if (bCompare && ComparePhase>0 && PhaseSeconds>=3.f && PhaseSeconds<CompareSettle && BenchmarkCompareScreenshot!=ComparePhase)
    {
        // Screenshot and settling frames are explicitly excluded from the summaries.
        FScreenshotRequest::RequestScreenshot(BenchmarkDirectory/FString::Printf(TEXT("phase_%d.png"),ComparePhase),false,false);
        BenchmarkCompareScreenshot=ComparePhase;
        LogBenchmarkSceneFormat(ComparePhase);
    }
    CSV_CUSTOM_STAT(JapanBenchmark,Phase,ComparePhase,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,Measured,!bCompare || PhaseSeconds>=CompareSettle+.2f ? 1:0,ECsvCustomStatOp::Set);
    if (BenchmarkView == TEXT("road_walk"))
    {
        // Real character movement and collision, at a steady run. No fixed timestep,
        // transform playback or screenshots inside the timed interval.
        // The new character maps the retired jog toggle to Walk. Exercise its
        // actual Run (slowed Sprint) so the route and recovery timer agree.
        bWalk=false; bJog=false; bSprintHeld=false;
        ReviewForward=FRotator(0,GetActorRotation().Yaw+GetRoadSteering()*120.f*Dt,0).Vector();
        MoveIntent=FVector2D(0.f,1.f);
        const FRotator Target(-12.f,ReviewForward.Rotation().Yaw,0.f);
        Controller->SetControlRotation(FMath::RInterpTo(Controller->GetControlRotation(),Target,Dt,5.f));
    }
    if (BenchmarkView == TEXT("traverse"))
    {
        MoveIntent.Y = 1.f;
        bWalk = T < 5.f;
        bJog = T >= 5.f && T < 10.f;
        const float Orbit = T < 10.f ? 110.f*FMath::Sin(T*PI/10.f) : 0.f;
        Controller->SetControlRotation(FRotator(-8.f,ReviewForward.Rotation().Yaw+Orbit,0.f));
        if (Previous-Warmup < 16.f && T >= 16.f) RequestJump(FInputActionValue());
    }
    const FVector P = GetActorLocation();
    const FVector C = FollowCamera->GetComponentLocation();
    const FRotator R = FollowCamera->GetComponentRotation();
    CSV_CUSTOM_STAT(JapanBenchmark,Seconds,T,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,Speed,GetVelocity().Size2D(),ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,Skating,SkateRide->IsRiding()?1:0,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,Falling,GetCharacterMovement()->IsFalling()?1:0,ECsvCustomStatOp::Set);
    // Route progress, so a traversal claim can be checked against waypoints rather than a timer.
    CSV_CUSTOM_STAT(JapanBenchmark,RoadIndex,SkateReviewIndex,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,RoadSamples,SkateReviewRoad.Num(),ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,RoadTurns,SkateReviewTurns,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,RoadRecoveries,SkateReviewRecoveries,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,PlayerX,P.X,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,PlayerY,P.Y,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,PlayerZ,P.Z,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,CameraX,C.X,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,CameraY,C.Y,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,CameraZ,C.Z,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,CameraYaw,R.Yaw,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,CameraPitch,R.Pitch,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,CameraFOV,FollowCamera->FieldOfView,ECsvCustomStatOp::Set);
    FDynamicResolutionStateInfos Resolution;
    GEngine->GetDynamicResolutionCurrentStateInfos(Resolution);
    const bool bDynamic = Resolution.Status == EDynamicResolutionStatus::Enabled;
    const float ScreenPercentage = bDynamic
        ? 100.f*Resolution.ResolutionFractionApproximations[GDynamicPrimaryResolutionFraction]
        : IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage"))->GetFloat();
    CSV_CUSTOM_STAT(JapanBenchmark,DynamicResolution,bDynamic?1:0,ECsvCustomStatOp::Set);
    CSV_CUSTOM_STAT(JapanBenchmark,ScreenPercentageApprox,ScreenPercentage,ECsvCustomStatOp::Set);
    if (T >= (bCompare?6.f*BenchmarkSeconds+5.f*CompareSettle:BenchmarkSeconds))
    {
        MoveIntent = FVector2D::ZeroVector;
        FCsvProfiler::Get()->EndCapture();
        bBenchmarkFinished = true;
        UE_LOG(LogTemp,Display,TEXT("BENCHMARK COMPLETE"));
    }
}
