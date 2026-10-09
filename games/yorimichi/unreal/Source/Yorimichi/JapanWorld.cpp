#include "JapanWorld.h"
#include "JapanGameplayCollision.h"
#include "AtelierData.h"
#include "HarborLook.h"
#include "PhysicsEngine/BodySetup.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/BoxComponent.h"
#include "Components/SphereComponent.h"
#include "Components/PostProcessComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/DirectionalLight.h"
#include "Components/LightComponent.h"
#include "EngineUtils.h"
#include "Engine/StaticMesh.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "Kismet/GameplayStatics.h"
#include "Camera/PlayerCameraManager.h"
#include "LeafStorm.h"
#include "GullFlock.h"
#include "VillageLife.h"
#include "MegaRamp.h"
#include "SkatePark.h"
#include "SuperUltraMegaPark.h"
#include "Hippodrome.h"
#include "ZeppelinService.h"
#include "SeeThrough.h"

AJapanWorld::AJapanWorld()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

void AJapanWorld::BeginPlay()
{
    Super::BeginPlay();
    Load();
}

static UStaticMesh* LoadMesh(const FString& Name)
{
    const FString Path = FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Name, *Name);
    return LoadObject<UStaticMesh>(nullptr, *Path);
}

void AJapanWorld::Load()
{
    const double Started = FPlatformTime::Seconds();
    TArray<FString> Incomplete;
    const FString JsonPath = AtelierDataPath(TEXT("world.json"));
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *JsonPath)) { UE_LOG(LogTemp, Error, TEXT("world.json not found at %s"), *JsonPath); return; }
    TSharedPtr<FJsonObject> Root;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid()) { UE_LOG(LogTemp, Error, TEXT("world.json parse failed")); return; }

    // The tree house's build (world/regions/treehouse/build.py) writes what depends on its meshes to a file of its
    // own: prop instances join the world's, and its lights and rooms join world['treehouse'].
    TSharedPtr<FJsonObject> HouseRuntime;
    const TSharedPtr<FJsonObject>* HouseLayout=nullptr;
    if(Root->TryGetObjectField(TEXT("treehouse"),HouseLayout) &&
       (HouseRuntime=AtelierReadJson(FPaths::GetPath(JsonPath)/TEXT("treehouse/runtime.json"))))
    {
        auto Instances=Root->GetObjectField(TEXT("instances"));
        for(const auto& Pair:HouseRuntime->GetObjectField(TEXT("instances"))->Values)
        {
            TArray<TSharedPtr<FJsonValue>> Combined;
            const TArray<TSharedPtr<FJsonValue>>* Prior=nullptr;
            if(Instances->TryGetArrayField(Pair.Key,Prior)) Combined=*Prior;
            Combined.Append(Pair.Value->AsArray());Instances->SetArrayField(Pair.Key,Combined);
        }
        for(const auto& Pair:HouseRuntime->Values)
            if(Pair.Key!=TEXT("instances")) (*HouseLayout)->SetField(Pair.Key,Pair.Value);
    }

    // Optional independently generated eastern district. Keep the original world
    // and southwest work untouched; append instance groups before creating HISMs.
    const FString CityPath=FPaths::GetPath(JsonPath)/TEXT("hidamari/city.json");
    TSharedPtr<FJsonObject> City=AtelierReadJson(CityPath);
    if(City)
    {
        auto Instances=Root->GetObjectField(TEXT("instances"));
        // The old distant scenery inside the new playable district must disappear.
        for(auto& Pair:Instances->Values)
        {
            if(!FString(Pair.Key).StartsWith(TEXT("Tree"))) continue;
            TArray<TSharedPtr<FJsonValue>> Kept;
            for(const auto& Item:Pair.Value->AsArray())
            {
                const auto& P=Item->AsArray();
                const double X=P[0]->AsNumber(),Y=P[1]->AsNumber();
                const bool InCity=X>300 && X<2200 && Y>-450 && Y<1600;
                const bool InNorth=X>-700 && X<2400 && Y>500 && Y<3000;
                if(!InCity && !InNorth) Kept.Add(Item);
            }
            Pair.Value=MakeShared<FJsonValueArray>(Kept);
        }
        for(const auto& Pair:City->GetObjectField(TEXT("instances"))->Values)
        {
            TArray<TSharedPtr<FJsonValue>> Combined;
            const TArray<TSharedPtr<FJsonValue>>* Prior=nullptr;
            if(Instances->TryGetArrayField(Pair.Key,Prior)) Combined=*Prior;
            Combined.Append(Pair.Value->AsArray());Instances->SetArrayField(Pair.Key,Combined);
        }
        // Hidamari's late-afternoon grade over the whole city (location.json city_bounds) and the arrival hillside west
        // of it (x 280), out over the harbour to the lighthouse (y -280) and up to 700 m, so the town seen from a glide
        // above it keeps the same light: the global sky light and grade's cool shadows turn its cream plaster pale
        // blue, so it also white-balances warmer. The district grades below (priority 2) take precedence inside.
        UBoxComponent* CityBounds=NewObject<UBoxComponent>(this);
        CityBounds->SetupAttachment(RootComponent);
        CityBounds->SetRelativeLocation(ToUE(770,40,330));
        CityBounds->SetBoxExtent(FVector(49000,32000,37000));
        CityBounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        CityBounds->SetCollisionResponseToAllChannels(ECR_Ignore);
        CityBounds->SetGenerateOverlapEvents(false);
        CityBounds->SetCanEverAffectNavigation(false);
        CityBounds->RegisterComponent();
        UPostProcessComponent* CityGrade=NewObject<UPostProcessComponent>(this);
        CityGrade->SetupAttachment(CityBounds);
        CityGrade->bUnbound=false;CityGrade->BlendRadius=4000;CityGrade->Priority=1;
        CityGrade->Settings.bOverride_SceneColorTint=true;
        CityGrade->Settings.SceneColorTint=FLinearColor(1.09,.99,.83);
        CityGrade->Settings.bOverride_ColorGainShadows=true;
        CityGrade->Settings.ColorGainShadows=FVector4(1.07,1.0,.88,1);
        CityGrade->Settings.bOverride_ColorGainHighlights=true;
        CityGrade->Settings.ColorGainHighlights=FVector4(1.05,1.0,.92,1);
        CityGrade->Settings.bOverride_ColorContrast=true;
        CityGrade->Settings.ColorContrast=FVector4(1.04,1.04,1.04,1);
        CityGrade->Settings.bOverride_WhiteTemp=true;
        CityGrade->Settings.WhiteTemp=7200;
        CityGrade->RegisterComponent();
        float CityGradeDistance=0.f;
        UE_LOG(LogTemp,Display,TEXT("City grade bounds: lanes=%d aerial=%d arrival=%d forest=%d"),CityGrade->EncompassesPoint(ToUE(1100,-46,30),0.f,&CityGradeDistance),
            CityGrade->EncompassesPoint(ToUE(800,40,650),0.f,&CityGradeDistance),
            CityGrade->EncompassesPoint(ToUE(330,80,30),0.f,&CityGradeDistance),CityGrade->EncompassesPoint(ToUE(100,0,30),0.f,&CityGradeDistance));
        // Seen from a glide above the town, every roof and street faces the sky light, so nothing is dark: the darkest
        // pixels sat at 99/255 against 30 in a street view. Contrast alone pivots on mid grey, where those darks already
        // are, so the black point comes down (a negative offset) with a little more colour, from 90 m up (blending in
        // from 60 m), the city grade's warmth kept. Its own box over the same ground, above the district grades.
        UBoxComponent* GlideBounds=NewObject<UBoxComponent>(this);
        GlideBounds->SetupAttachment(RootComponent);
        GlideBounds->SetRelativeLocation(ToUE(770,40,395));
        GlideBounds->SetBoxExtent(FVector(49000,32000,30500));
        GlideBounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        GlideBounds->SetCollisionResponseToAllChannels(ECR_Ignore);
        GlideBounds->SetGenerateOverlapEvents(false);
        GlideBounds->SetCanEverAffectNavigation(false);
        GlideBounds->RegisterComponent();
        UPostProcessComponent* GlideGrade=NewObject<UPostProcessComponent>(this);
        GlideGrade->SetupAttachment(GlideBounds);
        GlideGrade->bUnbound=false;GlideGrade->BlendRadius=3000;GlideGrade->Priority=2;
        GlideGrade->Settings.bOverride_ColorContrast=true;
        GlideGrade->Settings.ColorContrast=FVector4(1.1,1.1,1.1,1);
        GlideGrade->Settings.bOverride_ColorSaturation=true;
        GlideGrade->Settings.ColorSaturation=FVector4(1.15,1.15,1.15,1);
        GlideGrade->Settings.bOverride_ColorOffset=true;
        GlideGrade->Settings.ColorOffset=FVector4(-.03,-.03,-.03,0);
        GlideGrade->RegisterComponent();
        float GlideGradeDistance=0.f;
        UE_LOG(LogTemp,Display,TEXT("Glide grade bounds: aerial=%d street=%d"),GlideGrade->EncompassesPoint(ToUE(800,40,650),0.f,&GlideGradeDistance),
            GlideGrade->EncompassesPoint(ToUE(1100,-46,30),0.f,&GlideGradeDistance));
        // A gentle local warm grade matches the sheltered arcade's art direction.
        // Blend at its approaches; leave every other district and user setting alone.
        UBoxComponent* ArcadeBounds=NewObject<UBoxComponent>(this);
        ArcadeBounds->SetupAttachment(RootComponent);
        ArcadeBounds->SetRelativeLocation(ToUE(660,75,18));
        ArcadeBounds->SetBoxExtent(FVector(6500,1800,1400));
        ArcadeBounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        ArcadeBounds->SetCollisionResponseToAllChannels(ECR_Ignore);
        ArcadeBounds->SetGenerateOverlapEvents(false);
        ArcadeBounds->SetCanEverAffectNavigation(false);
        ArcadeBounds->RegisterComponent();
        UPostProcessComponent* ArcadeGrade=NewObject<UPostProcessComponent>(this);
        ArcadeGrade->SetupAttachment(ArcadeBounds);
        ArcadeGrade->bUnbound=false;ArcadeGrade->BlendRadius=1000;ArcadeGrade->Priority=2;
        ArcadeGrade->Settings.bOverride_SceneColorTint=true;
        ArcadeGrade->Settings.SceneColorTint=FLinearColor(1.08,.94,.75);
        ArcadeGrade->Settings.bOverride_ColorContrast=true;
        ArcadeGrade->Settings.ColorContrast=FVector4(1.08,1.08,1.08,1);
        ArcadeGrade->RegisterComponent();
        float ArcadeGradeDistance=0.f;
        const bool bArcadeGradeActive=ArcadeGrade->EncompassesPoint(ToUE(620,75,17),0.f,&ArcadeGradeDistance);
        UE_LOG(LogTemp,Display,TEXT("Arcade grade bounds: inside=%d distance=%.2f"),bArcadeGradeActive,ArcadeGradeDistance);
        // Short-range shop practicals: no shadow maps and a generous distance fade.
        const TArray<TSharedPtr<FJsonValue>>* ArcadeLights=nullptr;
        for (const TCHAR* Field : {TEXT("arcade_lights"),TEXT("plaza_lights")})
        if (City->TryGetArrayField(Field,ArcadeLights))
            for (const auto& LightPosition:*ArcadeLights)
            {
                const auto& P=LightPosition->AsArray();
                if (P.Num()!=3) continue;
                UPointLightComponent* Light=NewObject<UPointLightComponent>(this);
                Light->SetupAttachment(RootComponent);
                Light->SetRelativeLocation(ToUE(P[0]->AsNumber(),P[1]->AsNumber(),P[2]->AsNumber()));
                Light->SetMobility(EComponentMobility::Movable);
                Light->SetIntensityUnits(ELightUnits::Lumens);
                Light->SetIntensity(350.f);
                Light->SetLightColor(FLinearColor(1.f,.68f,.35f));
                Light->SetAttenuationRadius(420.f);
                Light->SetCastShadows(false);
                Light->SetVolumetricScatteringIntensity(0.f);
                Light->SetMaxDrawDistance(6500.f);
                Light->SetMaxDistanceFadeRange(2000.f);
                Light->RegisterComponent();
            }
        UBoxComponent* PlazaBounds=NewObject<UBoxComponent>(this);
        PlazaBounds->SetupAttachment(RootComponent);
        PlazaBounds->SetRelativeLocation(ToUE(730,170,30));
        PlazaBounds->SetBoxExtent(FVector(8500,6000,2400));
        PlazaBounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        PlazaBounds->SetCollisionResponseToAllChannels(ECR_Ignore);
        PlazaBounds->SetGenerateOverlapEvents(false);
        PlazaBounds->SetCanEverAffectNavigation(false);
        PlazaBounds->RegisterComponent();
        UPostProcessComponent* PlazaGrade=NewObject<UPostProcessComponent>(this);
        PlazaGrade->SetupAttachment(PlazaBounds);PlazaGrade->bUnbound=false;
        PlazaGrade->BlendRadius=1500;PlazaGrade->Priority=2;
        PlazaGrade->Settings.bOverride_SceneColorTint=true;
        PlazaGrade->Settings.SceneColorTint=FLinearColor(1.07,.96,.83);
        PlazaGrade->Settings.bOverride_ColorContrast=true;
        PlazaGrade->Settings.ColorContrast=FVector4(1.05,1.05,1.05,1);
        PlazaGrade->RegisterComponent();
        float PlazaGradeDistance=0.f;
        UE_LOG(LogTemp,Display,TEXT("Plaza grade bounds: inside=%d"),PlazaGrade->EncompassesPoint(ToUE(675,120,23),0.f,&PlazaGradeDistance));

        InitializeHarborLook(this);
        InitializeGardenBridgeLook(this);
        bHidamariLoaded=true;
        const TArray<TSharedPtr<FJsonValue>>* Bounds=nullptr;
        if(City->TryGetArrayField(TEXT("bounds"),Bounds) && Bounds->Num()==4)
        {
            const FVector A=ToUE((*Bounds)[0]->AsNumber(),(*Bounds)[1]->AsNumber(),0),B=ToUE((*Bounds)[2]->AsNumber(),(*Bounds)[3]->AsNumber(),0);
            TownBounds=FBox2D(FVector2D(FMath::Min(A.X,B.X),FMath::Min(A.Y,B.Y)),FVector2D(FMath::Max(A.X,B.X),FMath::Max(A.Y,B.Y)));
        }
        UE_LOG(LogTemp,Display,TEXT("Hidamari city extension loaded"));
    }

    // Raw little-endian float heights accompany world.json. Missing/old exports
    // retain the raycast fallback, so an existing scene remains loadable.
    GroundResolution = Root->GetIntegerField(TEXT("n"));
    GroundSize = Root->GetNumberField(TEXT("size")) * 100.f;
    TArray<uint8> HeightBytes;
    const int64 HeightCount = int64(GroundResolution) * GroundResolution;
    if (GroundResolution >= 2 && GroundResolution <= 4096 && GroundSize > 0.f &&
        FFileHelper::LoadFileToArray(HeightBytes, *(FPaths::GetPath(JsonPath) / TEXT("heightmap.bin"))) &&
        HeightBytes.Num() == HeightCount * sizeof(float))
    {
        GroundHeights.SetNumUninitialized(HeightCount);
        FMemory::Memcpy(GroundHeights.GetData(), HeightBytes.GetData(), HeightBytes.Num());
        for (float H : GroundHeights)
            if (!FMath::IsFinite(H)) { GroundHeights.Empty(); break; }
    }
    UE_LOG(LogTemp, Log, TEXT("particle heightfield: %d samples"), GroundHeights.Num());

    const TArray<TSharedPtr<FJsonValue>>* PS = nullptr;
    if (Root->TryGetArrayField(TEXT("player_start"), PS) && PS->Num() >= 4)
        PlayerStart = FTransform(FRotator(0, -(*PS)[3]->AsNumber(), 0), ToUE((*PS)[0]->AsNumber(), (*PS)[1]->AsNumber(), (*PS)[2]->AsNumber()));
    const TArray<TSharedPtr<FJsonValue>>* SH = nullptr;
    if (Root->TryGetArrayField(TEXT("shots"), SH))
        for (const TSharedPtr<FJsonValue>& V : *SH)
        {
            const TArray<TSharedPtr<FJsonValue>>& A = V->AsArray();
            if (A.Num() < 5) continue;
            FWorldShot S; S.Location = ToUE(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()); S.Rotation = FRotator(A[4]->AsNumber(), -A[3]->AsNumber(), 0);
            Shots.Add(S);
        }

    const TArray<TSharedPtr<FJsonValue>>* WD = nullptr;
    if (Root->TryGetArrayField(TEXT("wind_dir"), WD) && WD->Num() >= 2) WindDir = FVector((*WD)[0]->AsNumber(), -(*WD)[1]->AsNumber(), 0).GetSafeNormal();
    WindSpeed = Root->HasField(TEXT("wind_speed")) ? Root->GetNumberField(TEXT("wind_speed")) * 100.0 : 350.f;
    // The skate pier clears its own ground of trees, bushes, grass and litter (world/regions/skatepark/park.json).
    const FString ParkPath = AtelierDataPath(TEXT("skatepark/park.json"));
    TArray<TArray<FVector2D>> ParkClearance = ASkatePark::LoadClearance(ParkPath);
    const FString CommunityParkPath = AtelierDataPath(TEXT("communitypark/park.json"));
    ParkClearance.Append(ASkatePark::LoadClearance(CommunityParkPath));
    // The hippodrome on the slope north of Hidamari (docs/HIPPODROME.md) keeps its oval and stands clear too.
    const FString HippodromePath = AtelierDataPath(TEXT("hippodrome/hippodrome.json"));
    ParkClearance.Append(ASkatePark::LoadClearance(HippodromePath));
    int32 Cleared = 0;
    // Playable ground far from the origin, such as the forest round the Mega Park (megapark/forest.py): the detailed
    // trees there are near ones, with shadows, collision and the camera fade; the low-poly crowns stay backdrop.
    TArray<FBox2D> NearTrees;
    const TArray<TSharedPtr<FJsonValue>>* NearBoxes = nullptr;
    if (City.IsValid() && City->TryGetArrayField(TEXT("near_trees"), NearBoxes))
        for (const TSharedPtr<FJsonValue>& V : *NearBoxes)
        {
            const TArray<TSharedPtr<FJsonValue>>& B = V->AsArray();
            if (B.Num() < 4) continue;
            const FVector A = ToUE(B[0]->AsNumber(), B[1]->AsNumber(), 0), C = ToUE(B[2]->AsNumber(), B[3]->AsNumber(), 0);
            NearTrees.Add(FBox2D(FVector2D(FMath::Min(A.X, C.X), FMath::Min(A.Y, C.Y)), FVector2D(FMath::Max(A.X, C.X), FMath::Max(A.Y, C.Y))));
        }
    const TSharedPtr<FJsonObject>* Inst = nullptr;
    if (Root->TryGetObjectField(TEXT("instances"), Inst))
    {
        for (const auto& Pair : (*Inst)->Values)
        {
            const FString Key(Pair.Key);
            UStaticMesh* Mesh = LoadMesh(Key);
            if (!Mesh) { Incomplete.Add(TEXT("mesh ") + Key); UE_LOG(LogTemp, Warning, TEXT("missing mesh asset %s"), *Key); continue; }
            const bool bGrass = Key.StartsWith(TEXT("Grass"));
            const bool bBush = Key.StartsWith(TEXT("Bush"));
            const bool bTree = Key.StartsWith(TEXT("Tree")) || Key.StartsWith(TEXT("HD_NorthTree"));
            const bool bLitter = Key == TEXT("Litter");
            TArray<FTransform> Near, Distant;
            Near.Reserve(Pair.Value->AsArray().Num());
            for (const TSharedPtr<FJsonValue>& V : Pair.Value->AsArray())
            {
                const TArray<TSharedPtr<FJsonValue>>& A = V->AsArray();
                if (A.Num() < 5) continue;
                const double Sc = A[4]->AsNumber();
                const FVector Position = ToUE(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber());
                if (!ParkClearance.IsEmpty() && (bTree || bBush || bGrass || bLitter || Key.StartsWith(TEXT("Rock"))) && ASkatePark::Inside(ParkClearance, FVector2D(Position))) { ++Cleared; continue; }
                // The far-hill backdrop is outside the playable square. Keep its
                // silhouettes, but do not build thousands of useless physics bodies.
                const bool bCityTree=City.IsValid() && Position.X>30000 && Position.X<142000 && Position.Y>-50000 && Position.Y<30000;
                // The new trail is playable: nearby trunks cast shadows and
                // keep collision, while the distant summit forest stays cheap.
                const bool bNorthTrailTree=City.IsValid() && Position.X>85000 && Position.X<130000 && Position.Y>-125000 && Position.Y<=-50000;
                const bool bNearTree = Key.StartsWith(TEXT("Tree")) && NearTrees.ContainsByPredicate([&](const FBox2D& B) { return B.IsInside(FVector2D(Position)); });
                const bool bBackdrop = bTree && !bCityTree && !bNorthTrailTree && !bNearTree && FMath::Max(FMath::Abs(Position.X), FMath::Abs(Position.Y)) > GroundSize * 0.75f;
                (bBackdrop ? Distant : Near).Add(FTransform(FRotator(0, -A[3]->AsNumber(), 0), Position, FVector(Sc)));
            }
            auto AddGroup = [&](const TArray<FTransform>& Xs, bool bBackdrop)
            {
                if (Xs.IsEmpty()) return;
                UHierarchicalInstancedStaticMeshComponent* H = NewObject<UHierarchicalInstancedStaticMeshComponent>(this);
                H->SetStaticMesh(Mesh); H->SetupAttachment(RootComponent);
                H->SetMobility(EComponentMobility::Static);
                if (Key==TEXT("HD_Harbor") || Key==TEXT("HD_Boat") || Key==TEXT("HD_Sea") || Key==TEXT("HD_Bollard"))
                    H->SetLightingChannels(true, true, false);
                H->SetCanEverAffectNavigation(false);
                const bool bWater=Key==TEXT("HD_Sea") || Key==TEXT("HD_InlandWater") || Key==TEXT("Lake_Water");
                // The city's overhead wires (HD_Wires, 10 m up) never stop a jump or the camera, and cast no shimmering lines.
                const bool bWires=Key==TEXT("HD_Wires");
                H->SetCollisionEnabled(bGrass || bBush || bLitter || bBackdrop || bWater || bWires || Key==TEXT("Lake_Plants") || Key==TEXT("HD_Boat") || (Key==TEXT("HD_ArcadeRoof") || Key==TEXT("HD_ArcadeLanterns") || Key==TEXT("HD_PlazaWater")) ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryOnly);
                // Camera see-through (docs/CAMERA.md): solid things stop the chase camera. Thin things (trees, bushes,
                // poles, lanterns, the torii, the tree house's props and thin pieces) let it through and fade whole
                // where they hide Cairo; the materials read how in custom primitive data 0. The far backdrop never
                // comes between, so it skips the fade's vertex work.
                const int32 Fade = bBackdrop ? JapanSeeThrough::FadeSolid : JapanSeeThrough::FadeMode(Key, Mesh);
                if (Fade != JapanSeeThrough::FadeSolid)
                {
                    H->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
                    H->SetCustomPrimitiveDataFloat(0, float(Fade));
                }
                if (Key == TEXT("TH_Frame") || Key == TEXT("TH_Dressing"))
                    UE_LOG(LogTemp, Display, TEXT("SEE-THROUGH %s: %s (%d uv channels)"), *Key,
                        Fade == JapanSeeThrough::FadePieces ? TEXT("fades piece by piece") : TEXT("fades at the lens only, no piece bake"),
                        Mesh->GetNumTexCoords(0));
                H->SetCastShadow(!bGrass && !bLitter && !bBackdrop && !bWater && !bWires && Key!=TEXT("HD_ArcadeRoof") && Key!=TEXT("HD_ArcadeLanterns") && Key!=TEXT("HD_PlazaWater"));
                if (bGrass || bLitter || bBackdrop) H->bAffectDistanceFieldLighting = false;
                if (bGrass) H->SetCullDistances(6000, 8000);
                else if (bBush) H->SetCullDistances(30000, 36000);
                else if (bLitter) H->SetCullDistances(7000, 9000);
                if (bTree || bBush) H->SetWorldPositionOffsetDisableDistance(18000);
                // The tree house: the camera arm keeps above the floor Cairo stands on there, and in hole mode its probe
                // passes the house (SetSeeThroughProbe). Its door curtains swing up to 60 cm out of their rest pose.
                if (Key.StartsWith(TEXT("TH_")))
                {
                    H->ComponentTags.Add(JapanSeeThrough::Tag);
                    SeeThroughGroups.Add(H);
                    if (Key == TEXT("TH_Dressing")) H->SetBoundsScale(1.05f);
                }
                H->bAutoRebuildTreeOnInstanceChanges = false;
                H->RegisterComponent();
                H->AddInstances(Xs, false, false, false);
                H->BuildTreeIfOutdated(true, true);
                H->bAutoRebuildTreeOnInstanceChanges = true;
                TotalInstances += Xs.Num(); Groups.Add(H);
                if (bBackdrop) BackdropGroups.Add(H);
            };
            AddGroup(Near, false); AddGroup(Distant, true);
        }
    }
    if (UStaticMesh* Dome = LoadMesh(TEXT("SkyDome")))
    {
        SkyDome = NewObject<UStaticMeshComponent>(this, TEXT("SkyDome"));
        SkyDome->SetStaticMesh(Dome); SkyDome->SetupAttachment(RootComponent);
        SkyDome->SetWorldScale3D(FVector(20000.0));           // 1 m sphere -> 20 km
        SkyDome->SetCastShadow(false); SkyDome->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        SkyDome->bVisibleInRealTimeSkyCaptures = true;
        SkyDome->RegisterComponent();
    }
    if (UStaticMesh* SeaMesh = LoadMesh(TEXT("Sea")))
    {
        Sea = NewObject<UStaticMeshComponent>(this, TEXT("Sea"));
        Sea->SetStaticMesh(SeaMesh); Sea->SetupAttachment(RootComponent);
        // Only the boat supports a rider at sea level. Walking off shore uses safe recovery.
        Sea->SetCastShadow(false);Sea->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Sea->SetGenerateOverlapEvents(false);
        Sea->RegisterComponent();
    }
    bLoaded = true;
    // The tree house (world/regions/treehouse): warm lantern and room lights, [x, y, z, lumens, radius m, shadows],
    // a local golden grade inside its box (layout.py) and a dimmer look inside each room (build.py, runtime.json).
    const TSharedPtr<FJsonObject>* House=nullptr;
    if (Root->TryGetObjectField(TEXT("treehouse"),House))
    {
        const TArray<TSharedPtr<FJsonValue>>* Lights=nullptr;
        int32 Count=0;
        if ((*House)->TryGetArrayField(TEXT("lights"),Lights))
            for (const auto& V:*Lights)
            {
                const auto& P=V->AsArray();
                if (P.Num()<5) continue;
                UPointLightComponent* Light=NewObject<UPointLightComponent>(this);
                Light->SetupAttachment(RootComponent);
                Light->SetRelativeLocation(ToUE(P[0]->AsNumber(),P[1]->AsNumber(),P[2]->AsNumber()));
                Light->SetMobility(EComponentMobility::Movable);
                Light->SetIntensityUnits(ELightUnits::Lumens);
                Light->SetIntensity(P[3]->AsNumber());
                Light->SetLightColor(FLinearColor(1.f,.74f,.48f));
                Light->SetAttenuationRadius(P[4]->AsNumber()*100.f);
                Light->SetSourceRadius(6.f);
                Light->SetCastShadows(P.Num()>5 && P[5]->AsNumber()>0);
                Light->SetVolumetricScatteringIntensity(0.f);
                Light->SetMaxDrawDistance(12000.f);
                Light->SetMaxDistanceFadeRange(3000.f);
                Light->RegisterComponent();
                ++Count;
            }
        const TSharedPtr<FJsonObject>* Grade=nullptr;
        if ((*House)->TryGetObjectField(TEXT("grade"),Grade))
        {
            const auto& C=(*Grade)->GetArrayField(TEXT("center"));
            const auto& X=(*Grade)->GetArrayField(TEXT("extent"));
            const auto& T=(*Grade)->GetArrayField(TEXT("tint"));
            UBoxComponent* Bounds=NewObject<UBoxComponent>(this);
            Bounds->SetupAttachment(RootComponent);
            Bounds->SetRelativeLocation(ToUE(C[0]->AsNumber(),C[1]->AsNumber(),C[2]->AsNumber()));
            Bounds->SetBoxExtent(FVector(X[0]->AsNumber(),X[1]->AsNumber(),X[2]->AsNumber())*100.);
            Bounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
            Bounds->SetCollisionResponseToAllChannels(ECR_Ignore);
            Bounds->SetGenerateOverlapEvents(false);
            Bounds->SetCanEverAffectNavigation(false);
            Bounds->RegisterComponent();
            UPostProcessComponent* Look=NewObject<UPostProcessComponent>(this);
            Look->SetupAttachment(Bounds);
            Look->bUnbound=false;Look->BlendRadius=(*Grade)->GetNumberField(TEXT("blend"))*100.;Look->Priority=2;
            Look->Settings.bOverride_SceneColorTint=true;
            Look->Settings.SceneColorTint=FLinearColor(T[0]->AsNumber(),T[1]->AsNumber(),T[2]->AsNumber());
            const double Sat=(*Grade)->GetNumberField(TEXT("saturation")),Con=(*Grade)->GetNumberField(TEXT("contrast"));
            Look->Settings.bOverride_ColorSaturation=true;Look->Settings.ColorSaturation=FVector4(Sat,Sat,Sat,1);
            Look->Settings.bOverride_ColorContrast=true;Look->Settings.ColorContrast=FVector4(Con,Con,Con,1);
            Look->Settings.bOverride_BloomIntensity=true;Look->Settings.BloomIntensity=(*Grade)->GetNumberField(TEXT("bloom"));
            Look->RegisterComponent();
        }
        // Inside each room a lower-key, less saturated look (the paintings' rooms are dim wood lit by lanterns and
        // window light): boxes [centre, half extent, yaw] or spheres [centre, radius] from treehouse/build.py.
        const TSharedPtr<FJsonObject>* RoomLook=nullptr;
        const TArray<TSharedPtr<FJsonValue>>* Rooms=nullptr;
        int32 RoomCount=0;
        if ((*House)->TryGetObjectField(TEXT("room_grade"),RoomLook) && (*House)->TryGetArrayField(TEXT("rooms"),Rooms))
            for (const auto& V:*Rooms)
            {
                const auto& Room=V->AsObject();
                const auto& C=Room->GetArrayField(TEXT("center"));
                UShapeComponent* Shape=nullptr;
                if (Room->HasField(TEXT("radius")))
                {
                    USphereComponent* Sphere=NewObject<USphereComponent>(this);
                    Sphere->SetSphereRadius(Room->GetNumberField(TEXT("radius"))*100.);
                    Shape=Sphere;
                }
                else
                {
                    const auto& X=Room->GetArrayField(TEXT("extent"));
                    UBoxComponent* Box=NewObject<UBoxComponent>(this);
                    Box->SetBoxExtent(FVector(X[0]->AsNumber(),X[1]->AsNumber(),X[2]->AsNumber())*100.);
                    Shape=Box;
                }
                Shape->SetupAttachment(RootComponent);
                Shape->SetRelativeLocation(ToUE(C[0]->AsNumber(),C[1]->AsNumber(),C[2]->AsNumber()));
                Shape->SetRelativeRotation(FRotator(0,-Room->GetNumberField(TEXT("yaw")),0));
                FSeeThroughRoom& Cut=SeeThroughRooms.AddDefaulted_GetRef();
                Cut.Center=ToUE(C[0]->AsNumber(),C[1]->AsNumber(),C[2]->AsNumber());
                Cut.Yaw=FMath::DegreesToRadians(-Room->GetNumberField(TEXT("yaw")));
                Cut.bRound=Room->HasField(TEXT("radius"));
                if (Cut.bRound)
                {
                    // A round room's height comes apart from its radius; older runtime files had none: 1.8 m.
                    const double Radius=Room->GetNumberField(TEXT("radius"));
                    double Half=1.8;
                    Room->TryGetNumberField(TEXT("half_height"),Half);
                    Cut.Extent=FVector(Radius,Radius,Half)*100.;
                }
                else
                {
                    const auto& X=Room->GetArrayField(TEXT("extent"));
                    Cut.Extent=FVector(X[0]->AsNumber(),X[1]->AsNumber(),X[2]->AsNumber())*100.;
                }
                Shape->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
                Shape->SetCollisionResponseToAllChannels(ECR_Ignore);
                Shape->SetGenerateOverlapEvents(false);
                Shape->SetCanEverAffectNavigation(false);
                Shape->RegisterComponent();
                const auto& T=(*RoomLook)->GetArrayField(TEXT("tint"));
                UPostProcessComponent* Look=NewObject<UPostProcessComponent>(this);
                Look->SetupAttachment(Shape);
                Look->bUnbound=false;Look->BlendRadius=(*RoomLook)->GetNumberField(TEXT("blend"))*100.;Look->Priority=3;
                Look->Settings.bOverride_SceneColorTint=true;
                Look->Settings.SceneColorTint=FLinearColor(T[0]->AsNumber(),T[1]->AsNumber(),T[2]->AsNumber());
                const double Sat=(*RoomLook)->GetNumberField(TEXT("saturation")),Con=(*RoomLook)->GetNumberField(TEXT("contrast"));
                Look->Settings.bOverride_ColorSaturation=true;Look->Settings.ColorSaturation=FVector4(Sat,Sat,Sat,1);
                Look->Settings.bOverride_ColorContrast=true;Look->Settings.ColorContrast=FVector4(Con,Con,Con,1);
                Look->Settings.bOverride_AutoExposureBias=true;Look->Settings.AutoExposureBias=(*RoomLook)->GetNumberField(TEXT("exposure"));
                Look->RegisterComponent();
                ++RoomCount;
            }
        UE_LOG(LogTemp,Display,TEXT("TREEHOUSE lights %d grade %d rooms %d"),Count,Grade!=nullptr,RoomCount);
    }
    const TSharedPtr<FJsonObject>* Village=nullptr;
    if (Root->TryGetObjectField(TEXT("village"),Village))
    {
        VillageRecord=*Village;
        if (GetNetMode()!=NM_DedicatedServer) if (auto* Life=GetWorld()->SpawnActor<AVillageLife>()) Life->Initialize(this,*Village);
    }
    const TSharedPtr<FJsonObject>* Lake=nullptr;
    if(Root->TryGetObjectField(TEXT("forest_lake"),Lake))
    {
        const auto& C=(*Lake)->GetArrayField(TEXT("center"));
        const auto& R=(*Lake)->GetArrayField(TEXT("radii"));
        const auto& S=(*Lake)->GetArrayField(TEXT("safe_shore"));
        ForestLakeCenter=ToUE(C[0]->AsNumber(),C[1]->AsNumber(),(*Lake)->GetNumberField(TEXT("water_height")));
        ForestLakeRadii=FVector2D(R[0]->AsNumber()*100.,R[1]->AsNumber()*100.);
        ForestLakeSafeShore=ToUE(S[0]->AsNumber(),S[1]->AsNumber(),S[2]->AsNumber());
        bForestLakeLoaded=true;
    }
    const TSharedPtr<FJsonObject>* ZeppelinData=nullptr;
    if(Root->TryGetObjectField(TEXT("zeppelin"),ZeppelinData))
    { Zeppelin=GetWorld()->SpawnActor<AZeppelinService>();if(Zeppelin)Zeppelin->Initialize(*ZeppelinData); }
    const TSharedPtr<FJsonObject>* Mega=nullptr;
    if(Root->TryGetObjectField(TEXT("mega"),Mega))
    {
        auto* Ramp=GetWorld()->SpawnActor<AMegaRamp>();
        if (Ramp) Ramp->Initialize(*Mega);
        if (!Ramp || !Ramp->bGameplayReady) Incomplete.Add(TEXT("mini-mega"));
    }
    else Incomplete.Add(TEXT("mini-mega data"));
    auto InstallPark = [&](const FString& Path, const TCHAR* Label)
    {
        auto* Park = FPaths::FileExists(Path) ? GetWorld()->SpawnActor<ASkatePark>() : nullptr;
        if (!Park || !Park->Initialize(Path)) Incomplete.Add(Label);
    };
    InstallPark(ParkPath, TEXT("skate pier"));
    // The Mega Park in the western foothills: the original meshes, riding collision and grind paths, placed (docs/MEGAPARK.md).
    const auto* MegaPark = ASuperUltraMegaPark::Spawn(GetWorld(), AtelierDataPath(TEXT("megapark/park.json")));
    if (!MegaPark || !MegaPark->bGameplayReady) Incomplete.Add(TEXT("mega park"));
    InstallPark(CommunityParkPath, TEXT("community park"));
    const auto* Hippodrome = AHippodrome::Spawn(GetWorld(), HippodromePath);
    if (!Hippodrome || !Hippodrome->bGameplayReady) Incomplete.Add(TEXT("hippodrome"));
    UE_LOG(LogTemp, Display, TEXT("SKATE PARK cleared %d vegetation instances"), Cleared);
    // The road guardrails are grindable: the W-beam's top edge is 85 cm over the rail line.
    if (USkateRailSubsystem* Rails = GetWorld()->GetSubsystem<USkateRailSubsystem>())
    {
        const TArray<TSharedPtr<FJsonValue>>* Runs = nullptr;
        if (Root->TryGetArrayField(TEXT("rail_runs"), Runs))
            for (int32 R = 0; R < Runs->Num(); ++R)
            {
                FSkateRail Rail; Rail.Id = FName(*FString::Printf(TEXT("guardrail_%d"), R));
                for (const auto& P : (*Runs)[R]->AsArray())
                {
                    const auto& A = P->AsArray();
                    if (A.Num() >= 3) Rail.Points.Add(ToUE(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber() + .85));
                }
                Rails->Add(MoveTemp(Rail));
            }
    }
    if(City.IsValid() && GetNetMode()!=NM_DedicatedServer)
        for(const auto& Group:City->GetArrayField(TEXT("resident_groups")))
            if(auto* Life=GetWorld()->SpawnActor<AVillageLife>()) Life->Initialize(this,Group->AsObject());
    WindMPC = LoadObject<UMaterialParameterCollection>(nullptr, TEXT("/Game/Japan/Materials/MPC_Wind.MPC_Wind"));
    if (GetNetMode()!=NM_DedicatedServer) GetWorld()->SpawnActor<ALeafStorm>(FVector::ZeroVector, FRotator::ZeroRotator);
    // gulls over the sea, a little off the middle of the road
    AGullFlock* Flock = GetNetMode()==NM_DedicatedServer ? nullptr : GetWorld()->SpawnActor<AGullFlock>(ToUE(20, -170, 45), FRotator::ZeroRotator);
    if (!City.IsValid()) Incomplete.Add(TEXT("Hidamari data"));
    if (HouseLayout && !HouseRuntime.IsValid()) Incomplete.Add(TEXT("tree house data"));
    if (TotalInstances == 0) Incomplete.Add(TEXT("world geometry"));
    JapanGameplayCollision::Install(GetWorld());
    BootstrapError = FString::Join(Incomplete, TEXT(", "));
    bGameplayReady = bLoaded && Incomplete.IsEmpty();
    if (!bGameplayReady) UE_LOG(LogTemp, Warning, TEXT("NETWORK world incomplete: %s"), *BootstrapError);
    UE_LOG(LogTemp, Log, TEXT("world loaded: %d groups, %d instances, %d shots, flock %d, %.1f ms"), Groups.Num(), TotalInstances, Shots.Num(), Flock ? 1 : 0, (FPlatformTime::Seconds() - Started) * 1000.0);
}

