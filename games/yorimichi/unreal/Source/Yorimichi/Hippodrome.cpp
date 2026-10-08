#include "Hippodrome.h"
#include "JapanNetwork.h"
#include "AtelierData.h"
#include "HorseRace.h"
#include "Animation/AnimSequence.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

static TSharedPtr<FJsonObject> ReadHippodromeJson(const FString& Path)
{
    return AtelierReadJson(Path);
}

static FVector JsonVector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return FVector(A.Num() > 0 ? A[0]->AsNumber() : 0., A.Num() > 1 ? A[1]->AsNumber() : 0., A.Num() > 2 ? A[2]->AsNumber() : 0.);
}

// ------------------------------------------------------------------------------------------------------------ Course

FVector FHippodromeCourse::At(double S, double Offset, float* Yaw) const
{
    S = FMath::Fmod(S, Lap); if (S < 0.) S += Lap;
    const double R = Radius + Offset, Ox = Origin.X, Oy = Origin.Y;
    double X, Y, Heading;
    if (S < Half) { X = FinishX + S; Y = Oy - R; Heading = 0.; }                      // home straight, east
    else if ((S -= Half) < PI * Radius)                                                  // east turn
    { const double A = -HALF_PI + S / Radius; X = Ox + Half + R * FMath::Cos(A); Y = Oy + R * FMath::Sin(A); Heading = A + HALF_PI; }
    else if ((S -= PI * Radius) < 2. * Half) { X = Ox + Half - S; Y = Oy + R; Heading = PI; }   // back straight, west
    else if ((S -= 2. * Half) < PI * Radius)                                             // west turn
    { const double A = HALF_PI + S / Radius; X = Ox - Half + R * FMath::Cos(A); Y = Oy + R * FMath::Sin(A); Heading = A + HALF_PI; }
    else { S -= PI * Radius; X = Ox - Half + S; Y = Oy - R; Heading = 0.; }              // home straight to the post
    if (Yaw) *Yaw = float(-FMath::RadiansToDegrees(Heading));
    return World(X, Y);
}

bool FHippodromeCourse::InTurn(double S) const
{
    S = FMath::Fmod(S, Lap); if (S < 0.) S += Lap;
    return !(S < Half || (Half + PI * Radius <= S && S < 3. * Half + PI * Radius) || S >= Lap - Half);
}

double FHippodromeCourse::CurvatureScale(double S, double Offset) const { return InTurn(S) ? (Radius + Offset) / Radius : 1.; }

// ------------------------------------------------------------------------------------------------------------ Roster

const TMap<FString, FHorseSpec>& FHorseSpec::All()
{
    static TMap<FString, FHorseSpec> Roster;
    static bool bLoaded = false;
    if (bLoaded) return Roster;
    bLoaded = true;
    const TSharedPtr<FJsonObject> Root = ReadHippodromeJson(AtelierDataPath(TEXT("horses/roster.json")));
    const TArray<TSharedPtr<FJsonValue>>* Characters = nullptr;
    if (!Root || !Root->TryGetArrayField(TEXT("characters"), Characters)) { UE_LOG(LogTemp, Warning, TEXT("Horse roster: missing")); return Roster; }
    for (const TSharedPtr<FJsonValue>& Value : *Characters)
    {
        const TSharedPtr<FJsonObject>& C = Value->AsObject();
        FHorseSpec S;
        S.Name = C->GetStringField(TEXT("name")); C->TryGetStringField(TEXT("label"), S.Label);
        C->TryGetStringField(TEXT("kind"), S.Kind); C->TryGetStringField(TEXT("coat"), S.Coat);
        S.Mesh = FSoftObjectPath(C->GetStringField(TEXT("mesh")));
        C->TryGetNumberField(TEXT("mesh_yaw"), S.MeshYaw); C->TryGetNumberField(TEXT("scale"), S.Scale); C->TryGetNumberField(TEXT("height_cm"), S.HeightCm);
        const TSharedPtr<FJsonObject>* Speeds = nullptr;
        if (C->TryGetObjectField(TEXT("speeds_cm"), Speeds))
            for (const auto& Speed : (*Speeds)->Values) S.SpeedsCm.Add(FName(*Speed.Key), float(Speed.Value->AsNumber()));
        for (const auto& Clip : C->GetObjectField(TEXT("clips"))->Values)
        {
            const TSharedPtr<FJsonObject>& Entry = Clip.Value->AsObject();
            S.Clips.Add(FName(*Clip.Key), FSoftObjectPath(Entry->GetStringField(TEXT("path"))));
            S.Lengths.Add(FName(*Clip.Key), float(Entry->GetNumberField(TEXT("length"))));
        }
        for (const auto& Role : C->GetObjectField(TEXT("roles"))->Values) S.Roles.Add(FName(*Role.Key), FName(*Role.Value->AsString()));
        Roster.Add(S.Name, MoveTemp(S));
    }
    UE_LOG(LogTemp, Display, TEXT("Horse roster: %d characters"), Roster.Num());
    return Roster;
}

