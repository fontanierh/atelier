#include "GondolaService.h"
#include "AtelierData.h"
#include "JapanNetwork.h"
#include "LiveLibrary.h"
#include "WandererCharacter.h"
#include "TransportAudio.h"
#include "Algo/BinarySearch.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#if WITH_EDITOR
#include "StaticMeshResources.h"
#include "Serialization/JsonWriter.h"
#endif
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Math/RotationMatrix.h"
#include "Misc/Paths.h"
#include "Net/UnrealNetwork.h"
#include "Serialization/JsonSerializer.h"

/** @cc [owner:fontanierh,label:correctness] gondola-native-logical-rope-bounds
 * Every bounded rope child MUST retain its complete original three-LOD logical
 * box and true sphere, measured from actual final native PositionVertexBuffers.
 * No AABB-diagonal sphere, CPU-access setting change or class fallback is allowed.
 * Missing buffers, mismatched family membership and nonfinite bounds MUST refuse. */
FString UGondolaRopeMeshComponent::FinishLogicalRope(const FString& Parent, const TArray<UStaticMesh*>& Parts)
{
#if WITH_EDITOR
    if (Parent.IsEmpty() || Parts.IsEmpty() || Parts.Num() > 8) return {};
    TArray<FString> Family;
    TSet<UStaticMesh*> Seen;
    for (UStaticMesh* Mesh : Parts)
    {
        if (!Mesh || Seen.Contains(Mesh) || !Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.Num() != 3) return {};
        Seen.Add(Mesh); Family.Add(Mesh->GetPathName());
    }
    FBoxSphereBounds::Builder Bounds;
    for (int32 Lod = 0; Lod < 3; ++Lod)
    {
        FBox3f Box(ForceInit);
        for (const UStaticMesh* Mesh : Parts)
        {
            const auto& Buffer = Mesh->GetRenderData()->LODResources[Lod].VertexBuffers.PositionVertexBuffer;
            if (!Buffer.GetVertexData() || Buffer.GetNumVertices() == 0) return {};
            for (uint32 Index = 0; Index < Buffer.GetNumVertices(); ++Index)
            {
                const FVector3f Position = Buffer.VertexPosition(Index);
                if (Position.ContainsNaN()) return {};
                Box += Position;
            }
        }
        if (!Box.IsValid) return {};
        const FVector3f Center = Box.GetCenter();
        float RadiusSquared = 0.f;
        for (const UStaticMesh* Mesh : Parts)
        {
            const auto& Buffer = Mesh->GetRenderData()->LODResources[Lod].VertexBuffers.PositionVertexBuffer;
            for (uint32 Index = 0; Index < Buffer.GetNumVertices(); ++Index)
                RadiusSquared = FMath::Max(RadiusSquared, (Buffer.VertexPosition(Index) - Center).SizeSquared());
        }
        Bounds += FBoxSphereBounds(FVector(Center), FVector(Box.GetExtent()), FMath::Sqrt(RadiusSquared));
    }
    const FBoxSphereBounds Result = Bounds;
    if (Result.ContainsNaN() || Result.SphereRadius <= 0.) return {};
    for (UStaticMesh* Mesh : Parts)
    {
        auto* Data = Cast<UGondolaRopeBoundsData>(Mesh->GetAssetUserDataOfClass(UGondolaRopeBoundsData::StaticClass()));
        const bool Changed = !Data || Data->LogicalParent != Parent || Data->Family != Family ||
            Data->Origin != Result.Origin || Data->Extent != Result.BoxExtent || Data->Radius != Result.SphereRadius;
        if (!Data) { Data = NewObject<UGondolaRopeBoundsData>(Mesh); Mesh->AddAssetUserData(Data); }
        if (Changed)
        {
            Data->LogicalParent = Parent; Data->Family = Family; Data->Origin = Result.Origin;
            Data->Extent = Result.BoxExtent; Data->Radius = Result.SphereRadius; Mesh->MarkPackageDirty();
        }
    }
    auto Vector = [](const FVector& Value)
    {
        return TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(Value.X),
            MakeShared<FJsonValueNumber>(Value.Y), MakeShared<FJsonValueNumber>(Value.Z)};
    };
    const auto Object = MakeShared<FJsonObject>();
    Object->SetArrayField(TEXT("origin"), Vector(Result.Origin));
    Object->SetArrayField(TEXT("extent"), Vector(Result.BoxExtent));
    Object->SetNumberField(TEXT("sphere_radius"), Result.SphereRadius);
    FString Json;
    return FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Json)) ? Json : FString();
#else
    return {};
#endif
}

bool UGondolaRopeMeshComponent::ConfigureLogicalFamily(const FString& Parent, const TArray<FString>& Family)
{
    UStaticMesh* Mesh = GetStaticMesh();
    const auto* Data = Mesh ? Cast<UGondolaRopeBoundsData>(Mesh->GetAssetUserDataOfClass(UGondolaRopeBoundsData::StaticClass())) : nullptr;
    if (!Data || Data->LogicalParent != Parent || Data->Family != Family || Family.IsEmpty() || Family.Num() > 8 ||
        !Family.Contains(Mesh->GetPathName()) || Data->Origin.ContainsNaN() || Data->Extent.ContainsNaN() ||
        Data->Extent.GetMin() < 0. || !FMath::IsFinite(Data->Radius) || Data->Radius <= 0.) return false;
    LogicalBounds = FBoxSphereBounds(Data->Origin, Data->Extent, Data->Radius);
    return !LogicalBounds.ContainsNaN();
}

FBoxSphereBounds UGondolaRopeMeshComponent::CalcBounds(const FTransform& LocalToWorld) const
{
    FBoxSphereBounds Result = LogicalBounds.TransformBy(LocalToWorld);
    Result.BoxExtent *= BoundsScale; Result.SphereRadius *= BoundsScale;
    return Result;
}

namespace
{
TAutoConsoleVariable<float> ClockScale(TEXT("gondola.TimeScale"),1.f,TEXT("Development ropeway clock scale; host authoritative."));
FVector Vector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return A.Num()==3 ? FVector(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber()) : FVector::ZeroVector;
}
double Wrap(double Time,double Period) { double T=FMath::Fmod(Time,Period);return T<0?T+Period:T; }
float Ease(float V) { V=FMath::Clamp(V,0.f,1.f);return V*V*(3.f-2.f*V); }
FAutoConsoleCommandWithWorldAndArgs GoCommand(TEXT("gondola.Go"),TEXT("Visit a ropeway station at the next stopped cabin."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World)
    { if (auto* S=AGondolaService::Find(World)) S->GoTo(Args.IsEmpty()?TEXT("hidamari"):Args[0]); }));
}