bool AJapanWorld::IsInSeeThroughRoom(int32 Index, const FVector& P, float Margin) const
{
    if (!SeeThroughRooms.IsValidIndex(Index)) return false;
    const FSeeThroughRoom& R = SeeThroughRooms[Index];
    const FVector D = P - R.Center;
    if (FMath::Abs(D.Z) > R.Extent.Z + Margin) return false;
    if (R.bRound) return FVector2D(D.X, D.Y).Size() <= R.Extent.X + Margin;
    // Into the room's frame (the same turn as the material's): x along the room's yaw.
    const double C = FMath::Cos(R.Yaw), S = FMath::Sin(R.Yaw);
    const double X = D.X * C + D.Y * S, Y = D.Y * C - D.X * S;
    return FMath::Abs(X) <= R.Extent.X + Margin && FMath::Abs(Y) <= R.Extent.Y + Margin;
}

int32 AJapanWorld::FindSeeThroughRoom(const FVector& P, float Margin) const
{
    for (int32 I = 0; I < SeeThroughRooms.Num(); ++I)
        if (IsInSeeThroughRoom(I, P, Margin)) return I;
    return INDEX_NONE;
}

void AJapanWorld::SetSeeThroughProbe(bool bIgnore)
{
    // Hole mode only (japan.SeeThroughHole 1). Only the chase camera's arm reads this (UJapanCameraArm sweeps without
    // these groups): the groups keep their collision, so other camera-channel traces still see the tree house.
    if (bIgnore == bSeeThroughProbeIgnored) return;
    bSeeThroughProbeIgnored = bIgnore;
    UE_LOG(LogTemp, Display, TEXT("SEE-THROUGH camera probe %s the tree house (%d groups)"), bIgnore ? TEXT("passes") : TEXT("stops at"), SeeThroughGroups.Num());
}