const FHorseSpec* FHorseSpec::Find(const FString& Name) { return All().Find(Name); }

FString FHorseSpec::PlayerRider() { return Find(TEXT("RiderCairo")) ? FString(TEXT("RiderCairo")) : FString(TEXT("RiderLink")); }

// ------------------------------------------------------------------------------------------------------------ Figure

AHippodromeFigure::AHippodromeFigure()
{
    PrimaryActorTick.bCanEverTick = false;
    Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent = Root;
    auto Make = [this](const TCHAR* Name)
    {
        USkeletalMeshComponent* M = CreateDefaultSubobject<USkeletalMeshComponent>(Name);
        M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        M->SetCanEverAffectNavigation(false);
        // The rider reads the saddle bone every frame, and the race camera often looks past a horse.
        M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
        return M;
    };
    Body = Make(TEXT("Body"));
    Body->SetupAttachment(Root);
    Rider = Make(TEXT("Rider"));
    Rider->SetupAttachment(Body);
}

AHippodromeFigure* AHippodromeFigure::Spawn(UWorld* World, const FString& BodyName, const FString& RiderName, const FVector& Ground, float Yaw)
{
    const FHorseSpec* BodyData = FHorseSpec::Find(BodyName);
    const FHorseSpec* RiderData = RiderName.IsEmpty() ? nullptr : FHorseSpec::Find(RiderName);
    if (!World || !BodyData) { UE_LOG(LogTemp, Warning, TEXT("Hippodrome: no roster entry %s"), *BodyName); return nullptr; }
    FActorSpawnParameters Params; Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    AHippodromeFigure* Figure = World->SpawnActor<AHippodromeFigure>(Ground, FRotator(0, Yaw, 0), Params);
    if (Figure) Figure->Initialize(*BodyData, RiderData);
    return Figure;
}

void AHippodromeFigure::LoadClips(const FHorseSpec& Spec, TMap<FName, TObjectPtr<UAnimSequence>>& Out)
{
    for (const auto& Clip : Spec.Clips)
        if (UAnimSequence* Sequence = Cast<UAnimSequence>(Clip.Value.TryLoad())) Out.Add(Clip.Key, Sequence);
}

void AHippodromeFigure::Initialize(const FHorseSpec& BodyData, const FHorseSpec* RiderData)
{
    BodySpec = BodyData;
    Body->SetSkeletalMeshAsset(Cast<USkeletalMesh>(BodySpec.Mesh.TryLoad()));
    Body->SetRelativeLocationAndRotation(FVector::ZeroVector, FRotator(0, BodySpec.MeshYaw, 0));
    Body->SetRelativeScale3D(FVector(BodySpec.Scale));
    LoadClips(BodySpec, BodyClips);
    bHasRider = false;
    if (RiderData && Body->GetSkeletalMeshAsset())
    {
        RiderSpec = *RiderData;
        Rider->SetSkeletalMeshAsset(Cast<USkeletalMesh>(RiderSpec.Mesh.TryLoad()));
        // The rider's root goes on the saddle in the horse's rest pose: its offset from the bone is taken there, so the
        // rider then follows the saddle through every stride.
        static const FName Saddle(TEXT("Saddle_Root"));
        const FReferenceSkeleton& Ref = Body->GetSkeletalMeshAsset()->GetRefSkeleton();
        int32 Bone = Ref.FindBoneIndex(Saddle);
        if (Rider->GetSkeletalMeshAsset() && Bone != INDEX_NONE)
        {
            FTransform BoneRest = FTransform::Identity;
            for (int32 I = Bone; I != INDEX_NONE; I = Ref.GetParentIndex(I)) BoneRest = BoneRest * Ref.GetRefBonePose()[I];
            // A rider mesh facing another way than the horse's (Cairo faces +X, the glTF riders +Y) turns to face ahead.
            const FTransform Seat(FRotator(0, RiderSpec.MeshYaw - BodySpec.MeshYaw, 0), BoneRest.GetLocation(),
                FVector(RiderSpec.Scale / FMath::Max(BodySpec.Scale, .01f)));
            Rider->AttachToComponent(Body, FAttachmentTransformRules::KeepRelativeTransform, Saddle);
            Rider->SetRelativeTransform(Seat.GetRelativeTransform(BoneRest));
            LoadClips(RiderSpec, RiderClips);
            bHasRider = true;
        }
        else UE_LOG(LogTemp, Warning, TEXT("Hippodrome: %s cannot carry %s (no Saddle_Root or mesh)"), *BodySpec.Name, *RiderSpec.Name);
    }
    Rider->SetVisibility(bHasRider);
    PlayBody(TEXT("idle"), true);
    if (bHasRider) PlayRider(TEXT("idle"), true);
}