bool FGondolaLine::Parse(const TSharedPtr<FJsonObject>& Data)
{
    *this=FGondolaLine();
    const TSharedPtr<FJsonObject>* Clock=nullptr;
    if (!Data || !Data->TryGetObjectField(TEXT("clock"),Clock)) return false;
    Id=Data->GetStringField(TEXT("id")); CabinCount=int32(Data->GetNumberField(TEXT("cabins")));
    Cycle=(*Clock)->GetNumberField(TEXT("cycle_s"));
    if (!FMath::IsFinite(Cycle)||Cycle<=1.||CabinCount<1||CabinCount>32) return false;
    for (const auto& Value:(*Clock)->GetArrayField(TEXT("points")))
    {
        if (Value->Type!=EJson::Array||Value->AsArray().Num()!=3) return false;
        const FVector V=Vector(Value->AsArray());if(V.ContainsNaN())return false;Points.Add(V);
    }
    for (const auto& Value:(*Clock)->GetArrayField(TEXT("arc")))
    { const double V=Value->AsNumber();if(!FMath::IsFinite(V)||(!Arc.IsEmpty()&&V<=Arc.Last()))return false;Arc.Add(V); }
    if (Points.Num()<4||Arc.Num()!=Points.Num()||Arc[0]!=0.||!Points[0].Equals(Points.Last(),.001))return false;
    for (int32 I=1;I<Arc.Num();++I)
        if (!FMath::IsNearlyEqual((Arc[I]-Arc[I-1])*100.,FVector::Dist(Points[I],Points[I-1]),.01))return false;
    double Previous=0.;
    for (const auto& Value:(*Clock)->GetArrayField(TEXT("intervals")))
    {
        if(Value->Type!=EJson::Array||Value->AsArray().Num()!=6)return false;
        const auto& A=Value->AsArray();for(const auto& V:A)if(V->Type!=EJson::Number||!FMath::IsFinite(V->AsNumber()))return false;
        FGondolaInterval Row{A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber(),A[3]->AsNumber(),A[4]->AsNumber(),A[5]->AsNumber()};
        if(Row.End<=Row.Start||!FMath::IsNearlyEqual(Row.Start,Previous,1e-6)||Row.From<0||Row.To<Row.From||Row.To>Arc.Last()+1e-6||Row.Speed<0||Row.Speed>5.001)return false;
        const double Dt=Row.End-Row.Start;
        if(!FMath::IsNearlyEqual(Row.From+Row.Speed*Dt+.5*Row.Acceleration*Dt*Dt,Row.To,1e-5)||Row.Speed+Row.Acceleration*Dt<-.001)return false;
        Intervals.Add(Row);Previous=Row.End;
    }
    if(Intervals.IsEmpty()||!FMath::IsNearlyEqual(Previous,Cycle,1e-6))return false;
    for(const auto& Value:(*Clock)->GetArrayField(TEXT("stops")))
    {
        const auto S=Value->AsObject();if(!S)return false;
        FGondolaStop Stop{S->GetNumberField(TEXT("start")),S->GetNumberField(TEXT("end")),S->GetNumberField(TEXT("arc")),S->GetStringField(TEXT("station")),int32(S->GetNumberField(TEXT("side")))};
        if(!FMath::IsFinite(Stop.Start)||!FMath::IsFinite(Stop.End)||!FMath::IsFinite(Stop.Arc)||Stop.End<=Stop.Start||Stop.End>Cycle||Stop.Arc<0||Stop.Arc>=Arc.Last())return false;
        Stops.Add(Stop);
    }
    if(Stops.Num()!=4)return false;
    for(const auto& Value:(*Clock)->GetArrayField(TEXT("events")))
    {const auto E=Value->AsObject();if(!E)return false;Events.Add({E->GetNumberField(TEXT("time")),E->GetStringField(TEXT("kind"))});}
    return true;
}

FVector FGondolaLine::Point(double Distance) const
{
    const double S=Wrap(Distance,Arc.Last());
    const int32 I=FMath::Clamp(Algo::UpperBound(Arc,S)-1,0,Points.Num()-2);
    return FMath::Lerp(Points[I],Points[I+1],(S-Arc[I])/(Arc[I+1]-Arc[I]));
}

FGondolaPose FGondolaLine::State(double Time,const FVector& Pivot) const
{
    FGondolaPose Out;Out.CycleTime=Wrap(Time,Cycle);
    const int32 I=FMath::Clamp(Algo::UpperBoundBy(Intervals,Out.CycleTime,&FGondolaInterval::Start)-1,0,Intervals.Num()-1);
    const FGondolaInterval& R=Intervals[I];const double Dt=Out.CycleTime-R.Start;
    Out.Arc=FMath::Clamp(R.From+R.Speed*Dt+.5*R.Acceleration*Dt*Dt,R.From,R.To);
    Out.Speed=FMath::Max(0.,R.Speed+R.Acceleration*Dt);
    // The kit's grip faces opposite circuit travel so its -y door faces the platform/outside on both tracks.
    const FVector X=-(Point(Out.Arc+.05)-Point(Out.Arc-.05)).GetSafeNormal();
    const FVector Z=(FVector::UpVector-X*X.Z).GetSafeNormal();
    const FQuat GripRotation=FRotationMatrix::MakeFromXZ(X,Z).ToQuat();
    const FVector Heading=FVector(X.X,X.Y,0.).GetSafeNormal();
    const FQuat BodyRotation=FRotationMatrix::MakeFromXZ(Heading,FVector::UpVector).ToQuat();
    const FVector At=Point(Out.Arc);
    Out.Grip=FTransform(GripRotation,At);
    Out.Body=FTransform(BodyRotation,At+GripRotation.RotateVector(Pivot)-BodyRotation.RotateVector(Pivot));
    for(int32 S=0;S<Stops.Num();++S)
        if(Out.CycleTime>=Stops[S].Start&&Out.CycleTime<Stops[S].End)
        {
            Out.Stop=S;Out.Door=FMath::Min(Ease(float((Out.CycleTime-Stops[S].Start-.6)/1.2)),Ease(float((Stops[S].End-Out.CycleTime-1.5)/1.2)));break;
        }
    return Out;
}