bool AJapanWorld::SampleGroundHeight(const FVector& Position, float& Height) const
{
    if (GroundHeights.IsEmpty()) return false;
    const float X = (Position.X / GroundSize + 0.5f) * (GroundResolution - 1);
    const float Y = (-Position.Y / GroundSize + 0.5f) * (GroundResolution - 1);
    if (X < 0.f || Y < 0.f || X > GroundResolution - 1 || Y > GroundResolution - 1) return false;
    const int32 I = FMath::Min(FMath::FloorToInt(X), GroundResolution - 2);
    const int32 J = FMath::Min(FMath::FloorToInt(Y), GroundResolution - 2);
    const int32 K = J * GroundResolution + I;
    Height = 100.f * FMath::Lerp(
        FMath::Lerp(GroundHeights[K], GroundHeights[K + 1], X - I),
        FMath::Lerp(GroundHeights[K + GroundResolution], GroundHeights[K + GroundResolution + 1], X - I), Y - J);
    // A small cosmetic clearance covers the road's six-centimetre surface offset.
    Height += 6.f;
    return true;
}

// Diagnosis only. `japan.HideGroups Tree_Broad;Bush` hides every instanced group whose mesh name
// contains one of those substrings, so one foliage family at a time can be priced and photographed
// without editing the world. Semicolons separate entries because -ExecCmds already splits on commas.
// Empty by default and never set by the game.
static TAutoConsoleVariable<FString> CVarHideGroups(TEXT("japan.HideGroups"),TEXT(""),
    TEXT("Semicolon-separated mesh-name substrings whose instanced groups are hidden (diagnosis only)."),
    ECVF_Cheat);

