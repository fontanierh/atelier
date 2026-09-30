#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "SkateRails.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "StaticMeshResources.h"
#include "TwoBoneIK.h"
#include "UObject/UObjectIterator.h"

namespace
{
    // Native left/up/forward metres -> UE forward/right/up centimetres (change handedness).
    FVector FromNative(const FVector& V) { return FVector(V.Z, -V.X, V.Y) * 100.; }
    FVector ToNative(const FVector& V) { return FVector(-V.Y, V.Z, V.X) * .01; }
    TSharedPtr<FJsonValue> Number(double V) { return MakeShared<FJsonValueNumber>(V); }
    TArray<TSharedPtr<FJsonValue>> VectorJSON(FVector V) { return {Number(V.X), Number(V.Y), Number(V.Z)}; }
    FVector VectorValue(const TArray<TSharedPtr<FJsonValue>>& A) { return A.Num() == 3 ? FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()) : FVector::ZeroVector; }
    FTransform MatrixValue(const TSharedPtr<FJsonValue>& Value)
    {
        const auto& A = Value->AsArray();
        if (A.Num() != 16) return FTransform::Identity;
        auto Axis = [&](int I) { return FVector(A[I+2]->AsNumber(), -A[I]->AsNumber(), A[I+1]->AsNumber()); };
        // Conjugate rotation by the axis mapping: local UE +Y is native -X as well.
        return FTransform(FMatrix(FPlane(Axis(8),0), FPlane(-Axis(0),0), FPlane(Axis(4),0), FPlane(Axis(12)*100.,1)));
    }
    FString Encode(const TSharedPtr<FJsonObject>& O)
    {
        FString Text; FJsonSerializer::Serialize(O.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
        return Text;
    }
    FString RuntimeFolder() { return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Data/SkateRuntime")); }
    FString TrickLabel(FString Name)
    {
        Name.RemoveFromStart(TEXT("ID_TRICK_"));
        for (const TCHAR* Family : {TEXT("GROUND_TRICK_"),TEXT("FLIP_"),TEXT("GRIND_"),TEXT("GRAB_")}) Name.RemoveFromStart(Family);
        TArray<FString> Words; Name.ParseIntoArray(Words,TEXT("_"),true);
        for (FString& Word : Words)
        {
            if (Word==TEXT("N")) Word=TEXT("Nollie");
            else if (Word!=TEXT("FS") && Word!=TEXT("BS")) { Word=Word.ToLower(); if (!Word.IsEmpty()) Word[0]=FChar::ToUpper(Word[0]); }
        }
        return FString::Join(Words,TEXT(" ")).Replace(TEXT("50 50"),TEXT("50-50"));
    }
    FString RuntimeBinary()
    {
        return RuntimeFolder() / TEXT("bin/atelier-skate-runtime")
#if PLATFORM_WINDOWS
            TEXT(".exe")
#endif
            ;
    }

    /** Snapshot nearby static collision. The native worker owns its narrow phase, BVH and contact solver. */
    bool ExportWorld(UWorld* World, ACharacter* Rider, FVector Centre, float Yaw, USkateRailSubsystem* Rails, FString& Path)
    {
        constexpr double Radius = 10000.;
        const FBox Region(Centre-FVector(Radius),Centre+FVector(Radius));
        TArray<TSharedPtr<FJsonValue>> Triangles, Lines;
        for (TObjectIterator<UStaticMeshComponent> It; It; ++It)
        {
            UStaticMeshComponent* C = *It;
            if (C->GetWorld()!=World || C->GetOwner()==Rider || !C->IsRegistered() || !C->IsCollisionEnabled() ||
                C->GetCollisionResponseToChannel(ECC_Pawn)!=ECR_Block || !C->Bounds.GetBox().Intersect(Region)) continue;
            UStaticMesh* Mesh=C->GetStaticMesh();
            if (!Mesh || !Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty()) continue;
            const FStaticMeshLODResources& LOD=Mesh->GetRenderData()->LODResources[0];
            if (!LOD.VertexBuffers.PositionVertexBuffer.GetVertexData() || LOD.VertexBuffers.PositionVertexBuffer.GetNumVertices()==0 || LOD.IndexBuffer.GetNumIndices()==0) continue;
            TArray<FTransform> Instances;
            if (auto* ISM=Cast<UInstancedStaticMeshComponent>(C))
            {
                for (int32 Index : ISM->GetInstancesOverlappingSphere(Centre,Radius,true))
                { FTransform T; if (ISM->GetInstanceTransform(Index,T,true)) Instances.Add(T); }
            }
            else Instances.Add(C->GetComponentTransform());
            const FIndexArrayView Indices=LOD.IndexBuffer.GetArrayView();
            for (const FTransform& T : Instances) for (int32 I=0; I+2<Indices.Num(); I+=3)
            {
                FVector P[3]; FBox Bounds(ForceInit);
                for (int32 K=0;K<3;++K) { P[K]=T.TransformPosition(FVector(LOD.VertexBuffers.PositionVertexBuffer.VertexPosition(Indices[I+K]))); Bounds+=P[K]; }
                if (!Bounds.Intersect(Region)) continue;
                FVector N=FVector::CrossProduct(P[1]-P[0],P[2]-P[0]);
                if (N.SizeSquared()<.0001) continue;
                const FVector Authored=T.TransformVectorNoScale(FVector(LOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(Indices[I])));
                if (FVector::DotProduct(N,Authored)<0) Swap(P[1],P[2]);
                Swap(P[1],P[2]); // The coordinate reflection reverses winding.
                TArray<TSharedPtr<FJsonValue>> Points;
                for (const FVector& Point : P) Points.Add(MakeShared<FJsonValueArray>(VectorJSON(ToNative(Point))));
                Triangles.Add(MakeShared<FJsonValueArray>(Points));
                if (Triangles.Num()>=500000) return false;
            }
        }
        if (Triangles.IsEmpty()) return false;
        if (Rails) for (const FSkateRail& Rail : Rails->Rails) if (Rail.Bounds.Intersect(Region) && Rail.Points.Num()>=2)
        {
            TArray<TSharedPtr<FJsonValue>> Points;
            for (const FVector& P : Rail.Points) Points.Add(MakeShared<FJsonValueArray>(VectorJSON(ToNative(P))));
            Lines.Add(MakeShared<FJsonValueArray>(Points));
        }
        auto Root=MakeShared<FJsonObject>(); Root->SetArrayField(TEXT("triangles"),Triangles); Root->SetArrayField(TEXT("rails"),Lines);
        Root->SetArrayField(TEXT("spawn"),VectorJSON(ToNative(Centre))); Root->SetNumberField(TEXT("heading"),-FMath::DegreesToRadians(Yaw));
        const FString Folder=RuntimeFolder()/TEXT("sessions"); IFileManager::Get().MakeDirectory(*Folder,true);
        Path=Folder/(FGuid::NewGuid().ToString()+TEXT(".json"));
        UE_LOG(LogTemp,Display,TEXT("SKATE retail collision: %d triangles, %d rails"),Triangles.Num(),Lines.Num());
        return FFileHelper::SaveStringToFile(Encode(Root),*Path,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    }
}

/** A retained process isolates native faults and keeps decoded banks resident between rides. */
class FSkateRuntime
{
public:
    FProcHandle Process;
    void *Read=nullptr,*Write=nullptr,*ErrorRead=nullptr;
    bool Ready=false,PendingActivation=false,AwaitingPose=false;
    float FrameTime=0;
    FString Buffer,State=TEXT("Loading skater"),Error,Trick;
    FVector CollisionCentre=FVector::ZeroVector,Spawn=FVector::ZeroVector,Velocity=FVector::ZeroVector;
    TOptional<FVector> PendingLaunch;
    float SpawnYaw=0,Score=0,ManualBalance=0;
    uint64 Tick=0;
    FTransform Root=FTransform::Identity,Camera=FTransform::Identity;
    float CameraFOV=0;
    TArray<FName> Names;
    TArray<FTransform> Reference,Bones;
    TArray<FString> Files;
    ~FSkateRuntime()
    {
        if (Process.IsValid())
        {
            SendSimple(TEXT("quit"));
            FPlatformProcess::ClosePipe(nullptr,Write); Write=nullptr;
            // No game state is stored in the worker. Ensure shutdown never leaves an orphan.
            if (FPlatformProcess::IsProcRunning(Process)) FPlatformProcess::TerminateProc(Process,true);
            FPlatformProcess::CloseProc(Process);
        }
        FPlatformProcess::ClosePipe(Read,Write); FPlatformProcess::ClosePipe(ErrorRead,nullptr);
        for (const FString& File : Files) IFileManager::Get().Delete(*File);
    }
    void Send(const TSharedPtr<FJsonObject>& O) { if (Write) FPlatformProcess::WritePipe(Write,Encode(O)); }
    void SendSimple(const TCHAR* Op) { auto O=MakeShared<FJsonObject>(); O->SetStringField(TEXT("op"),Op); Send(O); }
    void Activate(bool Goofy)
    {
        PendingActivation=true;
        if (!Ready) return;
        auto O=MakeShared<FJsonObject>(); O->SetStringField(TEXT("op"),TEXT("activate")); O->SetArrayField(TEXT("spawn"),VectorJSON(ToNative(Spawn)));
        O->SetNumberField(TEXT("heading"),-FMath::DegreesToRadians(SpawnYaw)); O->SetBoolField(TEXT("goofy"),Goofy);
        O->SetStringField(TEXT("difficulty"),GetDefault<USkateSettings>()->Difficulty); O->SetNumberField(TEXT("trucks"),GetDefault<USkateSettings>()->TruckTightness);
        Send(O); PendingActivation=false;
        if (PendingLaunch)
        {
            auto Launch=MakeShared<FJsonObject>(); Launch->SetStringField(TEXT("op"),TEXT("launch"));
            Launch->SetArrayField(TEXT("velocity"),VectorJSON(ToNative(*PendingLaunch))); Send(Launch); PendingLaunch.Reset();
        }
    }
    bool Poll()
    {
        const FString Errors=FPlatformProcess::ReadPipe(ErrorRead);
        if (!Errors.IsEmpty()) UE_LOG(LogTemp,Verbose,TEXT("SKATE retail: %s"),*Errors.Left(4096));
        Buffer+=FPlatformProcess::ReadPipe(Read);
        bool Changed=false; FString Line;
        int32 End;
        while (Buffer.FindChar('\n',End))
        {
            Line=Buffer.Left(End); Buffer.RightChopInline(End+1);
            TSharedPtr<FJsonObject> O;
            if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Line),O) || !O) continue;
            const FString Type=O->GetStringField(TEXT("type"));
            if (Type==TEXT("error")) { Error=O->GetStringField(TEXT("message")); continue; }
            if (Type!=TEXT("ready") && Type!=TEXT("pose")) continue;
            AwaitingPose=false;
            const auto& Matrices=O->GetArrayField(TEXT("bones"));
            if (Matrices.IsEmpty() || Matrices.Num()>256) { Error=TEXT("Invalid native skeleton"); continue; }
            Root=MatrixValue(O->Values[TEXT("root")]); Bones.Reset();
            for (const auto& M : Matrices) Bones.Add(MatrixValue(M));
            Velocity=FromNative(VectorValue(O->GetArrayField(TEXT("velocity")))); State=O->GetStringField(TEXT("state"));
            Trick=TrickLabel(O->GetStringField(TEXT("trick"))); Score=O->GetNumberField(TEXT("score")); Tick=uint64(O->GetNumberField(TEXT("tick")));
            ManualBalance=O->GetNumberField(TEXT("manual"));
            if (Root.ContainsNaN() || Velocity.ContainsNaN() || Bones.ContainsByPredicate([](const FTransform& T){return T.ContainsNaN();}))
            { Error=TEXT("Nonfinite native output"); continue; }
            if (Type==TEXT("ready"))
            {
                for (const auto& N : O->GetArrayField(TEXT("names"))) Names.Add(FName(N->AsString()));
                for (const auto& M : O->GetArrayField(TEXT("reference"))) Reference.Add(MatrixValue(M));
                Ready=Names.Num()==Bones.Num() && Reference.Num()==Bones.Num();
            }
            const TSharedPtr<FJsonObject>* Cam=nullptr;
            if (O->TryGetObjectField(TEXT("camera"),Cam))
            {
                const auto& B=(*Cam)->GetArrayField(TEXT("basis"));
                if (B.Num()==9)
                {
                    auto Axis=[&](int I){return FVector(B[I+2]->AsNumber(),-B[I]->AsNumber(),B[I+1]->AsNumber());};
                    Camera=FTransform(FRotationMatrix::MakeFromXZ(Axis(6),Axis(3)).ToQuat(),FromNative(VectorValue((*Cam)->GetArrayField(TEXT("position")))));
                    CameraFOV=(*Cam)->GetNumberField(TEXT("fov"));
                }
            }
            Changed=true;
        }
        if (Error.IsEmpty() && !FPlatformProcess::IsProcRunning(Process)) Error=TEXT("The skating worker stopped");
        return Changed;
    }
    FTransform Bone(FName Name) const
    {
        int32 I=Names.IndexOfByKey(Name); return Bones.IsValidIndex(I) ? Bones[I]*Root : Root;
    }
    FTransform Bind(FName Name) const
    {
        int32 I=Names.IndexOfByKey(Name); return Reference.IsValidIndex(I)?Reference[I]:FTransform::Identity;
    }
};