AGondolaService::AGondolaService()
{
    PrimaryActorTick.bCanEverTick=true;PrimaryActorTick.TickGroup=TG_PrePhysics;
    bReplicates=true;bAlwaysRelevant=true;SetReplicateMovement(false);SetNetUpdateFrequency(5.f);
    RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root"));RootComponent->SetMobility(EComponentMobility::Static);Tags.Add(TEXT("NoClimb"));
}
AGondolaService* AGondolaService::Find(const UObject* Context)
{
    UWorld* W=Context?Context->GetWorld():nullptr;if(!W)return nullptr;TActorIterator<AGondolaService> I(W);return I?*I:nullptr;
}
AGondolaService* AGondolaService::Spawn(UWorld* World,const FString& Path)
{
    if(!World||!FPaths::FileExists(Path))return nullptr;if(auto* Existing=Find(World))return Existing;
    auto* S=World->SpawnActor<AGondolaService>();if(S&&!S->Initialize(Path)){S->Destroy();return nullptr;}return S;
}
void AGondolaService::BeginPlay()
{
    Super::BeginPlay();if(!bReady)Initialize(AtelierDataPath(TEXT("gondola/runtime.json")));
}
void AGondolaService::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps)const
{Super::GetLifetimeReplicatedProps(OutLifetimeProps);DOREPLIFETIME(AGondolaService,NetworkState);}

UStaticMeshComponent* AGondolaService::MeshPart(const FString& Name,const FString& Path,bool Collision,bool Movable,bool Rope)
{
    auto* Mesh=LoadObject<UStaticMesh>(nullptr,*Path);if(!Mesh){UE_LOG(LogTemp,Error,TEXT("GONDOLA missing mesh %s"),*Path);return nullptr;}
    UStaticMeshComponent* C=Rope?NewObject<UGondolaRopeMeshComponent>(this,*Name):NewObject<UStaticMeshComponent>(this,*Name);C->SetupAttachment(RootComponent);
    C->SetMobility(Movable?EComponentMobility::Movable:EComponentMobility::Static);C->SetStaticMesh(Mesh);
    C->SetCollisionEnabled(Collision?ECollisionEnabled::QueryAndPhysics:ECollisionEnabled::NoCollision);
    C->SetCollisionObjectType(Movable?ECC_Vehicle:ECC_WorldStatic);C->SetGenerateOverlapEvents(false);
    C->SetCanEverAffectNavigation(false);C->SetAffectDistanceFieldLighting(false);C->SetNetAddressable();
    C->PrimaryComponentTick.bCanEverTick=false;Components.Add(C);if(Movable)C->RegisterComponent();return C;
}

void AGondolaService::BuildCabinSeats(const FVector& CabinSize,float CabinFloorZ,TArray<FSeat>& OutSeats)
{
    // Derived directly from assets/vehicles/gondola/cabin.py bench constants:
    // Wall thickness T = 7.5 cm, bench depth SEAT_D = 40.0 cm, bench height SEAT_H = 46.0 cm.
    // Door is on +Y_ue (-y in Blender); back bench is on -Y_ue facing +Y_ue (Yaw 90),
    // west bench on -X_ue facing +X_ue (Yaw 0), east bench on +X_ue facing -X_ue (Yaw 180).
    const float WallT=7.5f,BenchD=40.f,BenchH=46.f;
    const float Xi=CabinSize.X*0.5f-WallT;
    const float Yi=CabinSize.Y*0.5f-WallT;
    const float SeatZ=CabinFloorZ+BenchH;
    OutSeats.Reset();
    OutSeats.Add({TEXT("back_left"),FVector(-28.f,-(Yi-0.5f*BenchD),SeatZ),90.f});
    OutSeats.Add({TEXT("back_right"),FVector(28.f,-(Yi-0.5f*BenchD),SeatZ),90.f});
    OutSeats.Add({TEXT("west"),FVector(-(Xi-0.5f*BenchD),0.f,SeatZ),0.f});
    OutSeats.Add({TEXT("east"),FVector(Xi-0.5f*BenchD,0.f,SeatZ),180.f});
}