// Distance at which the far-hill backdrop forest fades out, in centimetres. 0 keeps the shipped
// behaviour, which is no cull distance at all on those groups. Diagnosis first; if it earns its
// place it becomes a desktop profile value, never a phone one.
static TAutoConsoleVariable<float> CVarBackdropCull(TEXT("japan.BackdropCull"),0.f,
    TEXT("Cull distance in cm for backdrop instanced groups (0 = never cull)."),ECVF_Cheat);

void AJapanWorld::ApplyGroupDiagnostics()
{
    const float Cull = CVarBackdropCull.GetValueOnGameThread();
    if (!FMath::IsNearlyEqual(Cull,AppliedBackdropCull))
    {
        AppliedBackdropCull = Cull;
        int32 Touched = 0;
        for (auto* Group : BackdropGroups)
            if (Group)
            {
                Group->SetCullDistances(Cull > 0.f ? FMath::RoundToInt(Cull*.8f) : 0,
                                        Cull > 0.f ? FMath::RoundToInt(Cull) : 0);
                ++Touched;
            }
        UE_LOG(LogTemp,Display,TEXT("DIAGNOSTIC backdrop cull %.0f cm on %d groups"),Cull,Touched);
    }
    const FString Wanted = CVarHideGroups.GetValueOnGameThread();
    if (Wanted == AppliedHideGroups) return;
    AppliedHideGroups = Wanted;
    TArray<FString> Parts;
    Wanted.ParseIntoArray(Parts,TEXT(";"));
    int32 Hidden = 0;
    for (auto* Group : Groups)
    {
        if (!Group || !Group->GetStaticMesh()) continue;
        const FString Name = Group->GetStaticMesh()->GetName();
        bool Match = false;
        for (const FString& Part : Parts)
            if (!Part.TrimStartAndEnd().IsEmpty() && Name.Contains(Part.TrimStartAndEnd())) Match = true;
        Group->SetVisibility(!Match,false);
        Hidden += Match ? 1 : 0;
    }
    UE_LOG(LogTemp,Display,TEXT("DIAGNOSTIC hide groups '%s': %d of %d instanced groups hidden"),
           *Wanted,Hidden,Groups.Num());
}