void USkateComponent::StartRetailRuntime()
{
    if (!GetDefault<USkateSettings>()->UseRetailRuntime || !FPaths::FileExists(RuntimeBinary()) ||
        !FPaths::FileExists(RuntimeFolder()/TEXT("assets/private/game.json"))) return;
    if (!RetailRuntime)
    {
        FString File;
        if (!ExportWorld(GetWorld(),Rider,Pos,Rot.Rotator().Yaw,RailSystem,File))
        { UE_LOG(LogTemp,Error,TEXT("SKATE retail: could not export nearby collision")); return; }
        RetailRuntime=MakeShared<FSkateRuntime>();
        RetailRuntime->Files.Add(File); RetailRuntime->CollisionCentre=Pos;
        void *ChildWrite=nullptr,*ChildRead=nullptr,*ChildError=nullptr;
        FPlatformProcess::CreatePipe(RetailRuntime->Read,ChildWrite);
        FPlatformProcess::CreatePipe(ChildRead,RetailRuntime->Write,true);
        FPlatformProcess::CreatePipe(RetailRuntime->ErrorRead,ChildError);
        const FString Args=FString::Printf(TEXT("\"%s\" \"%s\""),*(RuntimeFolder()/TEXT("assets")),*File);
        RetailRuntime->Process=FPlatformProcess::CreateProc(*RuntimeBinary(),*Args,false,true,true,nullptr,0,nullptr,ChildWrite,ChildRead,ChildError);
        FPlatformProcess::ClosePipe(ChildRead,ChildWrite); FPlatformProcess::ClosePipe(nullptr,ChildError);
        if (!RetailRuntime->Process.IsValid()) { RetailRuntime.Reset(); return; }
    }
    else if (FVector::DistSquared(Pos,RetailRuntime->CollisionCentre)>FMath::Square(6000.f))
    {
        FString File;
        if (!ExportWorld(GetWorld(),Rider,Pos,Rot.Rotator().Yaw,RailSystem,File)) { StowImmediately(); return; }
        RetailRuntime->Files.Add(File); RetailRuntime->CollisionCentre=Pos;
        auto Update=MakeShared<FJsonObject>(); Update->SetStringField(TEXT("op"),TEXT("world")); Update->SetStringField(TEXT("path"),File); RetailRuntime->Send(Update);
    }
    RetailRuntime->Spawn=Pos; RetailRuntime->SpawnYaw=Rot.Rotator().Yaw;
    RetailRuntime->Activate(bGoofy); bRetailActive=true; RetailPose.Reset();
}
void USkateComponent::SuspendRetailRuntime()
{
    if (RetailRuntime) { RetailRuntime->SendSimple(TEXT("suspend")); RetailRuntime->PendingActivation=false; RetailRuntime->PendingLaunch.Reset(); RetailRuntime->FrameTime=0; }
    bRetailActive=false; RetailPose.Reset();
}
void USkateComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    RetailRuntime.Reset(); Super::EndPlay(Reason);
}
void USkateComponent::LaunchRetail(const FVector& V)
{
    if (!bRetailActive || !RetailRuntime) return;
    if (!RetailRuntime->Ready || RetailRuntime->PendingActivation) { RetailRuntime->PendingLaunch=V; return; }
    auto O=MakeShared<FJsonObject>(); O->SetStringField(TEXT("op"),TEXT("launch")); O->SetArrayField(TEXT("velocity"),VectorJSON(ToNative(V))); RetailRuntime->Send(O);
}
void USkateComponent::ConfigureRetail()
{
    if (!RetailRuntime) return;
    auto O=MakeShared<FJsonObject>(); O->SetStringField(TEXT("op"),TEXT("configure")); O->SetBoolField(TEXT("goofy"),bGoofy);
    O->SetStringField(TEXT("difficulty"),GetDefault<USkateSettings>()->Difficulty); O->SetNumberField(TEXT("trucks"),GetDefault<USkateSettings>()->TruckTightness);
    RetailRuntime->Send(O);
}