bool AGondolaService::Initialize(const FString& Path)
{
    if(bReady)return true;if(bFailed)return false;bFailed=true;
    const auto Root=AtelierReadJson(Path);if(!Root)return false;
    for(const auto& V:Root->GetArrayField(TEXT("lines")))
    {FGondolaLine L;if(!L.Parse(V->AsObject()))return false;Lines.Add(MoveTemp(L));}
    if(Lines.Num()!=3)return false;
    for(const auto& V:Root->GetArrayField(TEXT("static")))
    {
        const auto R=V->AsObject();if(!R)return false;
        const FString Name=R->GetStringField(TEXT("name"));auto* C=MeshPart(Name,R->GetStringField(TEXT("mesh")),R->GetBoolField(TEXT("collision")),false);if(!C)return false;
        C->SetWorldLocationAndRotation(Vector(R->GetArrayField(TEXT("location_cm"))),FRotator(0,R->GetNumberField(TEXT("yaw")),0));
        if(Name.EndsWith(TEXT("_Collision")))C->SetVisibility(false);C->RegisterComponent();
    }
    for(const auto& V:Root->GetArrayField(TEXT("stations")))
    {
        const auto R=V->AsObject();FStation& S=Stations.AddDefaulted_GetRef();S.Id=R->GetStringField(TEXT("id"));
        for(const auto& P:R->GetArrayField(TEXT("walk_cm")))S.Walk.Add(Vector(P->AsArray()));
        S.Audio=NewObject<UGondolaStationAudioComponent>(this,*FString(TEXT("Drive_")+S.Id));S.Audio->SetupAttachment(RootComponent);
        Components.Add(S.Audio);S.Audio->RegisterComponent();S.Audio->SetWorldLocation(Vector(R->GetArrayField(TEXT("location_cm"))));
    }
    const auto Data=Root->GetObjectField(TEXT("cabin"));Pivot=Vector(Data->GetArrayField(TEXT("grip_pivot_cm")));
    FloorZ=Data->GetNumberField(TEXT("floor_z_cm"));DoorCentre=Vector(Data->GetArrayField(TEXT("door_centre_cm")));
    DoorWidth=Data->GetNumberField(TEXT("door_width_cm"));DoorHeight=Data->GetNumberField(TEXT("door_height_cm"));
    const auto& Dimensions=Data->GetArrayField(TEXT("size_cm"));Size=FVector(Dimensions[0]->AsNumber(),Dimensions[1]->AsNumber(),0);
    BuildCabinSeats(Size,FloorZ,Seats);
    for(int32 L=0;L<Lines.Num();++L)
    {
        const auto Row=Root->GetArrayField(TEXT("lines"))[L]->AsObject();
        TArray<FString> RopeFamily;
        for (const auto& Value : Row->GetArrayField(TEXT("ropes"))) RopeFamily.Add(Value->AsString());
        if (RopeFamily.IsEmpty() || RopeFamily.Num() > 8) return false;
        TSet<FString> RopeSeen;
        for (int32 Part = 0; Part < RopeFamily.Num(); ++Part)
        {
            if (RopeSeen.Contains(RopeFamily[Part])) return false;
            RopeSeen.Add(RopeFamily[Part]);
            auto* Base=MeshPart(FString::Printf(TEXT("Rope_%s_%02d"),*Lines[L].Id,Part),RopeFamily[Part],false,false,true);
            auto* Rope=Cast<UGondolaRopeMeshComponent>(Base);
            if (!Rope || Rope->GetStaticMesh()->GetNumLODs()!=3 ||
                !Rope->ConfigureLogicalFamily(TEXT("GD_")+Lines[L].Id+TEXT("_Rope"),RopeFamily)) return false;
            Rope->RegisterComponent();Rope->SetForcedLodModel(1);Ropes.Add({Rope,L});
        }
        for(int32 I=0;I<Lines[L].CabinCount;++I)
        {
            FCabin& C=Cabins.AddDefaulted_GetRef();C.Line=L;C.Index=I;
            const FString Prefix=FString::Printf(TEXT("Cabin_%s_%02d_"),*Lines[L].Id,I);
            C.Body=MeshPart(Prefix+TEXT("Collision"),Data->GetStringField(TEXT("body")),true,true);if(!C.Body)return false;C.Body->SetVisibility(false);
            for(const auto& V:Data->GetArrayField(TEXT("parts")))
            {
                const FString Asset=V->AsString();FString Name=FPaths::GetBaseFilename(Asset);Name=Name.Left(Name.Find(TEXT("."))<0?Name.Len():Name.Find(TEXT(".")));
                auto* Part=MeshPart(Prefix+Name,Asset,false,true);if(!Part)return false;Part->SetCullDistance(Data->GetNumberField(TEXT("cull_cm")));
                if(Asset.Contains(TEXT("GD_CabinGrip.")))C.Grip=Part;
                else if(Asset.Contains(TEXT("GD_CabinDoor")))
                {
                    C.Doors.Add(Part);const FString Key=Asset.Contains(TEXT("DoorLeft"))?TEXT("GD_CabinDoorLeft"):TEXT("GD_CabinDoorRight");
                    C.DoorOffsets.Add(Vector(Data->GetObjectField(TEXT("door_offsets_cm"))->GetArrayField(Key)));
                }
                else C.Parts.Add(Part);
            }
            if(!C.Grip||C.Doors.Num()!=2)return false;
            C.DoorBlock=NewObject<UBoxComponent>(this,*(Prefix+TEXT("DoorBlock")));C.DoorBlock->SetupAttachment(C.Body);
            C.DoorBlock->SetBoxExtent(FVector(DoorWidth/2,5,DoorHeight/2));C.DoorBlock->SetRelativeLocation(DoorCentre+FVector(0,0,DoorHeight/2));
            C.DoorBlock->SetCollisionObjectType(ECC_Vehicle);C.DoorBlock->SetCollisionResponseToAllChannels(ECR_Block);C.DoorBlock->SetNetAddressable();
            Components.Add(C.DoorBlock);C.DoorBlock->RegisterComponent();
            C.Audio=NewObject<UGondolaAudioComponent>(this,*(Prefix+TEXT("Audio")));C.Audio->SetupAttachment(C.Body);Components.Add(C.Audio);C.Audio->RegisterComponent();
            C.SeatTaken.Init(0,Seats.Num());
        }
    }
    bReady=true;bFailed=false;Place(ServiceTime(),true);if(HasAuthority())Publish();return true;
}

double AGondolaService::ServiceTime()const
{
    const auto* State=GetWorld()->GetGameState();const double Now=State?State->GetServerWorldTimeSeconds():GetWorld()->GetTimeSeconds();
    return Now+Offset+(GetNetMode()==NM_Client&&NetworkState.Serial?(Now-NetworkState.Stamp)*(NetworkState.Scale-1.):0.);
}