void AJapanWorld::ApplyPerformanceSettings(bool bPerformance)
{
    if (!bLoaded || AppliedPerformanceMode == int32(bPerformance)) return;
    for (auto* Group : Groups)
    {
        const FString Name = Group->GetStaticMesh()->GetName();
        if (Name.StartsWith(TEXT("Grass")))
            Group->SetCullDistances(bPerformance ? 3500 : 6000,bPerformance ? 5000 : 8000);
        if (Name.StartsWith(TEXT("Tree")) || Name.StartsWith(TEXT("Bush")))
            Group->SetWorldPositionOffsetDisableDistance(bPerformance ? 6000 : 18000);
    }
    AppliedPerformanceMode = int32(bPerformance);
}

void AJapanWorld::ApplyVolumetricFog(bool bOn, const FVolumetricFogLook& Look)
{
    TActorIterator<AExponentialHeightFog> It(GetWorld());
    UExponentialHeightFogComponent* Fog = It ? It->GetComponent() : nullptr;
    if (!Fog || (bFogApplied && (bOn ? AppliedFog == Look : !AppliedFog))) return;
    TActorIterator<ADirectionalLight> SunIt(GetWorld());
    ULightComponent* Sun = SunIt ? SunIt->GetLightComponent() : nullptr;
    if (!FogBase)
        FogBase = FFogBase{Fog->FogDensity, Fog->FogHeightFalloff, Fog->FogCutoffDistance, Fog->VolumetricFogDistance,
                           Sun ? Sun->VolumetricScatteringIntensity : 1.f, Fog->bEnableVolumetricFog};
    bFogApplied = true;
    if (!bOn)
    {
        AppliedFog.Reset();
        Fog->SetFogDensity(FogBase->Density); Fog->SetFogHeightFalloff(FogBase->Falloff);
        Fog->SetFogCutoffDistance(FogBase->Cutoff); Fog->SetVolumetricFogDistance(FogBase->Distance);
        Fog->SetVolumetricFog(FogBase->bVolumetric);
        if (Sun) Sun->SetVolumetricScatteringIntensity(FogBase->Shafts);
        return;
    }
    AppliedFog = Look;
    // The medium is the height fog's own: extinction 0.5 * density / 1000 per cm at the fog actor's height (sea level),
    // halving every 1000 / falloff cm up (83 m at 0.12): the shore and the valleys are mistiest, the forest lake (75 m)
    // has half as much. Twice the default density washed a low sun out to white.
    AppliedFogDensity = -1.f;
    UpdateFogDensity(0.f); Fog->SetFogHeightFalloff(FMath::Max(.001f, Look.Falloff));
    // Forward scattering: shafts and a halo toward the sun, still some from the side. 0.7 blew a low sun out.
    Fog->SetVolumetricFogScatteringDistribution(FMath::Clamp(Look.Scattering, -.9f, .9f));
    Fog->SetVolumetricFogAlbedo(FColor::White);
    Fog->SetVolumetricFogEmissive(FLinearColor::Black);
    Fog->SetVolumetricFogExtinctionScale(1.f);
    if (Sun) Sun->SetVolumetricScatteringIntensity(FMath::Max(0.f, Look.Shafts));
    // The grid's reach is the same in both profiles (Performance has half the slices). Everything beyond it is seen
    // through the whole grid's mist, so the reach sets the veil on every distant view: 90 m put ~30% over Hidamari from
    // the sea, 30 m ~10%. The near metres fade in so the character never wades through blocky froxels.
    const float Distance = FMath::Clamp(Look.Reach, 1000.f, 20000.f);
    Fog->SetVolumetricFogDistance(Distance);
    Fog->SetVolumetricFogStartDistance(0.f);
    Fog->SetVolumetricFogNearFadeInDistance(300.f);
    // No analytic height fog past the grid: everything farther (the sky dome too) is seen through the grid's mist and gets
    // no more, and the painted materials keep their own distance haze. Volumetric fog itself ignores the cutoff.
    Fog->SetFogCutoffDistance(Distance);
    Fog->SetVolumetricFog(true);
}

