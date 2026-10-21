#include "JapanWorld.h"
#include "AtelierData.h"
#include "JapanGameplayCollision.h"
#include "SkatePark.h"
#include "CollisionQueryParams.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

bool AJapanWorld::IsBrowserScene()
{
#if PLATFORM_HTML5
    return true;
#else
    return FParse::Param(FCommandLine::Get(), TEXT("browserpilot"));
#endif
}

void AJapanWorld::LoadBrowserScene()
{
    const auto Scene = AtelierReadJson(AtelierDataPath(TEXT("Browser/scene.json")));
    double Version = 0;
    FString Profile;
    const TArray<TSharedPtr<FJsonValue>>* Assets = nullptr;
    if (!Scene || !Scene->TryGetNumberField(TEXT("version"), Version) || Version != 1 ||
        !Scene->TryGetStringField(TEXT("profile"), Profile) || Profile != TEXT("skate-pier") ||
        !Scene->TryGetArrayField(TEXT("required_assets"), Assets) || Assets->IsEmpty())
    {
        BootstrapError = TEXT("Missing or invalid Browser/scene.json; build browser.scene");
        UE_LOG(LogTemp, Error, TEXT("BROWSER scene unavailable: %s"), *BootstrapError);
        return;
    }
    TArray<FString> Missing;
    for (const auto& Value : *Assets)
    {
        const FString Path = Value->AsString();
        if (!Path.StartsWith(TEXT("/Game/")) || !LoadObject<UObject>(nullptr, *Path)) Missing.Add(Path);
    }
    ASkatePark* Park = GetWorld()->SpawnActor<ASkatePark>();
    if (!Park || !Park->Initialize(AtelierDataPath(TEXT("Browser/park.json")))) Missing.Add(TEXT("skate pier geometry/rails"));
    if (Park)
    {
        PlayerStart = FTransform(FRotator(0, Park->ParkSpawnYaw, 0), Park->ParkSpawn);
        FHitResult Hit;
        const FVector P = Park->ParkSpawn;
        if (!GetWorld()->LineTraceSingleByChannel(Hit, P + FVector(0, 0, 200), P - FVector(0, 0, 500),
                                                  ECC_Visibility, FCollisionQueryParams(SCENE_QUERY_STAT(BrowserSpawn))))
            Missing.Add(TEXT("spawn riding collision"));
    }
    auto* Dome = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    auto* Sky = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Japan/Materials/M_Sky.M_Sky"));
    if (Dome && Sky)
    {
        SkyDome = NewObject<UStaticMeshComponent>(this, TEXT("SkyDome"));
        SkyDome->SetupAttachment(RootComponent); SkyDome->SetStaticMesh(Dome); SkyDome->SetMaterial(0, Sky);
        SkyDome->SetWorldScale3D(FVector(20000)); SkyDome->SetCastShadow(false);
        SkyDome->SetCollisionEnabled(ECollisionEnabled::NoCollision); SkyDome->RegisterComponent();
    }
    else Missing.Add(TEXT("painted sky"));
    JapanGameplayCollision::Install(GetWorld());
    BootstrapError = FString::Join(Missing, TEXT(", "));
    bLoaded = bGameplayReady = Missing.IsEmpty();
    if (bGameplayReady)
    { UE_LOG(LogTemp, Display, TEXT("BROWSER scene ready: skate pier, painted sky, collision and rails")); }
    else
    { UE_LOG(LogTemp, Error, TEXT("BROWSER scene incomplete: %s"), *BootstrapError); }
}