void AGondolaService::Place(double Time,bool First)
{
    const float RunningScale=HasAuthority()?FMath::Clamp(ClockScale.GetValueOnGameThread(),0.f,30.f):NetworkState.Scale;
    for(FCabin& C:Cabins)
    {
        const auto& L=Lines[C.Line];const double T=Time+L.Cycle*C.Index/L.CabinCount;
        C.Previous=C.Body->GetComponentTransform();const auto P=L.State(T,Pivot);
        C.Body->SetWorldTransform(P.Body,false,nullptr,ETeleportType::TeleportPhysics);C.Grip->SetWorldTransform(P.Grip);
        for(UStaticMeshComponent* Part:C.Parts)Part->SetWorldTransform(P.Body);
        for(int32 D=0;D<C.Doors.Num();++D)
        {FTransform Door=P.Body;Door.AddToTranslation(P.Body.TransformVectorNoScale(C.DoorOffsets[D]*P.Door));C.Doors[D]->SetWorldTransform(Door);}
        C.DoorBlock->SetCollisionEnabled(P.Stop!=INDEX_NONE&&P.Door>.999f?ECollisionEnabled::NoCollision:ECollisionEnabled::QueryAndPhysics);
        C.Audio->SetSpeed(P.Speed*100.*RunningScale);
        if(C.bPrimed&&!First)
        {
            if(C.Pose.Door<=0.f&&P.Door>0.f)C.Audio->OnDoorOpen();
            if(C.Pose.Door>.999f&&P.Door<.999f)C.Audio->OnDoorClose();
            const double Passed=T-C.LastTime;
            if(Passed>0&&Passed<L.Cycle)
                for(const auto& E:L.Events)
                    if(Wrap(E.Time-Wrap(C.LastTime,L.Cycle),L.Cycle)<Passed)
                    {if(E.Kind==TEXT("tower"))C.Audio->OnTowerPass();else if(E.Kind==TEXT("attach"))C.Audio->OnGripAttach();else C.Audio->OnGripRelease();}
        }
        C.Pose=P;C.LastTime=T;C.bPrimed=true;
    }
    for(FStation& S:Stations)S.Audio->SetRunning(RunningScale>0.f?1.f:0.f);
    // Imported far detail is permitted only beyond its declared contact/deviation distances.
    const auto* PC=GetWorld()->GetFirstPlayerController();const FVector View=PC&&PC->PlayerCameraManager?PC->PlayerCameraManager->GetCameraLocation():FVector::ZeroVector;
    for(const FRope& Rope:Ropes)
    {
        const auto& L=Lines[Rope.Line];double Best=DBL_MAX;
        for(int32 I=0;I<L.Points.Num()-1;I+=20)
        {const int32 J=FMath::Min(I+20,L.Points.Num()-1);const double Lower=FMath::Max(0.,FVector::Dist(View,L.Points[I])-(L.Arc[J]-L.Arc[I])*100.);Best=FMath::Min(Best,Lower*Lower);}
        Rope.Mesh->SetForcedLodModel(Best<FMath::Square(100000.)?1:Best<FMath::Square(200000.)?2:3);
    }
}