void AJapanWorld::UpdateFogDensity(float Dt)
{
    if (!AppliedFog) return;
    TActorIterator<AExponentialHeightFog> It(GetWorld());
    UExponentialHeightFogComponent* Fog = It ? It->GetComponent() : nullptr;
    if (!Fog) return;
    // How much of Hidamari the view holds: the camera's place and points up to 450 m along its look, each fully in the town
    // inside its bounds and fading out over 150 m, so the town keeps its contrast seen from the hill or the sea too. A
    // longer reach thinned the mist on the village road at the start, 550 m from the town and looking toward it.
    // Eased over about a second, so turning toward the town never pops the mist away.
    float Town = 0.f;
    if (TownBounds.bIsValid)
        if (const APlayerCameraManager* Camera = UGameplayStatics::GetPlayerCameraManager(this, 0))
        {
            const FVector C = Camera->GetCameraLocation();
            const FVector Ahead = Camera->GetCameraRotation().Vector().GetSafeNormal2D();
            for (const float Reach : {0.f, 15000.f, 30000.f, 45000.f})
            {
                const FVector P = C + Ahead * Reach;
                const float Outside = FMath::Sqrt(TownBounds.ComputeSquaredDistanceToPoint(FVector2D(P.X, P.Y)));
                Town = FMath::Max(Town, FMath::SmoothStep(0.f, 1.f, 1.f - Outside / 15000.f));
            }
        }
    TownView = Dt > 0.f ? FMath::FInterpTo(TownView, Town, Dt, 1.5f) : Town;
    const float Density = FMath::Max(0.f, AppliedFog->Density) * FMath::Lerp(1.f, FMath::Clamp(AppliedFog->Town, 0.f, 1.f), TownView);
    if (FMath::Abs(Density - AppliedFogDensity) < .0002f) return;     // each change re-sends the fog to the renderer
    Fog->SetFogDensity(Density);
    AppliedFogDensity = Density;
}

