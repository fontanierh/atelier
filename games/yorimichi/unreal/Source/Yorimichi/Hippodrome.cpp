#include "Hippodrome.h"
#include "AtelierData.h"
#include "Components/StaticMeshComponent.h"
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
    Spot(TEXT("return"), ReturnGround, ReturnYaw);
    UE_LOG(LogTemp, Display, TEXT("Hippodrome: %d meshes at %s, lap %.1f m"), Placed, *GetActorLocation().ToString(), Course.Lap);
    return true;
}