AGondolaService::FRiderSeat& AGondolaService::SeatFor(AWandererCharacter* Character)
{
    for(FRiderSeat& S:SeatsByRider)if(S.Character.Get()==Character)return S;
    FRiderSeat& S=SeatsByRider.AddDefaulted_GetRef();S.Character=Character;return S;
}
const AGondolaService::FRiderSeat* AGondolaService::FindSeat(const AWandererCharacter* Character)const
{
    for(const FRiderSeat& S:SeatsByRider)if(S.Character.Get()==Character)return &S;
    return nullptr;
}
int32 AGondolaService::NearestFreeSeat(int32 CabinIndex,const FVector& WorldFeet)const
{
    if(!Cabins.IsValidIndex(CabinIndex))return INDEX_NONE;
    const FCabin& Cabin=Cabins[CabinIndex];
    const FTransform& T=Cabin.Body->GetComponentTransform();
    int32 Best=INDEX_NONE;double BestDist=DBL_MAX;
    for(int32 I=0;I<Seats.Num();++I)
    {
        if(Cabin.SeatTaken.IsValidIndex(I)&&Cabin.SeatTaken[I])continue;
        const double D=FVector::Dist2D(T.TransformPosition(Seats[I].Location),WorldFeet);
        if(D<BestDist){BestDist=D;Best=I;}
    }
    return Best;
}
void AGondolaService::SitDown(FTransportRider& R,FRiderSeat& S,int32 CabinIndex,int32 SeatIndex)
{
    AWandererCharacter* C=R.Character.Get();
    if(!C||!Cabins.IsValidIndex(CabinIndex)||!Seats.IsValidIndex(SeatIndex))return;
    if(S.Seat!=INDEX_NONE&&Cabins.IsValidIndex(S.Cabin)&&Cabins[S.Cabin].SeatTaken.IsValidIndex(S.Seat))
        Cabins[S.Cabin].SeatTaken[S.Seat]=0;
    FCabin& Cabin=Cabins[CabinIndex];
    if(Cabin.SeatTaken.IsValidIndex(SeatIndex))Cabin.SeatTaken[SeatIndex]=1;
    R.Vehicle=CabinIndex;
    FTransportRiders::SetAboard(R,true,false,ETransportVehicle::Gondola);
    S.Cabin=CabinIndex;S.Seat=SeatIndex;S.Seated=0.f;S.bSailed=false;S.bManualStand=false;
    C->bTrainDriving=true;C->bGondolaSeated=true;
    auto* M=C->GetCharacterMovement();
    C->MoveIntent=FVector2D::ZeroVector;C->bJog=C->bWalk=C->bSprintHeld=false;
    M->StopMovementImmediately();M->ClearAccumulatedForces();M->SetMovementMode(MOVE_None);
    C->SetActorEnableCollision(false);
    const FTransform& T=Cabin.Body->GetComponentTransform();
    const FSeat& Seat=Seats[SeatIndex];
    const float Half=C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const float SeatYaw=float(T.Rotator().Yaw)+Seat.Yaw;
    C->SetActorLocationAndRotation(T.TransformPosition(Seat.Location)+FVector(0.f,0.f,Half-12.f),
        FRotator(0.f,SeatYaw,0.f),false,nullptr,ETeleportType::TeleportPhysics);
    S.SeatedAt=C->GetActorLocation();
    if(C->IsLocallyControlled()&&C->Controller)
        C->Controller->SetControlRotation(FRotator(0.f,SeatYaw,0.f));
    C->SetAction(TEXT("SitDown"),false,.12f,true);
    UE_LOG(LogTemp,Display,TEXT("GONDOLA RIDER %s sat cabin=%d seat=%s"),*C->GetName(),CabinIndex,*Seat.Id);
}
void AGondolaService::StandUp(FTransportRider& R,FRiderSeat& S)
{
    AWandererCharacter* C=R.Character.Get();
    if(!C||S.Seat==INDEX_NONE)return;
    const int32 CabinIndex=S.Cabin;
    const int32 SeatIndex=S.Seat;
    if(Cabins.IsValidIndex(CabinIndex)&&Cabins[CabinIndex].SeatTaken.IsValidIndex(SeatIndex))
        Cabins[CabinIndex].SeatTaken[SeatIndex]=0;
    S.Seat=INDEX_NONE;S.Seated=0.f;S.bSailed=false;
    C->bGondolaSeated=false;C->bTrainDriving=false;
    if(Cabins.IsValidIndex(CabinIndex))
    {
        const FCabin& Cabin=Cabins[CabinIndex];
        const FTransform& T=Cabin.Body->GetComponentTransform();
        const float Half=C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        const FVector StandLocal(0.f,0.f,FloorZ+Half+2.f);
        const float DoorYaw=float(T.Rotator().Yaw)+90.f;
        C->SetActorLocationAndRotation(T.TransformPosition(StandLocal),FRotator(0.f,DoorYaw,0.f),false,nullptr,ETeleportType::TeleportPhysics);
        C->SetActorEnableCollision(true);
        auto* M=C->GetCharacterMovement();
        M->SetMovementMode(MOVE_Walking);M->bForceNextFloorCheck=true;
        C->SetBase(Cabin.Body);
    }
    else
    {
        C->SetActorEnableCollision(true);
        C->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    }
    C->SetAction(NAME_None,false,.2f);
    UE_LOG(LogTemp,Display,TEXT("GONDOLA RIDER %s stood cabin=%d seat=%s"),*C->GetName(),CabinIndex,
        Seats.IsValidIndex(SeatIndex)?*Seats[SeatIndex].Id:TEXT("-"));
}
bool AGondolaService::SitPlayer(AWandererCharacter* Character,int32 PreferredSeat)
{
    if(!Character)return false;
    auto& R=FTransportRiders::Find(Riders,Character);
    auto& S=SeatFor(Character);
    if(!R.bAboard||!Cabins.IsValidIndex(R.Vehicle))return false;
    const FVector Feet=Character->GetActorLocation()-FVector(0,0,Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const int32 SeatIndex=Seats.IsValidIndex(PreferredSeat)?PreferredSeat:NearestFreeSeat(R.Vehicle,Feet);
    if(SeatIndex==INDEX_NONE)return false;
    SitDown(R,S,R.Vehicle,SeatIndex);
    if(HasAuthority())Publish();
    return true;
}
bool AGondolaService::StandPlayer(AWandererCharacter* Character)
{
    if(!Character)return false;
    auto& R=FTransportRiders::Find(Riders,Character);
    auto& S=SeatFor(Character);
    if(S.Seat==INDEX_NONE)return false;
    S.bManualStand=true;
    StandUp(R,S);
    if(HasAuthority())Publish();
    return true;
}
bool AGondolaService::TryInteract(AWandererCharacter* Character)
{
    auto* Service=Find(Character);
    if(!Service||!Character)return false;
    const FRiderSeat* S=Service->FindSeat(Character);
    if(S&&S->Seat!=INDEX_NONE)return Service->StandPlayer(Character);
    return Service->SitPlayer(Character);
}
void AGondolaService::UpdateRiders(float Dt)
{
    bool Changed=Riders.RemoveAll([](const FTransportRider& R){return !R.Character.IsValid();})>0;
    SeatsByRider.RemoveAll([](const FRiderSeat& S){return !S.Character.IsValid();});
    for(TActorIterator<AWandererCharacter> It(GetWorld());It;++It)
    {
        auto* C=*It;if(C->IsNpc())continue;
        auto& R=FTransportRiders::Find(Riders,C);FTransportRiders::OrderTick(*this,R);
        auto& S=SeatFor(C);
        if(S.Seat!=INDEX_NONE&&Cabins.IsValidIndex(S.Cabin)&&Seats.IsValidIndex(S.Seat))
        {
            const FCabin& Cabin=Cabins[S.Cabin];
            if(S.Seated>0.f&&(C->IsLocallyControlled()||HasAuthority())&&FVector::Dist(C->GetActorLocation(),S.SeatedAt)>300.)
            {
                StandUp(R,S);
                FTransportRiders::SetAboard(R,false,false,ETransportVehicle::Gondola);
                R.Vehicle=INDEX_NONE;Changed=true;continue;
            }
            S.bSailed|=Cabin.Pose.Speed>0.5;
            if((S.bSailed&&Cabin.Pose.Stop!=INDEX_NONE&&Cabin.Pose.Door>0.85f)||
               (!C->MoveIntent.IsNearlyZero()&&Cabin.Pose.Stop!=INDEX_NONE&&Cabin.Pose.Door>0.5f&&S.Seated>0.5f))
            {
                S.bManualStand=true;
                StandUp(R,S);Changed=true;
            }
            else
            {
                const FSeat& Seat=Seats[S.Seat];
                const FTransform& T=Cabin.Body->GetComponentTransform();
                const float Half=C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
                const double Turn=FRotator::NormalizeAxis(T.Rotator().Yaw-Cabin.Previous.Rotator().Yaw);
                C->SetActorLocationAndRotation(T.TransformPosition(Seat.Location)+FVector(0.f,0.f,Half-12.f),
                    FRotator(0.f,float(T.Rotator().Yaw)+Seat.Yaw,0.f),false,nullptr,ETeleportType::TeleportPhysics);
                S.SeatedAt=C->GetActorLocation();
                C->GetCharacterMovement()->Velocity=FVector::ZeroVector;
                if(C->IsLocallyControlled()&&C->Controller&&!FMath::IsNearlyZero(Turn))
                    C->Controller->SetControlRotation(C->Controller->GetControlRotation()+FRotator(0.,Turn,0.));
                S.Seated+=Dt;
                if(S.Seated>1.1f)C->SetAction(TEXT("SitIdle"),true,.2f);
                continue;
            }
        }
        if(!C->IsPlayerControlled()||!(C->IsLocallyControlled()||C->HasAuthority()))continue;
        int32 Vehicle=INDEX_NONE;
        const FVector Feet=C->GetActorLocation()-FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()-3.);
        for(int32 I=0;I<Cabins.Num();++I)
        {
            const FCabin& Cabin=Cabins[I];
            if(C->GetMovementBase()==Cabin.Body){Vehicle=I;break;}
            // The character has not ticked yet: test the frame it occupied last tick.
            const FVector Local=Cabin.Previous.InverseTransformPosition(Feet);
            if(FMath::Abs(Local.X)>Size.X/2||FMath::Abs(Local.Y)>Size.Y/2||Local.Z<FloorZ-12||Local.Z>FloorZ+25)continue;
            const FVector Now=Cabin.Body->GetComponentTransform().TransformPosition(Local);FHitResult Hit;
            if(GetWorld()->LineTraceSingleByObjectType(Hit,Now+FVector(0,0,12),Now-FVector(0,0,35),FCollisionObjectQueryParams(ECC_Vehicle))&&Hit.GetComponent()==Cabin.Body&&Hit.ImpactNormal.Z>.7f)
            {Vehicle=I;break;}
        }
        if(Vehicle!=INDEX_NONE)FTransportRiders::Carry(R,*this,Cabins[Vehicle].Body,Cabins[Vehicle].Previous,true);
        Changed|=R.bAboard!=(Vehicle!=INDEX_NONE)||(R.bAboard&&R.Vehicle!=Vehicle);
        R.Vehicle=Vehicle;FTransportRiders::SetAboard(R,Vehicle!=INDEX_NONE,false,ETransportVehicle::Gondola);
        if(Vehicle==INDEX_NONE)S.bManualStand=false;
        else if(S.Seat==INDEX_NONE&&!S.bManualStand)
        {
            const FCabin& Cabin=Cabins[Vehicle];
            const FVector Local=Cabin.Body->GetComponentTransform().InverseTransformPosition(Feet);
            const bool bInsideCore=FMath::Abs(Local.X)<=55.f&&Local.Y<=35.f;
            const bool bStoppedWalking=C->MoveIntent.IsNearlyZero()&&C->GetVelocity().Size2D()<15.f;
            const bool bDeparting=Cabin.Pose.Stop==INDEX_NONE||Cabin.Pose.Door<0.95f;
            if((bInsideCore&&bStoppedWalking)||bDeparting)
            {
                const int32 SeatIndex=NearestFreeSeat(Vehicle,Feet);
                if(SeatIndex!=INDEX_NONE){SitDown(R,S,Vehicle,SeatIndex);Changed=true;}
            }
        }
    }
    if(Changed&&HasAuthority())Publish();
}