float AJapanWorld::WindStrength(const FVector& P, float T) const
{
    return FMath::Max(0.15f, 1.f + 0.45f * FMath::Sin(T * 0.37f + P.X * 0.0004f) + 0.3f * FMath::Sin(T * 1.1f + P.Y * 0.0007f) + 0.15f * FMath::Sin(T * 2.9f));
}

void AJapanWorld::Tick(float Dt)
{
    Super::Tick(Dt);
    if (GetNetMode()==NM_DedicatedServer) return;
    UpdateHarborLook(this);
    UpdateFogDensity(Dt);
    ApplyGroupDiagnostics();
    if (!WindMPC) return;
    UMaterialParameterCollectionInstance* I = GetWorld()->GetParameterCollectionInstance(WindMPC);
    if (!I) return;
    const float T = GetWorld()->GetTimeSeconds();
    if (APawn* P = UGameplayStatics::GetPlayerPawn(this, 0))
    {
        const FVector L = P->GetActorLocation();
        I->SetVectorParameterValue(TEXT("PlayerPos"), FLinearColor(L.X, L.Y, L.Z, 0.f));
        const FVector W = WindDir * WindStrength(L, T) * (WindSpeed / 350.f);
        I->SetVectorParameterValue(TEXT("Wind"), FLinearColor(W.X, W.Y, 0.f, 0.f));
    }
}