FName AHippodromeFigure::Resolve(const FHorseSpec& Spec, FName RoleOrClip)
{
    const FName Clip = Spec.Role(RoleOrClip);
    return Clip.IsNone() ? RoleOrClip : Clip;
}

bool AHippodromeFigure::RiderHas(FName Role) const { return bHasRider && RiderClips.Contains(Resolve(RiderSpec, Role)); }

float AHippodromeFigure::PlayBody(FName RoleOrClip, bool bLoop, float Rate)
{
    const FName Name = Resolve(BodySpec, RoleOrClip);
    const TObjectPtr<UAnimSequence>* Sequence = BodyClips.Find(Name);
    if (!Sequence || !*Sequence) return 0.f;
    Body->PlayAnimation(*Sequence, bLoop); Body->SetPlayRate(Rate); BodyCurrent = Name;
    return (*Sequence)->GetPlayLength() / FMath::Max(Rate, .01f);
}

float AHippodromeFigure::PlayRider(FName RoleOrClip, bool bLoop, float Rate)
{
    if (!bHasRider) return 0.f;
    const FName Name = Resolve(RiderSpec, RoleOrClip);
    const TObjectPtr<UAnimSequence>* Sequence = RiderClips.Find(Name);
    if (!Sequence || !*Sequence) return 0.f;
    Rider->PlayAnimation(*Sequence, bLoop); Rider->SetPlayRate(Rate); RiderCurrent = Name;
    return (*Sequence)->GetPlayLength() / FMath::Max(Rate, .01f);
}

float AHippodromeFigure::PlayRiderOnce(FName RoleOrClip, float Rate)
{
    const float Seconds = PlayRider(RoleOrClip, false, Rate);
    if (Seconds > 0.f) RiderBusyUntil = GetWorld()->GetTimeSeconds() + Seconds;
    return Seconds;
}

void AHippodromeFigure::Gait(FName HorseRole, FName RiderRole, float Rate)
{
    const FName HorseClip = Resolve(BodySpec, HorseRole);
    if (!BodyClips.Contains(HorseClip)) return;
    FName RiderClip = NAME_None;
    if (bHasRider)
    {
        RiderClip = Resolve(RiderSpec, RiderRole);
        if (!RiderClips.Contains(RiderClip)) RiderClip = Resolve(RiderSpec, TEXT("run"));
        if (!RiderClips.Contains(RiderClip)) RiderClip = NAME_None;
    }
    // The rider's clip runs at the rate that fits its cycle into the horse's, so a stride is a stride for both; a new
    // gait starts where the old one was in its stride, and the rider joins at the same point.
    const float HorseLength = FMath::Max(BodySpec.Lengths.FindRef(HorseClip), .01f);
    const float RiderLength = RiderClip.IsNone() ? 0.f : RiderSpec.Lengths.FindRef(RiderClip);
    const float RiderRate = Rate * RiderLength / HorseLength;
    const bool bRiderFree = GetWorld()->GetTimeSeconds() >= RiderBusyUntil;
    if (HorseClip != BodyCurrent)
    {
        const float OldLength = BodySpec.Lengths.FindRef(BodyCurrent);
        const float Phase = OldLength > .01f ? FMath::Frac(Body->GetPosition() / OldLength) : 0.f;
        PlayBody(HorseClip, true, Rate);
        Body->SetPosition(Phase * HorseLength, false);
        if (bRiderFree && !RiderClip.IsNone()) { PlayRider(RiderClip, true, RiderRate); Rider->SetPosition(Phase * RiderLength, false); }
        return;
    }
    Body->SetPlayRate(Rate);
    if (!bRiderFree || RiderClip.IsNone()) return;
    if (RiderClip != RiderCurrent)
    {
        PlayRider(RiderClip, true, RiderRate);
        Rider->SetPosition(FMath::Frac(Body->GetPosition() / HorseLength) * RiderLength, false);
    }
    else Rider->SetPlayRate(RiderRate);
}

// ------------------------------------------------------------------------------------------------------------ Venue

AHippodrome::AHippodrome()
{
    PrimaryActorTick.bCanEverTick = false;
    Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent = Root;
}

AHippodrome* AHippodrome::Spawn(UWorld* World, const FString& Path)
{
    if (!World || !FPaths::FileExists(Path)) return nullptr;
    AHippodrome* H = World->SpawnActor<AHippodrome>();
    if (H && !H->Initialize(Path)) { H->Destroy(); return nullptr; }
    return H;
}

AHippodrome* AHippodrome::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<AHippodrome> It(World);
    return It ? *It : nullptr;
}