void AGondolaService::Publish()
{
    if(!HasAuthority()||!JapanNetwork::IsOnline(GetWorld()))return;
    ++NetworkState.Serial;NetworkState.Offset=Offset;NetworkState.Scale=FMath::Clamp(ClockScale.GetValueOnGameThread(),0.f,30.f);
    const auto* GS=GetWorld()->GetGameState();NetworkState.Stamp=GS?GS->GetServerWorldTimeSeconds():GetWorld()->GetTimeSeconds();
    NetworkState.Passengers.Reset();
    for(const auto& R:Riders)
        if(auto* C=R.Character.Get();C&&R.bAboard&&Cabins.IsValidIndex(R.Vehicle))
        {
            auto& P=NetworkState.Passengers.AddDefaulted_GetRef();P.Rider=C;P.Cabin=R.Vehicle;
            if(const FRiderSeat* S=FindSeat(C))P.Seat=int16(S->Seat);
        }
    ForceNetUpdate();
}
void AGondolaService::ApplyRemote()
{
    if(!NetworkState.Serial||!bReady)return;
    TArray<FTransportMembership> Members;for(const auto& P:NetworkState.Passengers)Members.Add({P.Rider.Get(),P.Cabin});
    FTransportRiders::ApplyRemote(*this,Riders,Members,Cabins.Num(),ETransportVehicle::Gondola);
    for(const auto& P:NetworkState.Passengers)
        if(AWandererCharacter* C=P.Rider.Get())
        {
            auto& R=FTransportRiders::Find(Riders,C);
            auto& S=SeatFor(C);
            if(P.Seat!=INDEX_NONE&&S.Seat!=P.Seat)SitDown(R,S,P.Cabin,P.Seat);
            else if(P.Seat==INDEX_NONE&&S.Seat!=INDEX_NONE)StandUp(R,S);
        }
}
void AGondolaService::OnRep_NetworkState()
{
    if(!NetworkState.Serial)return;
    if(FMath::Abs(Offset-NetworkState.Offset)>1.)for(auto& C:Cabins)C.bPrimed=false;
    Offset=NetworkState.Offset;ApplyRemote();
}
void AGondolaService::Tick(float Dt)
{
    Super::Tick(Dt);if(!bReady)return;
    if(HasAuthority())
    {
        const float Scale=FMath::Clamp(ClockScale.GetValueOnGameThread(),0.f,30.f);Offset+=Dt*(Scale-1.);
        PublishElapsed+=Dt;
        if(Scale!=NetworkState.Scale||(Scale!=1.f&&PublishElapsed>=.2)){Publish();PublishElapsed=0.;}
    }
    else ApplyRemote();
    Place(ServiceTime());UpdateRiders(Dt);
}
void AGondolaService::EndPlay(const EEndPlayReason::Type Reason)
{
    for(auto& R:Riders)
    {
        if(AWandererCharacter* C=R.Character.Get())if(FRiderSeat* S= const_cast<FRiderSeat*>(FindSeat(C)))if(S->Seat!=INDEX_NONE)StandUp(R,*S);
        FTransportRiders::SetAboard(R,false,false,ETransportVehicle::Gondola);
    }
    Super::EndPlay(Reason);
}