bool USkateComponent::GetRetailCamera(FTransform& Out, float& FOV) const
{
    if (!bRetailActive || !RetailRuntime || !RetailRuntime->Ready || RetailRuntime->CameraFOV<=0) return false;
    Out=RetailRuntime->Camera; FOV=RetailRuntime->CameraFOV; return true;
}
FString USkateComponent::GetRetailState() const
{
    return bRetailActive && RetailRuntime ? FString::Printf(TEXT("%s tick=%llu"),*RetailRuntime->State,RetailRuntime->Tick) : FString();
}

void USkateComponent::StepRetailRuntime(float Dt)
{
    ReadInput(Dt);
    ComboFade=FMath::Max(0.f,ComboFade-Dt);
    if (!bRetailActive || !RetailRuntime) return;
    const bool Changed=RetailRuntime->Poll();
    if (!RetailRuntime->Error.IsEmpty())
    {
        UE_LOG(LogTemp,Error,TEXT("SKATE retail failed: %s"),*RetailRuntime->Error);
        StowImmediately(); RetailRuntime.Reset(); return;
    }
    if (!RetailRuntime->Ready) return;
    if (RetailRuntime->PendingActivation) { RetailRuntime->Activate(bGoofy); return; }
    RetailRuntime->FrameTime=FMath::Min(.1f,RetailRuntime->FrameTime+Dt);
    if (!RetailRuntime->AwaitingPose)
    {
    auto O=MakeShared<FJsonObject>(); O->SetStringField(TEXT("op"),TEXT("step")); O->SetNumberField(TEXT("dt"),RetailRuntime->FrameTime);
    int32 Buttons=(In.bPush?0x1000:0)|(In.bBrake?0x2000:0);
    int32 LeftTrigger=In.bGrabLeft?255:0,RightTrigger=In.bGrabRight?255:0;
    if (!bScripted && RiderApi && !RiderApi->IsSkateInputBlocked() && !RiderApi->IsSkateMouseFree())
        if (APlayerController* PC=Cast<APlayerController>(Rider->GetController()))
        {
            if (PC->IsInputKeyDown(EKeys::Gamepad_FaceButton_Left))
            {
                Buttons|=0x4000;
                if (!PC->IsInputKeyDown(EKeys::Gamepad_FaceButton_Bottom) && !PC->IsInputKeyDown(EKeys::W) && !PC->IsInputKeyDown(EKeys::Up)) Buttons&=~0x1000;
            }
            if (PC->IsInputKeyDown(EKeys::Gamepad_LeftShoulder)) Buttons|=0x100;
            if (PC->IsInputKeyDown(EKeys::Gamepad_RightShoulder)) Buttons|=0x200;
            if (PC->IsInputKeyDown(EKeys::Gamepad_LeftThumbstick)) Buttons|=0x40;
            if (PC->IsInputKeyDown(EKeys::Gamepad_RightThumbstick)) Buttons|=0x80;
            LeftTrigger=PC->IsInputKeyDown(EKeys::Q)?255:FMath::Clamp(FMath::RoundToInt(255*PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis)),0,255);
            RightTrigger=PC->IsInputKeyDown(EKeys::E)?255:FMath::Clamp(FMath::RoundToInt(255*PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis)),0,255);
        }
    O->SetNumberField(TEXT("buttons"),Buttons);
    auto Stick=[](FVector2D V){return TArray<TSharedPtr<FJsonValue>>{Number(FMath::RoundToInt(FMath::Clamp(V.X,-1.,1.)*32767)),Number(FMath::RoundToInt(FMath::Clamp(V.Y,-1.,1.)*32767))};};
    O->SetArrayField(TEXT("left"),Stick(In.bPowerslide?FVector2D(In.Left.X,-1):In.Left)); O->SetArrayField(TEXT("right"),Stick(In.Right));
    O->SetArrayField(TEXT("triggers"),{Number(LeftTrigger),Number(RightTrigger)}); RetailRuntime->Send(O);
    RetailRuntime->AwaitingPose=true; RetailRuntime->FrameTime=0;
    }
    if (!Changed) return;
    const FString& S=RetailRuntime->State;
    const ESkateMode NewMode=S.Contains(TEXT("Wipeout"))?ESkateMode::Bail:S.Contains(TEXT("Grind"))?ESkateMode::Grind:
        S.Contains(TEXT("Air"))?ESkateMode::Air:ESkateMode::Ground;
    if (NewMode!=Mode)
    {
        if (NewMode==ESkateMode::Bail) { ++Bails; PlayCue(TEXT("clatter"),1,1); }
        if (NewMode==ESkateMode::Air && Mode==ESkateMode::Ground) PlayCue(TEXT("pop"),1,1);
        if (NewMode==ESkateMode::Ground && Mode==ESkateMode::Air) { ++Landed; PlayCue(TEXT("land"),.8,1); }
        if (NewMode==ESkateMode::Grind) ++Grinds;
        ++Serial; Mode=NewMode;
    }
    const FTransform DeckWorld=RetailRuntime->Bone(TEXT("SKATEBOARD_ROOT"));
    Rot=DeckWorld.GetRotation(); Pos=DeckWorld.GetLocation()-Rot.GetUpVector()*9.05; Vel=RetailRuntime->Velocity;
    // Contact jitter at rest must not alternate the stance or the HUD every frame.
    const float Along=FVector::DotProduct(Vel,Rot.GetForwardVector());
    if (FMath::Abs(Along)>15.f) bFakie=Along<0;
    RailSpeed=Vel.Size();
    bManual=Mode==ESkateMode::Ground && FMath::Abs(RetailRuntime->ManualBalance)>.0001f;
    bNoseManual=bManual && RetailRuntime->Trick.Contains(TEXT("Nose"));
    bPushing=In.bPush; bBraking=In.bBrake; bPowerslide=S==TEXT("SlideGround");
    bSlide=S==TEXT("GrindBoardslide") || S==TEXT("GrindTipslide") || S==TEXT("GrindDarkslide");
    if (ShownCombo!=RetailRuntime->Trick || Score!=FMath::RoundToInt(RetailRuntime->Score) ||
        Mode==ESkateMode::Air || Mode==ESkateMode::Grind || bManual) ComboFade=1.5f;
    ShownCombo=RetailRuntime->Trick; Score=FMath::RoundToInt(RetailRuntime->Score); LastTrickName=FName(*ShownCombo);
    Rider->SetActorLocationAndRotation(RetailRuntime->Root.GetLocation()+FVector(0,0,BodyLift),RetailRuntime->Root.GetRotation(),false,nullptr,ETeleportType::TeleportPhysics);
    Movement()->Velocity=Vel;
    BoardRoot->SetWorldTransform(DeckWorld); Deck->SetRelativeTransform(FTransform::Identity);
    const TCHAR* TruckNames[]={TEXT("TRUCK_FRONT"),TEXT("TRUCK_BACK")};
    const TCHAR* WheelNames[]={TEXT("RIGHT_WHEELFRONT"),TEXT("LEFT_WHEELFRONT"),TEXT("RIGHT_WHEELBACK"),TEXT("LEFT_WHEELBACK")};
    // Fit the host board's mesh pivots to the source rig; preserve the native truck lean and wheel spin.
    const FTransform DeckBind=RetailRuntime->Bind(TEXT("SKATEBOARD_ROOT"));
    for (int32 I=0;I<Trucks.Num() && I<2;++I)
    {
        const FTransform TruckBind=RetailRuntime->Bind(TruckNames[I]);
        const FVector A=RetailRuntime->Bind(WheelNames[I*2]).GetLocation(),B=RetailRuntime->Bind(WheelNames[I*2+1]).GetLocation();
        const FVector Axle=(A+B)*.5;
        const float Height=FMath::Max(.1f,float(DeckBind.GetLocation().Z-1.2-Axle.Z));
        const FTransform Fit(FQuat(FVector::UpVector,I==0?0.f:PI)*DeckBind.GetRotation(),
            Axle+DeckBind.GetRotation().GetUpVector()*Height,FVector(1,FVector::Distance(A,B)/18.6,Height/5.15));
        Trucks[I]->SetWorldTransform(Fit.GetRelativeTransform(TruckBind)*RetailRuntime->Bone(TruckNames[I]));
    }
    for (int32 I=0;I<Wheels.Num() && I<4;++I)
    {
        const FTransform WheelBind=RetailRuntime->Bind(WheelNames[I]);
        // physicswheels/default/WheelRadius is 0.031 m; the host mesh radius is 2.65 cm.
        const FTransform Fit(DeckBind.GetRotation(),WheelBind.GetLocation(),FVector(3.1/2.65));
        Wheels[I]->SetWorldTransform(Fit.GetRelativeTransform(WheelBind)*RetailRuntime->Bone(WheelNames[I]));
    }
    RetargetRetailPose();
    // Rebuild before leaving the snapshot's inner 60 m; construction occurs in the worker.
    if (FVector::DistSquared(Pos,RetailRuntime->CollisionCentre)>FMath::Square(6000.f))
    {
        FString File;
        if (ExportWorld(GetWorld(),Rider,Pos,Rot.Rotator().Yaw,RailSystem,File))
        {
            RetailRuntime->Files.Add(File); RetailRuntime->CollisionCentre=Pos;
            auto Update=MakeShared<FJsonObject>(); Update->SetStringField(TEXT("op"),TEXT("world")); Update->SetStringField(TEXT("path"),File); RetailRuntime->Send(Update);
        }
    }
}