void AHippodrome::SetGateOnTrack(bool bOn)
{
    if (bOn == bGateOn || !GateMesh.IsValid()) return;
    bGateOn = bOn;
    GateMesh->SetVisibility(bOn);
    GateMesh->SetCollisionEnabled(bOn ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
}

bool AHippodrome::Initialize(const FString& Path)
{
    const TSharedPtr<FJsonObject> Root_ = ReadHippodromeJson(Path);
    if (!Root_) { UE_LOG(LogTemp, Warning, TEXT("Hippodrome: cannot read %s"), *Path); return false; }
    FString AssetRoot(TEXT("/Game/Hippodrome"));
    Root_->TryGetStringField(TEXT("asset_root"), AssetRoot);
    const FVector O = JsonVector(Root_->GetArrayField(TEXT("origin")));
    const TSharedPtr<FJsonObject> C = Root_->GetObjectField(TEXT("course"));
    Course.Origin = FVector2D(O.X, O.Y); Course.Z = O.Z;
    Course.Half = C->GetNumberField(TEXT("half")); Course.Radius = C->GetNumberField(TEXT("radius"));
    Course.Width = C->GetNumberField(TEXT("width")); Course.Lap = C->GetNumberField(TEXT("lap"));
    Course.FinishX = C->GetNumberField(TEXT("finish_x"));
    const TSharedPtr<FJsonObject> Gate = Root_->GetObjectField(TEXT("gate"));
    Course.GateS = Gate->GetNumberField(TEXT("s"));
    SetActorLocation(Course.World(O.X, O.Y));
    Tags.AddUnique(TEXT("hippodrome"));
    int32 Placed = 0;
    for (const TSharedPtr<FJsonValue>& Entry : Root_->GetArrayField(TEXT("meshes")))
    {
        const TSharedPtr<FJsonObject>& M = Entry->AsObject();
        const FString Name = M->GetStringField(TEXT("name"));
        UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *AssetRoot, *Name, *Name));
        if (!Mesh) { UE_LOG(LogTemp, Warning, TEXT("Hippodrome: mesh %s is not imported"), *Name); continue; }
        const FVector At = JsonVector(M->GetArrayField(TEXT("at")));
        bool bBlocks = true; M->TryGetBoolField(TEXT("blocks"), bBlocks);
        auto* Component = NewObject<UStaticMeshComponent>(this, *Name);
        Component->SetStaticMesh(Mesh); Component->SetupAttachment(RootComponent);
        Component->SetWorldLocationAndRotation(Course.World(O.X + At.X, O.Y + At.Y, At.Z), FRotator(0, -M->GetNumberField(TEXT("yaw")), 0));
        Component->SetCollisionEnabled(bBlocks ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
        Component->SetCollisionResponseToAllChannels(ECR_Block);
        Component->SetCanEverAffectNavigation(false);
        Component->RegisterComponent(); ++Placed;
        if (Name == TEXT("SM_HD_StartingGate")) GateMesh = Component;
    }
    RootComponent->SetMobility(EComponentMobility::Static);
    bGameplayReady = Placed > 0 && Placed == Root_->GetArrayField(TEXT("meshes")).Num();
    if (Placed == 0) return false;
    auto Spot = [&](const TCHAR* Key, FVector& Out, float& Yaw)
    {
        const TSharedPtr<FJsonObject> S = Root_->GetObjectField(Key);
        const FVector L = JsonVector(S->GetArrayField(TEXT("at")));
        Out = Course.World(O.X + L.X, O.Y + L.Y, L.Z); Yaw = -float(S->GetNumberField(TEXT("yaw")));
    };
    Spot(TEXT("master"), MasterGround, MasterYaw);
    Spot(TEXT("return"), ReturnGround, ReturnYaw);
    const FVector GateAt = JsonVector(Gate->GetArrayField(TEXT("at")));
    GateCentre = Course.World(O.X + GateAt.X, O.Y + GateAt.Y);
    GateYaw = -float(Gate->GetNumberField(TEXT("yaw")));
    Master = AHippodromeFigure::Spawn(GetWorld(), TEXT("Hudson"), FString(), MasterGround, MasterYaw);
    UE_LOG(LogTemp, Display, TEXT("Hippodrome: %d meshes at %s, lap %.1f m, gate at %.1f m, master %s"), Placed, *GetActorLocation().ToString(),
        Course.Lap, Course.GateS, Master.IsValid() ? TEXT("standing") : TEXT("MISSING"));
    FActorSpawnParameters Params; Params.Owner = this;
    if (JapanNetwork::Allows(GetWorld(), JapanNetwork::EActivity::Race))
        if (AHorseRace* Race = GetWorld()->SpawnActor<AHorseRace>(Params)) Race->Bind(this);
    return true;
}