bool AGondolaService::GoTo(const FString& Station)
{
    if(!bReady||JapanNetwork::IsOnline(GetWorld()))return false;
    for(const auto& R:Riders)if(R.bAboard)return false;
    auto* PC=GetWorld()->GetFirstPlayerController();auto* C=PC?Cast<AWandererCharacter>(PC->GetPawn()):nullptr;if(!C)return false;
    const auto* S=Stations.FindByPredicate([&](const FStation& Row){return Row.Id==Station;});if(!S||S->Walk.IsEmpty())return false;
    const double Now=ServiceTime();double Soon=DBL_MAX;
    for(const auto& Cabin:Cabins)
    {
        const auto& L=Lines[Cabin.Line];const double Phase=Now+L.Cycle*Cabin.Index/L.CabinCount;
        for(const auto& Stop:L.Stops)if(Stop.Station==Station)Soon=FMath::Min(Soon,Wrap(Stop.Start+2.-Wrap(Phase,L.Cycle),L.Cycle));
    }
    if(Soon==DBL_MAX)return false;Offset+=Soon;Place(ServiceTime(),true);
    C->GetCharacterMovement()->StopMovementImmediately();
    return C->SetActorLocation(S->Walk.Last()+FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+3.),false,nullptr,ETeleportType::TeleportPhysics);
}
FString AGondolaService::StateJson()const
{
    auto Root=MakeShared<FJsonObject>();Root->SetNumberField(TEXT("time"),ServiceTime());TArray<TSharedPtr<FJsonValue>> Rows;
    for(int32 I=0;I<Cabins.Num();++I)
    {
        const auto& C=Cabins[I];auto Row=MakeShared<FJsonObject>();Row->SetNumberField(TEXT("index"),I);Row->SetStringField(TEXT("line"),Lines[C.Line].Id);
        const FVector At=C.Body->GetComponentLocation();TArray<TSharedPtr<FJsonValue>> Position;
        for(double V:{At.X,At.Y,At.Z})Position.Add(MakeShared<FJsonValueNumber>(V));Row->SetArrayField(TEXT("location"),Position);
        Row->SetNumberField(TEXT("speed_m_s"),C.Pose.Speed);Row->SetNumberField(TEXT("door"),C.Pose.Door);
        Row->SetNumberField(TEXT("floor_tilt_deg"),FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(C.Body->GetUpVector().Z,-1.,1.))));
        Row->SetNumberField(TEXT("side"),C.Pose.Stop==INDEX_NONE?0:Lines[C.Line].Stops[C.Pose.Stop].Side);
        Row->SetStringField(TEXT("station"),C.Pose.Stop==INDEX_NONE?TEXT(""):Lines[C.Line].Stops[C.Pose.Stop].Station);Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("cabins"),Rows);Rows.Reset();
    for(const auto& R:Riders)if(R.Character.IsValid()&&R.bAboard)
    {
        auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("name"),R.Character->GetName());Row->SetNumberField(TEXT("cabin"),R.Vehicle);
        const FRiderSeat* S=FindSeat(R.Character.Get());
        const int32 SeatIdx=S?S->Seat:INDEX_NONE;
        Row->SetBoolField(TEXT("seated"),SeatIdx!=INDEX_NONE);
        Row->SetNumberField(TEXT("seat"),SeatIdx);
        Row->SetStringField(TEXT("seat_id"),Seats.IsValidIndex(SeatIdx)?Seats[SeatIdx].Id:TEXT(""));
        Row->SetBoolField(TEXT("first_person"),R.Character->IsTrainFirstPerson());
        Row->SetBoolField(TEXT("head_hidden"),R.Character->HidesTrainBody());
        Row->SetNumberField(TEXT("camera_blend"),R.Character->GetTrainViewBlend());
        if(Cabins.IsValidIndex(R.Vehicle))
        {
            const FVector Local=Cabins[R.Vehicle].Body->GetComponentTransform().InverseTransformPosition(R.Character->GetActorLocation());
            const float Radius=SeatIdx!=INDEX_NONE?18.f:22.f;
            const float Xi=Size.X*0.5f-7.5f,Yi=Size.Y*0.5f-7.5f;
            const float ClearX=Xi-FMath::Abs(float(Local.X))-Radius;
            const float ClearY=Yi-FMath::Abs(float(Local.Y))-Radius;
            const float ClearZ=(FloorZ+212.f)-(float(Local.Z)+55.f);
            Row->SetNumberField(TEXT("wall_clearance_cm"),FMath::Min3(ClearX,ClearY,ClearZ));
            Row->SetBoolField(TEXT("no_clip"),FMath::Min3(ClearX,ClearY,ClearZ)>0.f);
        }
        const auto* Base=R.Character->GetMovementBase();
        Row->SetStringField(TEXT("movement_base"),Base?Base->GetName():TEXT(""));
        Row->SetBoolField(TEXT("base_is_cabin"),Cabins.IsValidIndex(R.Vehicle)&&Base==Cabins[R.Vehicle].Body);
        const FVector Feet=R.Character->GetActorLocation()-FVector(0,0,R.Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
        TArray<TSharedPtr<FJsonValue>> Position;
        for(double V:{Feet.X,Feet.Y,Feet.Z})Position.Add(MakeShared<FJsonValueNumber>(V));
        Row->SetArrayField(TEXT("feet_cm"),Position);Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("riders"),Rows);FString Text;FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Text));return Text;
}
FVector AGondolaService::Point(const FString& What)const
{
    TArray<FString> Parts;What.ParseIntoArray(Parts,TEXT(":"));
    if(Parts.Num()==3&&Parts[0]==TEXT("walk"))
    {
        const auto* S=Stations.FindByPredicate([&](const FStation& R){return R.Id==Parts[1];});if(!S)return FVector::ZeroVector;
        int32 I=FCString::Atoi(*Parts[2]);if(I<0)I+=S->Walk.Num();return S->Walk.IsValidIndex(I)?S->Walk[I]:FVector::ZeroVector;
    }
    if(Parts.Num()==3&&Parts[0]==TEXT("seat"))
    {
        const int32 C=FCString::Atoi(*Parts[1]),I=FCString::Atoi(*Parts[2]);
        return Cabins.IsValidIndex(C)&&Seats.IsValidIndex(I)?Cabins[C].Body->GetComponentTransform().TransformPosition(Seats[I].Location):FVector::ZeroVector;
    }
    if(Parts.Num()==2&&Parts[0]==TEXT("cabin"))
    {const int32 I=FCString::Atoi(*Parts[1]);return Cabins.IsValidIndex(I)?Cabins[I].Body->GetComponentTransform().TransformPosition(FVector(0,0,FloorZ)):FVector::ZeroVector;}
    return FVector::ZeroVector;
}
FString UGondolaLive::GondolaState(){auto* S=AGondolaService::Find(ULiveLibrary::GameWorld());return S?S->StateJson():TEXT("{}");}
bool UGondolaLive::GondolaGo(const FString& Station){auto* S=AGondolaService::Find(ULiveLibrary::GameWorld());return S&&S->GoTo(Station);}
FVector UGondolaLive::GondolaPoint(const FString& What){auto* S=AGondolaService::Find(ULiveLibrary::GameWorld());return S?S->Point(What):FVector::ZeroVector;}
bool UGondolaLive::GondolaSit(int32 SeatIndex){auto* W=ULiveLibrary::GameWorld();auto* S=AGondolaService::Find(W);auto* PC=W?W->GetFirstPlayerController():nullptr;return S&&PC&&S->SitPlayer(Cast<AWandererCharacter>(PC->GetPawn()),SeatIndex);}
bool UGondolaLive::GondolaStand(){auto* W=ULiveLibrary::GameWorld();auto* S=AGondolaService::Find(W);auto* PC=W?W->GetFirstPlayerController():nullptr;return S&&PC&&S->StandPlayer(Cast<AWandererCharacter>(PC->GetPawn()));}