void USkateComponent::RetargetRetailPose()
{
    USkeletalMeshComponent* Mesh=Rider->GetMesh();
    if (!Mesh || !Mesh->GetSkeletalMeshAsset()) return;
    const FReferenceSkeleton& Ref=Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
    struct Mapping { const TCHAR* Target; const TCHAR* Source; const TCHAR* Child; };
    static const Mapping Map[]={
        {TEXT("pelvis"),TEXT("HIPS"),TEXT("SPINE")},{TEXT("spine"),TEXT("SPINE"),TEXT("SPINE1")},
        {TEXT("spine_mid"),TEXT("SPINE1"),TEXT("SPINE3")},{TEXT("chest"),TEXT("SPINE3"),TEXT("NECK")},
        {TEXT("neck"),TEXT("NECK"),TEXT("HEAD")},{TEXT("head"),TEXT("HEAD"),nullptr},
        {TEXT("clavicle_L"),TEXT("LEFTSHOULDER"),TEXT("LEFTARM")},{TEXT("upperarm_L"),TEXT("LEFTARM"),TEXT("LEFTFOREARM")},
        {TEXT("forearm_L"),TEXT("LEFTFOREARM"),TEXT("LEFTHAND")},{TEXT("hand_L"),TEXT("LEFTHAND"),nullptr},
        {TEXT("clavicle_R"),TEXT("RIGHTSHOULDER"),TEXT("RIGHTARM")},{TEXT("upperarm_R"),TEXT("RIGHTARM"),TEXT("RIGHTFOREARM")},
        {TEXT("forearm_R"),TEXT("RIGHTFOREARM"),TEXT("RIGHTHAND")},{TEXT("hand_R"),TEXT("RIGHTHAND"),nullptr},
        {TEXT("thigh_L"),TEXT("LEFTUPLEG"),TEXT("LEFTLEG")},{TEXT("shin_L"),TEXT("LEFTLEG"),TEXT("LEFTFOOT")},
        {TEXT("foot_L"),TEXT("LEFTFOOT"),TEXT("LEFTTOEBASE")},{TEXT("toe_L"),TEXT("LEFTTOEBASE"),nullptr},
        {TEXT("thigh_R"),TEXT("RIGHTUPLEG"),TEXT("RIGHTLEG")},{TEXT("shin_R"),TEXT("RIGHTLEG"),TEXT("RIGHTFOOT")},
        {TEXT("foot_R"),TEXT("RIGHTFOOT"),TEXT("RIGHTTOEBASE")},{TEXT("toe_R"),TEXT("RIGHTTOEBASE"),nullptr}
    };
    TArray<FTransform> Bind,Output; Bind.SetNum(Ref.GetNum()); Output.SetNum(Ref.GetNum()); RetailPose.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I) { int32 P=Ref.GetParentIndex(I); Bind[I]=P>=0?Ref.GetRefBonePose()[I]*Bind[P]:Ref.GetRefBonePose()[I]; }
    auto Source=[&](const TCHAR* N){return RetailRuntime->Names.IndexOfByKey(FName(N));};
    const int32 Hip=Ref.FindBoneIndex(TEXT("pelvis")),Foot=Ref.FindBoneIndex(TEXT("foot_L")),SHip=Source(TEXT("HIPS")),SFoot=Source(TEXT("LEFTFOOT"));
    if (Hip<0 || Foot<0 || SHip<0 || SFoot<0) { RetailPose.Reset(); return; }
    const float Ratio=(Bind[Hip].GetLocation().Z-Bind[Foot].GetLocation().Z)*Mesh->GetComponentScale().Z /
        FMath::Max(1.,RetailRuntime->Reference[SHip].GetLocation().Z-RetailRuntime->Reference[SFoot].GetLocation().Z);
    const FTransform RootToMesh=RetailRuntime->Root.GetRelativeTransform(Mesh->GetComponentTransform());
    // Preserve sole height: the source ankle is much farther above its sole than this character's ankle.
    const float SoleOffset=(Bind[Foot].GetLocation().Z-Bind[0].GetLocation().Z)*Mesh->GetComponentScale().Z -
        (RetailRuntime->Reference[SFoot].GetLocation().Z-RetailRuntime->Reference[0].GetLocation().Z)*Ratio;
    auto InMesh=[&](FTransform T){ T.ScaleTranslation(Ratio); T.AddToTranslation(FVector(0,0,SoleOffset)); return T*RootToMesh; };
    auto Frame=[](FVector Left,FVector Right,FVector Head,FVector HipP) { FVector Up=(Head-HipP).GetSafeNormal(); return FRotationMatrix::MakeFromXZ(FVector::CrossProduct(Right-Left,Up).GetSafeNormal(),Up).ToQuat(); };
    const int32 TL=Ref.FindBoneIndex(TEXT("thigh_L")),TR=Ref.FindBoneIndex(TEXT("thigh_R")),TH=Ref.FindBoneIndex(TEXT("head"));
    if (TL<0 || TR<0 || TH<0 || Source(TEXT("LEFTUPLEG"))<0 || Source(TEXT("RIGHTUPLEG"))<0 || Source(TEXT("HEAD"))<0)
    { RetailPose.Reset(); return; }
    // Imported meshes can carry a 180-degree facing correction. Joint names alone cannot recover it.
    const FQuat TargetFrame=FRotationMatrix::MakeFromXZ(SavedMeshRotation.UnrotateVector(FVector::ForwardVector),
        (Bind[TH].GetLocation()-Bind[Hip].GetLocation()).GetSafeNormal()).ToQuat();
    const FQuat Base=Frame(InMesh(RetailRuntime->Reference[Source(TEXT("LEFTUPLEG"))]).GetLocation(),InMesh(RetailRuntime->Reference[Source(TEXT("RIGHTUPLEG"))]).GetLocation(),InMesh(RetailRuntime->Reference[Source(TEXT("HEAD"))]).GetLocation(),InMesh(RetailRuntime->Reference[SHip]).GetLocation()) * TargetFrame.Inverse();
    TArray<FQuat> Fits; Fits.Init(Base,Ref.GetNum());
    TArray<FVector> Targets; Targets.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I)
    {
        const int32 Parent=Ref.GetParentIndex(I); const Mapping* Match=nullptr;
        for (const Mapping& M : Map) if (Ref.GetBoneName(I)==FName(M.Target)) { Match=&M; break; }
        if (Match && Source(Match->Source)>=0)
        {
            const int32 S=Source(Match->Source); const FTransform SB=InMesh(RetailRuntime->Reference[S]),SP=InMesh(RetailRuntime->Bones[S]);
            FQuat FitRotation=Base;
            // Hands and toes inherit the limb's reference alignment; a body-facing frame would twist them.
            if (!Match->Child && Parent>=0 && FCString::Strcmp(Match->Target,TEXT("head"))!=0) FitRotation=Fits[Parent];
            if (Match->Child && Source(Match->Child)>=0)
            {
                int32 Child=INDEX_NONE;
                for (const Mapping& M : Map) if (FCString::Strcmp(M.Source,Match->Child)==0) { Child=Ref.FindBoneIndex(M.Target); break; }
                if (Child>=0)
                {
                    FVector A=Base.RotateVector(Bind[Child].GetLocation()-Bind[I].GetLocation());
                    FVector B=InMesh(RetailRuntime->Reference[Source(Match->Child)]).GetLocation()-SB.GetLocation();
                    // The source ankle/toe height difference is anatomical, not a toe-down foot rotation.
                    if (FCString::Strncmp(Match->Target,TEXT("foot_"),5)==0)
                    {
                        const FVector Up=RootToMesh.GetRotation().GetUpVector();
                        A=FVector::VectorPlaneProject(A,Up); B=FVector::VectorPlaneProject(B,Up);
                    }
                    FitRotation=FQuat::FindBetweenNormals(A.GetSafeNormal(),B.GetSafeNormal())*Base;
                }
            }
            const FTransform Fit(FitRotation,SB.GetLocation()-FitRotation.RotateVector(Bind[I].GetLocation()));
            Fits[I]=FitRotation;
            Output[I]=Bind[I]*Fit*SB.Inverse()*SP;
            Output[I].SetScale3D(Bind[I].GetScale3D());
        }
        else Output[I]=Parent>=0?Ref.GetRefBonePose()[I]*Output[Parent]:Ref.GetRefBonePose()[I];
        Targets[I]=Output[I].GetLocation();
        // Transfer motion, not adult bone lengths. In particular the source has an extra spine segment.
        if (Parent>=0 && I!=Hip)
            Output[I].SetLocation(Output[Parent].TransformPosition(Ref.GetRefBonePose()[I].GetLocation()));
    }
    // Preserve the source foot contacts while solving with this character's actual thigh/shin lengths.
    for (const TCHAR* Side : {TEXT("L"),TEXT("R")})
    {
        const int32 A=Ref.FindBoneIndex(FName(*FString::Printf(TEXT("thigh_%s"),Side)));
        const int32 B=Ref.FindBoneIndex(FName(*FString::Printf(TEXT("shin_%s"),Side)));
        const int32 C=Ref.FindBoneIndex(FName(*FString::Printf(TEXT("foot_%s"),Side)));
        if (A<0 || B<0 || C<0) continue;
        const FQuat FootTurn=Output[C].GetRotation();
        const FVector Pole=Targets[B]+(Targets[B]-(Targets[A]+Targets[C])*.5)*2;
        AnimationCore::SolveTwoBoneIK(Output[A],Output[B],Output[C],Pole,Targets[C],false,1.f,1.f);
        Output[C].SetRotation(FootTurn);
        // The toe remains its authored distance from the ankle; it must not stretch through the deck.
        for (int32 I=C+1;I<Ref.GetNum();++I)
            if (Ref.GetParentIndex(I)==C) Output[I]=Ref.GetRefBonePose()[I]*Output[C];
    }
    for (int32 I=0;I<Ref.GetNum();++I)
    {
        const int32 Parent=Ref.GetParentIndex(I);
        RetailPose[I]=Parent>=0?Output[I].GetRelativeTransform(Output[Parent]):Output[I];
        RetailPose[I].NormalizeRotation();
    }
}
