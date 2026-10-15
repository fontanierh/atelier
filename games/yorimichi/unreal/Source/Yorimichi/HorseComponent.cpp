#include "HorseComponent.h"

#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "HorseRiderNode.h"
#include "JapanFootsteps.h"
#include "JapanGameplayCollision.h"
#include "JapanNetwork.h"
#include "JapanVehicleVisuals.h"
#include "LiveLibrary.h"
#include "PlayableCharacter.h"
#include "WandererCharacter.h"
#include "Animation/AnimSequence.h"
#include "Components/CapsuleComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

// Ride tuning and roster helpers. A named namespace: in a unity build an anonymous one would put these names in every
// later file's scope (a local Probes or Wrap would shadow them).
namespace HorseRide
{
    // Per EHorseRole: the rider's clip (A_<Rider> on his rig), the breed's roster clip, the HUD's word and whether it loops.
    struct FRoleClips { const TCHAR* Rider; const TCHAR* Horse; const TCHAR* Label; bool bLoop; };
    const FRoleClips Roles[] = {
        {TEXT("HorseIdle"), TEXT("Idle"), TEXT("Standing"), true},
        {TEXT("HorseIdleLook"), TEXT("IdleLook"), TEXT("Looking round"), false},
        {TEXT("HorseIdleGraze"), TEXT("IdleGraze"), TEXT("Grazing"), false},
        {TEXT("HorseIdleShake"), TEXT("IdleShake"), TEXT("Shaking"), false},
        {TEXT("HorseIdleFlehmen"), TEXT("IdleFlehmen"), TEXT("Sniffing"), false},
        {TEXT("HorseIdleAffection"), TEXT("IdleAffection"), TEXT("Nuzzling"), false},
        {TEXT("HorseWalk"), TEXT("Walk"), TEXT("Walk"), true},
        {TEXT("HorseTrot"), TEXT("Trot"), TEXT("Trot"), true},
        {TEXT("HorseCanter"), TEXT("Canter"), TEXT("Canter"), true},
        {TEXT("HorseGallop"), TEXT("Gallop"), TEXT("Gallop"), true},
        {TEXT("HorseSprint"), TEXT("Sprint"), TEXT("Sprint"), true},
        {TEXT("HorseMount"), TEXT("Idle"), TEXT("Getting on"), false},
        {TEXT("HorseDismount"), TEXT("Idle"), TEXT("Getting off"), false}};
    constexpr int32 RoleCount = int32(EHorseRole::Count);
    static_assert(UE_ARRAY_COUNT(Roles) == RoleCount, "one row per EHorseRole");
    // The shared game's checkpoint indexes the same order (JapanHorseState.cpp).
    static_assert(RoleCount == FJapanHorseState::RoleCount && int32(EHorseRole::Walk) == FJapanHorseState::IdleRoles &&
        int32(EHorseRole::Sprint) == FJapanHorseState::SprintRole && int32(EHorseRole::Mount) == FJapanHorseState::MountRole &&
        int32(EHorseRole::Dismount) == FJapanHorseState::DismountRole, "FJapanHorseState follows EHorseRole");
    const FRoleClips& RoleOf(EHorseRole Role) { return Roles[int32(Role)]; }
    const EHorseRole IdleVariants[] = {EHorseRole::IdleLook, EHorseRole::IdleGraze, EHorseRole::IdleShake,
                                       EHorseRole::IdleFlehmen, EHorseRole::IdleAffection};

    // PhaseTime's cap (FJapanHorseState::IsValid): getting on or off never lasts longer.
    constexpr float MaxPhaseTime = 10.f;
    // Each gait's top speed (cm/s); under IdleSpeed he stands. Alt (walk) and J (trot) hold the ride to a share of the
    // gallop; the sprint opens it up to SprintMaxSpeed.
    constexpr float IdleSpeed = 12.f, WalkMaxSpeed = 260.f, TrotMaxSpeed = 540.f, CanterMaxSpeed = 880.f;
    constexpr float GallopMaxSpeed = 1180.f, SprintMaxSpeed = 1480.f, WalkShare = .20f, JogShare = .42f;
    // Gathering speed (cm/s^2), riding on and sprinting; coasting with the reins slack; reining in.
    constexpr float Push = 520.f, SprintPush = 720.f, Coast = 420.f, ReinIn = 1400.f;
    // He gets off only once stopped (under 1.5 km/h), as off the bike.
    constexpr float DismountSpeed = 40.f;
    // The horse is longer than his capsule. Ahead of the saddle at a foreleg's knee height (above what the walking physics
    // steps up) and at the muzzle's (cm), a wall stops it. The reference breed's reach for every breed: the look replicates
    // outside the movement stream, so the simulation never reads it and a breed change mid-ride replays the same.
    struct FProbe { float Height, Reach; };
    const FProbe Probes[] = {{55.f, 80.f}, {150.f, 155.f}};
    // The front and back hooves, ahead of and behind the saddle, for the ground's pitch.
    constexpr float HoofSpan = 75.f;
    // How strongly the coat mask's pattern shows over the coat.
    constexpr float MaskStrength = .85f;

    // Rider space (assets/horses/build.py): metres, +X forward, +Y left, +Z up. The rider mesh: centimetres, +Y right.
    FVector FromRiderSpace(const TArray<TSharedPtr<FJsonValue>>& V)
    {
        return FVector(V[0]->AsNumber() * 100., -V[1]->AsNumber() * 100., V[2]->AsNumber() * 100.);
    }

    struct FContacts { FVector SaddleRoot, StirrupL, StirrupR, GripL, GripR; double SeatZ = 0., ScaleRatio = 1.; };
    bool ReadContacts(const TSharedPtr<FJsonObject>& Breed, FContacts& Out)
    {
        const TSharedPtr<FJsonObject>* Contacts = nullptr;
        if (!Breed->TryGetObjectField(TEXT("contacts"), Contacts) || !Contacts->IsValid()) return false;
        auto Point = [&](const TCHAR* Key, FVector& At)
        {
            const TArray<TSharedPtr<FJsonValue>>* V = nullptr;
            if (!(*Contacts)->TryGetArrayField(Key, V) || V->Num() != 3) return false;
            At = FromRiderSpace(*V);
            return true;
        };
        if (!Point(TEXT("saddle_root"), Out.SaddleRoot) || !Point(TEXT("stirrup_L"), Out.StirrupL) || !Point(TEXT("stirrup_R"), Out.StirrupR) ||
            !Point(TEXT("grip_L"), Out.GripL) || !Point(TEXT("grip_R"), Out.GripR) || !(*Contacts)->TryGetNumberField(TEXT("seat_z"), Out.SeatZ))
            return false;
        if (!(*Contacts)->TryGetNumberField(TEXT("scale_ratio"), Out.ScaleRatio) || Out.ScaleRatio <= 0.) Out.ScaleRatio = 1.;
        return true;
    }

    FLinearColor FromRgb(const TArray<TSharedPtr<FJsonValue>>& V)
    {
        return FLinearColor(float(V[0]->AsNumber()), float(V[1]->AsNumber()), float(V[2]->AsNumber()), 1.f);
    }

    int32 Wrap(int32 Index, int32 Count) { return Count > 0 ? ((Index % Count) + Count) % Count : 0; }

    // The index of Id among Items (offset by Offset), left alone for an empty Id; false when there is none.
    template<typename T, typename F> bool FindId(const FString& Id, const TArray<T>& Items, F&& IdOf, int32 Offset, uint8& Out)
    {
        if (Id.IsEmpty()) return true;
        for (int32 I = 0; I < Items.Num() && I + Offset <= MAX_uint8; ++I)
            if (IdOf(Items[I]).Equals(Id, ESearchCase::IgnoreCase)) { Out = uint8(I + Offset); return true; }
        return false;
    }
}  // namespace HorseRide

// Before physics: the movement component and the mesh wait on it (Initialize), so the velocity and heading it sets are the
// ones he moves with this frame.
UHorseComponent::UHorseComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

void UHorseComponent::Initialize(AWandererCharacter* InRider)
{
    if (Rider) return;   // possession and world readiness may both initialize the same pawn
    Rider = InRider;
    // Offline the simulation runs here, before the movement component moves him. A shared game moves it into the
    // movement component's own moves and flips this order (RefreshTickOrder, as the bike's).
    RefreshTickOrder();
    USkeletalMeshComponent* RiderMesh = Rider->GetMesh();
    RiderMesh->AddTickPrerequisiteComponent(this);
    MeshLocation = RiderMesh->GetRelativeLocation();
    MeshRotation = RiderMesh->GetRelativeRotation();
    HorseRoot = NewObject<USceneComponent>(Rider, TEXT("HorseRoot"));
    HorseRoot->SetupAttachment(RiderMesh);
    HorseRoot->RegisterComponent();
    HorseRoot->SetVisibility(false, true);
    auto Part = [&](const TCHAR* Name)
    {
        USkeletalMeshComponent* P = NewObject<USkeletalMeshComponent>(Rider, Name);
        P->SetupAttachment(HorseRoot);
        P->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        P->RegisterComponent();
        P->SetVisibility(false, true);
        return P;
    };
    HorseMesh = Part(TEXT("HorseBodyMesh"));
    SaddleMesh = Part(TEXT("HorseSaddleMesh"));
    ReinsMesh = Part(TEXT("HorseReinsMesh"));
    const bool bRoster = LoadRoster();
    LoadRiderClips();
    bAssetsReady = bRoster && !Breeds.IsEmpty() && RiderClips[int32(EHorseRole::Idle)] != nullptr;
    if (!bAssetsReady)
    {
        UE_LOG(LogTemp, Warning, TEXT("HORSE not installed for %s: %d breeds, rider clips %s (rig %s)"), *Rider->GetName(), Breeds.Num(),
            RiderClips[int32(EHorseRole::Idle)] ? TEXT("found") : TEXT("missing"), *RiderRig());
        return;
    }
    // The default look: the first of each list, and the plain coat mask when the roster has one.
    HorseRide::FindId(TEXT("Solid"), CoatMasks, [](const TPair<FString, FString>& M) { return M.Key; }, 0, Appearance.Mask);
    ApplyCurrentBreedAndTack();
    ApplyCurrentMaterials();
}

bool UHorseComponent::LoadRoster()
{
    FString Text;
    TSharedPtr<FJsonObject> Roster;
    const FString Path = AtelierDataPath(TEXT("horses/roster.json"));
    if (!FFileHelper::LoadFileToString(Text, *Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Roster) || !Roster)
    {
        UE_LOG(LogTemp, Error, TEXT("HORSE roster missing or unreadable: %s"), *Path);
        return false;
    }
    auto Missing = [&Path](const FString& What) { UE_LOG(LogTemp, Error, TEXT("HORSE roster %s: %s"), *Path, *What); };

    // The coat and hair masters name which body slots take a look; tack keeps what the import gave it.
    const TSharedPtr<FJsonObject>* Masters = nullptr;
    FString CoatPath, HairPath;
    if (Roster->TryGetObjectField(TEXT("masters"), Masters) && (*Masters)->TryGetStringField(TEXT("coat"), CoatPath) &&
        (*Masters)->TryGetStringField(TEXT("hair"), HairPath))
    {
        CoatMaster = LoadObject<UMaterialInterface>(nullptr, *CoatPath);
        HairMaster = LoadObject<UMaterialInterface>(nullptr, *HairPath);
    }
    if (!CoatMaster || !HairMaster) Missing(TEXT("no coat or hair master: the coat and hair keep their imported look"));

    const TArray<TSharedPtr<FJsonValue>>* Order = nullptr;
    const TSharedPtr<FJsonObject>* BreedObjects = nullptr;
    if (!Roster->TryGetArrayField(TEXT("breed_order"), Order) || !Roster->TryGetObjectField(TEXT("breeds"), BreedObjects))
    {
        Missing(TEXT("no breed_order or breeds"));
        return false;
    }
    // Contacts are kept as offsets from the reference breed's, the breed the rider's clips are authored on.
    FString Reference;
    const TSharedPtr<FJsonObject>* ReferenceBreed = nullptr;
    HorseRide::FContacts ReferenceContacts;
    const bool bReference = Roster->TryGetStringField(TEXT("reference_breed"), Reference) &&
        (*BreedObjects)->TryGetObjectField(Reference, ReferenceBreed) && HorseRide::ReadContacts(*ReferenceBreed, ReferenceContacts);
    if (!bReference) Missing(TEXT("no reference_breed contacts: every breed rides at the reference seat"));
    for (const TSharedPtr<FJsonValue>& Value : *Order)
    {
        FBreed Breed;
        const TSharedPtr<FJsonObject>* Object = nullptr;
        double Yaw = 0.;
        if (!Value->TryGetString(Breed.Slug) || !(*BreedObjects)->TryGetObjectField(Breed.Slug, Object) ||
            !(*Object)->TryGetStringField(TEXT("mesh"), Breed.Mesh) || !(*Object)->TryGetNumberField(TEXT("mesh_yaw"), Yaw))
        {
            Missing(FString::Printf(TEXT("breed %s has no entry, mesh or mesh_yaw; left out"), *Breed.Slug));
            continue;
        }
        Breed.MeshYaw = float(Yaw);
        if (!(*Object)->TryGetStringField(TEXT("name"), Breed.Name)) Breed.Name = Breed.Slug;
        Breed.Clips.SetNum(HorseRide::RoleCount);
        const TSharedPtr<FJsonObject>* BreedClips = nullptr;
        if ((*Object)->TryGetObjectField(TEXT("clips"), BreedClips))
            for (int32 R = 0; R < HorseRide::RoleCount; ++R)
            {
                const TSharedPtr<FJsonObject>* Clip = nullptr;
                if ((*BreedClips)->TryGetObjectField(HorseRide::Roles[R].Horse, Clip)) (*Clip)->TryGetStringField(TEXT("path"), Breed.Clips[R]);
            }
        if (Breed.Clips[int32(EHorseRole::Idle)].IsEmpty()) Missing(FString::Printf(TEXT("breed %s has no Idle clip"), *Breed.Slug));
        auto ReadTack = [&](const TCHAR* Field, TMap<FString, FString>& Paths)
        {
            const TSharedPtr<FJsonObject>* Parts = nullptr;
            if ((*Object)->TryGetObjectField(Field, Parts))
                for (const auto& Pair : (*Parts)->Values) Paths.Add(FString(Pair.Key), Pair.Value->AsString());
        };
        ReadTack(TEXT("saddles"), Breed.Saddles);
        ReadTack(TEXT("reins"), Breed.Reins);
        HorseRide::FContacts Contacts;
        if (bReference && HorseRide::ReadContacts(*Object, Contacts))
        {
            Breed.ScaleRatio = float(Contacts.ScaleRatio);
            Breed.Seat = FVector(Contacts.SaddleRoot.X - ReferenceContacts.SaddleRoot.X, 0., (Contacts.SeatZ - ReferenceContacts.SeatZ) * 100.);
            Breed.StirrupL = Contacts.StirrupL - ReferenceContacts.StirrupL;
            Breed.StirrupR = Contacts.StirrupR - ReferenceContacts.StirrupR;
            Breed.GripL = Contacts.GripL - ReferenceContacts.GripL;
            Breed.GripR = Contacts.GripR - ReferenceContacts.GripR;
        }
        else if (bReference) Missing(FString::Printf(TEXT("breed %s has no contacts: its rider sits at the reference seat"), *Breed.Slug));
        Breeds.Add(MoveTemp(Breed));
    }

    const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
    if (Roster->TryGetArrayField(TEXT("tack_sets"), List))
        for (const TSharedPtr<FJsonValue>& Value : *List) TackIds.Add(Value->AsString());
    const TSharedPtr<FJsonObject>* Masks = nullptr;
    if (Roster->TryGetObjectField(TEXT("coat_masks"), Masks))
        for (const auto& Pair : (*Masks)->Values) CoatMasks.Emplace(FString(Pair.Key), Pair.Value->AsString());
    if (Roster->TryGetArrayField(TEXT("coat_variants"), List))
        for (const TSharedPtr<FJsonValue>& Value : *List)
        {
            const TSharedPtr<FJsonObject>* Item = nullptr;
            FCoatVariant Variant;
            if (Value->TryGetObject(Item) && (*Item)->TryGetStringField(TEXT("id"), Variant.Id) && (*Item)->TryGetStringField(TEXT("texture"), Variant.Texture))
                CoatVariants.Add(Variant);
        }
    if (Roster->TryGetArrayField(TEXT("hair_colors"), List))
        for (const TSharedPtr<FJsonValue>& Value : *List)
        {
            const TSharedPtr<FJsonObject>* Item = nullptr;
            FString Id, Primary, Secondary;
            if (Value->TryGetObject(Item) && (*Item)->TryGetStringField(TEXT("id"), Id) && (*Item)->TryGetStringField(TEXT("primary"), Primary) &&
                (*Item)->TryGetStringField(TEXT("secondary"), Secondary))
                HairColors.Add({Id, FLinearColor(FColor::FromHex(Primary)), FLinearColor(FColor::FromHex(Secondary))});
        }
    if (Roster->TryGetArrayField(TEXT("hair_patterns"), List))
        for (const TSharedPtr<FJsonValue>& Value : *List)
        {
            const TSharedPtr<FJsonObject>* Item = nullptr;
            FHairPattern Pattern;
            double Mix = 0.;
            if (Value->TryGetObject(Item) && (*Item)->TryGetStringField(TEXT("id"), Pattern.Id) && (*Item)->TryGetNumberField(TEXT("mix"), Mix))
            {
                Pattern.Mix = float(Mix);
                HairPatterns.Add(Pattern);
            }
        }
    if (Roster->TryGetArrayField(TEXT("tints"), List))
        for (const TSharedPtr<FJsonValue>& Value : *List)
        {
            const TSharedPtr<FJsonObject>* Item = nullptr;
            const TArray<TSharedPtr<FJsonValue>>* Rgb = nullptr;
            FString Id;
            if (Value->TryGetObject(Item) && (*Item)->TryGetStringField(TEXT("id"), Id) && (*Item)->TryGetArrayField(TEXT("rgb"), Rgb) && Rgb->Num() == 3)
                Tints.Add({Id, HorseRide::FromRgb(*Rgb)});
        }
    if (TackIds.IsEmpty()) Missing(TEXT("no tack_sets: the horse goes bare"));
    if (CoatMasks.IsEmpty() || HairColors.IsEmpty() || HairPatterns.IsEmpty() || Tints.IsEmpty())
        Missing(TEXT("no coat_masks, hair_colors, hair_patterns or tints: those keep the imported look"));
    return true;
}

FString UHorseComponent::RiderRig() const { return RigOf(Rider); }

FString UHorseComponent::RigOf(const AWandererCharacter* Character)
{
    // As UBikeComponent::RiderRig: a rider without clips of his own borrows the default character's, and Toggle turns him
    // away unless they fit his skeleton.
    const FString Own = Character ? Character->GetBikeRig() : FString();
    if (!Own.IsEmpty()) return Own;
    const UClass* Player = FPlayableCharacter::Default().Class();
    return Player ? CastChecked<AWandererCharacter>(Player->GetDefaultObject())->GetBikeRig() : FString();
}

bool UHorseComponent::HasRiderClips(const AWandererCharacter* Character)
{
    const FString Rig = RigOf(Character);
    const TCHAR* Seated = HorseRide::Roles[int32(EHorseRole::Idle)].Rider;
    return !Rig.IsEmpty() && LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("/Game/%sHorse/A_%s.A_%s"), *Rig, Seated, Seated),
        nullptr, LOAD_NoWarn | LOAD_Quiet) != nullptr;
}

bool UHorseComponent::CanRide() const
{
    if (!bAssetsReady || !Rider) return false;
    const UAnimSequence* Seated = RiderClips[int32(EHorseRole::Idle)];
    const USkeletalMesh* Body = Rider->GetMesh()->GetSkeletalMeshAsset();
    return Seated && Body && Seated->GetSkeleton() == Body->GetSkeleton();
}

bool UHorseComponent::IsHorseVisible() const { return HorseRoot && HorseRoot->IsVisible(); }

void UHorseComponent::LoadRiderClips()
{
    const FString Rig = RiderRig();
    RiderClips.Init(nullptr, HorseRide::RoleCount);
    if (Rig.IsEmpty()) return;
    for (int32 R = 0; R < HorseRide::RoleCount; ++R)
        RiderClips[R] = LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("/Game/%sHorse/A_%s.A_%s"), *Rig, HorseRide::Roles[R].Rider, HorseRide::Roles[R].Rider),
            nullptr, LOAD_NoWarn | LOAD_Quiet);
}

void UHorseComponent::ApplyCurrentBreedAndTack()
{
    if (!Breeds.IsValidIndex(Appearance.Breed) || !HorseMesh) return;
    const FBreed& Breed = Breeds[Appearance.Breed];
    HorseRoot->SetRelativeRotation(FRotator(0.f, Breed.MeshYaw - MeshRotation.Yaw, 0.f));
    HorseMesh->SetSkeletalMesh(LoadObject<USkeletalMesh>(nullptr, *Breed.Mesh));
    HorseMesh->SetAnimationMode(EAnimationMode::AnimationSingleNode);
    HorseClips.Init(nullptr, HorseRide::RoleCount);
    for (int32 R = 0; R < HorseRide::RoleCount; ++R)
        if (!Breed.Clips[R].IsEmpty()) HorseClips[R] = LoadObject<UAnimSequence>(nullptr, *Breed.Clips[R]);
    // The import gives each slot an instance of a horse master with its own texture (and cutoff). The coat and the mane and
    // tail get a dynamic instance of it, so a look overrides only what it changes; eyes, hooves and tack stay as imported.
    HorseMesh->EmptyOverrideMaterials();
    CoatMaterials.Reset();
    HairMaterials.Reset();
    const UMaterial* CoatBase = CoatMaster ? CoatMaster->GetBaseMaterial() : nullptr;
    const UMaterial* HairBase = HairMaster ? HairMaster->GetBaseMaterial() : nullptr;
    for (int32 I = 0; I < HorseMesh->GetNumMaterials(); ++I)
    {
        UMaterialInterface* Imported = HorseMesh->GetMaterial(I);
        const UMaterial* Base = Imported ? Imported->GetBaseMaterial() : nullptr;
        if (!Base || (Base != CoatBase && Base != HairBase)) continue;
        UMaterialInstanceDynamic* Dynamic = UMaterialInstanceDynamic::Create(Imported, this);
        HorseMesh->SetMaterial(I, Dynamic);
        (Base == CoatBase ? CoatMaterials : HairMaterials).Add(Dynamic);
    }
    const FString TackId = GetTackId();
    auto Tack = [&](USkeletalMeshComponent* Part, const TMap<FString, FString>& Paths)
    {
        const FString* Path = Paths.Find(TackId);
        Part->SetSkeletalMesh(Path ? LoadObject<USkeletalMesh>(nullptr, **Path) : nullptr);
        Part->SetLeaderPoseComponent(HorseMesh, true);
    };
    Tack(SaddleMesh, Breed.Saddles);
    Tack(ReinsMesh, Breed.Reins);
    bHorseClipStale = true;
}

void UHorseComponent::ApplyCurrentMaterials()
{
    const FCoatVariant* Variant = CoatVariants.IsValidIndex(Appearance.Coat - 1) ? &CoatVariants[Appearance.Coat - 1] : nullptr;
    UTexture2D* VariantTexture = Variant ? LoadObject<UTexture2D>(nullptr, *Variant->Texture) : nullptr;
    UTexture2D* Mask = CoatMasks.IsValidIndex(Appearance.Mask) ? LoadObject<UTexture2D>(nullptr, *CoatMasks[Appearance.Mask].Value) : nullptr;
    for (UMaterialInstanceDynamic* Coat : CoatMaterials)
    {
        // Back to the imported instance (the breed's own coat) before this look's changes.
        Coat->ClearParameterValues();
        if (VariantTexture) Coat->SetTextureParameterValue(TEXT("BaseColorTexture"), VariantTexture);
        if (Tints.IsValidIndex(Appearance.Tint)) Coat->SetVectorParameterValue(TEXT("CoatTint"), Tints[Appearance.Tint].Color);
        if (Mask)
        {
            Coat->SetTextureParameterValue(TEXT("MaskTexture"), Mask);
            Coat->SetScalarParameterValue(TEXT("MaskStrength"), HorseRide::MaskStrength);
        }
    }
    // Hair colour 0 keeps the breed's own mane and tail (the import's hair_colour); k is hair_colors[k-1].
    const FHairColor* HairColor = HairColors.IsValidIndex(Appearance.HairColor - 1) ? &HairColors[Appearance.HairColor - 1] : nullptr;
    for (UMaterialInstanceDynamic* Hair : HairMaterials)
    {
        Hair->ClearParameterValues();
        if (HairColor)
        {
            Hair->SetVectorParameterValue(TEXT("PrimaryColor"), HairColor->Primary);
            Hair->SetVectorParameterValue(TEXT("SecondaryColor"), HairColor->Secondary);
        }
        if (HairPatterns.IsValidIndex(Appearance.HairPattern)) Hair->SetScalarParameterValue(TEXT("PatternMix"), HairPatterns[Appearance.HairPattern].Mix);
    }
}

bool UHorseComponent::IsValidAppearance(const FJapanHorseAppearance& A) const
{
    return A.IsWithin(Breeds.Num(), TackIds.Num(), 1 + CoatVariants.Num(), CoatMasks.Num(), 1 + HairColors.Num(), HairPatterns.Num(), Tints.Num());
}

bool UHorseComponent::ApplyAppearance(const FJapanHorseAppearance& NewAppearance)
{
    if (!IsValidAppearance(NewAppearance)) return false;
    const bool bBody = NewAppearance.Breed != Appearance.Breed || NewAppearance.Tack != Appearance.Tack;
    const bool bTextures = NewAppearance.Coat != Appearance.Coat || NewAppearance.Mask != Appearance.Mask;
    Appearance = NewAppearance;
    if (bBody) ApplyCurrentBreedAndTack();
    ApplyCurrentMaterials();
    // Local look changes can replace whole meshes and texture sets. Request collection at the engine's next safe
    // opportunity, with incremental purging, so trying breeds does not wait for the periodic pass. A remote look must
    // not make every observer collect; colour-only changes allocate no new asset set. Never collect inline here.
    if ((bBody || bTextures) && Rider && Rider->IsLocallyControlled() && GEngine) GEngine->ForceGarbageCollection(false);
    return true;
}

FJapanHorseAppearance UHorseComponent::RandomAppearance() const
{
    // Appearance only: never part of the ride's simulation.
    FJapanHorseAppearance A = Appearance;
    A.Breed = uint8(FMath::RandHelper(Breeds.Num()));
    A.Tack = uint8(FMath::RandHelper(TackIds.Num()));
    A.Coat = uint8(FMath::RandHelper(1 + CoatVariants.Num()));
    A.Mask = uint8(FMath::RandHelper(CoatMasks.Num()));
    A.HairColor = uint8(FMath::RandHelper(1 + HairColors.Num()));
    A.HairPattern = uint8(FMath::RandHelper(HairPatterns.Num()));
    A.Tint = uint8(FMath::RandHelper(Tints.Num()));
    return A;
}

FJapanHorseAppearance UHorseComponent::NextBreed(int32 Delta) const { FJapanHorseAppearance A = Appearance; A.Breed = uint8(HorseRide::Wrap(A.Breed + Delta, Breeds.Num())); return A; }
FJapanHorseAppearance UHorseComponent::NextTack(int32 Delta) const { FJapanHorseAppearance A = Appearance; A.Tack = uint8(HorseRide::Wrap(A.Tack + Delta, TackIds.Num())); return A; }
FJapanHorseAppearance UHorseComponent::NextCoat(int32 Delta) const { FJapanHorseAppearance A = Appearance; A.Coat = uint8(HorseRide::Wrap(A.Coat + Delta, 1 + CoatVariants.Num())); return A; }
void UHorseComponent::RandomizeHorse() { ApplyAppearance(RandomAppearance()); }
void UHorseComponent::CycleBreed(int32 Delta) { ApplyAppearance(NextBreed(Delta)); }
void UHorseComponent::CycleTack(int32 Delta) { ApplyAppearance(NextTack(Delta)); }
void UHorseComponent::CycleCoat(int32 Delta) { ApplyAppearance(NextCoat(Delta)); }

bool UHorseComponent::ResolveAppearance(const FString& Breed, const FString& Tack, const FString& Coat, const FString& Mask,
    const FString& HairColor, const FString& HairPattern, const FString& Tint, FJapanHorseAppearance& Out) const
{
    FJapanHorseAppearance A = Appearance;
    bool bCoat = true, bHairColor = true;
    if (Coat.Equals(TEXT("native"), ESearchCase::IgnoreCase)) A.Coat = 0;
    else bCoat = HorseRide::FindId(Coat, CoatVariants, [](const FCoatVariant& V) { return V.Id; }, 1, A.Coat);
    if (HairColor.Equals(TEXT("native"), ESearchCase::IgnoreCase)) A.HairColor = 0;
    else bHairColor = HorseRide::FindId(HairColor, HairColors, [](const FHairColor& C) { return C.Id; }, 1, A.HairColor);
    const bool bFound = bCoat && bHairColor &&
        HorseRide::FindId(Breed, Breeds, [](const FBreed& B) { return B.Slug; }, 0, A.Breed) &&
        HorseRide::FindId(Tack, TackIds, [](const FString& Id) { return Id; }, 0, A.Tack) &&
        HorseRide::FindId(Mask, CoatMasks, [](const TPair<FString, FString>& M) { return M.Key; }, 0, A.Mask) &&
        HorseRide::FindId(HairPattern, HairPatterns, [](const FHairPattern& P) { return P.Id; }, 0, A.HairPattern) &&
        HorseRide::FindId(Tint, Tints, [](const FTint& T) { return T.Id; }, 0, A.Tint);
    if (!bFound || !IsValidAppearance(A)) return false;
    Out = A;
    return true;
}

bool UHorseComponent::ConfigureHorse(const FString& Breed, const FString& Tack, const FString& Coat, const FString& Mask,
    const FString& HairColor, const FString& HairPattern, const FString& Tint)
{
    FJapanHorseAppearance A;
    return ResolveAppearance(Breed, Tack, Coat, Mask, HairColor, HairPattern, Tint, A) && ApplyAppearance(A);
}

bool UHorseComponent::Toggle()
{
    // A shared game toggles on the host only (AWandererCharacter::ServerRequestHorse), which then hands the activity over.
    if (JapanNetwork::IsOnline(GetWorld()) && (!Rider || !Rider->HasAuthority())) return false;
    if (!bAssetsReady || !Rider) { Hint = TEXT("The horses are not installed"); return false; }
    if (!CanRide()) { Hint = TEXT("This character has no horse clips"); return false; }
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    if (Phase == EPhase::Riding)
    {
        if (Speed > HorseRide::DismountSpeed) { Hint = TEXT("Slow down to get off"); return false; }
        if (!M->IsMovingOnGround()) { Hint = TEXT("Land to get off"); return false; }
        Phase = EPhase::Dismounting;
        PhaseTime = Speed = 0.f;
        bSprint = false;
        Hint.Reset();
        Play(EHorseRole::Dismount);
        return true;
    }
    if (Phase != EPhase::Stowed) return false;
    if (!M->IsMovingOnGround() || Rider->bIsCrouched) { Hint = TEXT("Stand on the ground, not crouching, to get the horse"); return false; }
    // The horse appears under him. Walking physics carries them both; nothing brakes the speed the horse sets.
    M->StopMovementImmediately();
    HoldFriction();
    Phase = EPhase::Mounting;
    PhaseTime = Speed = Steering = GaitPhase = IdleTimer = 0.f;
    ForcedIdle = EHorseRole::Idle;
    bSprint = bReinIn = bTerminal = false;
    ResetPresentation();
    Hint.Reset();
    Play(EHorseRole::Mount);
    HorseRoot->SetVisibility(true, true);
    JapanVehicleVisuals::SetRiderPose(Rider, MeshLocation, MeshRotation.Quaternion(), false);
    UE_LOG(LogTemp, Display, TEXT("HORSE summon: %s"), *GetStatus());
    return true;
}

void UHorseComponent::ResetPresentation()
{
    GroundPitch = BankAngle = PresentedSpeed = SmoothedAccelForward = 0.f;
    TorsoPitchDeg = TorsoPitchVel = TorsoRollDeg = TorsoRollVel = TorsoYawDeg = TorsoYawVel = PelvisHeaveCm = PelvisHeaveVel = 0.f;
    bHorseClipStale = true;
}

void UHorseComponent::HoldFriction()
{
    // Saved once a ride, when the horse is installed: a later handoff never saves the held-off zeros over the rider's.
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    if (!bFrictionSaved)
    {
        SavedFriction = M->GroundFriction;
        SavedBraking = M->BrakingDecelerationWalking;
        bFrictionSaved = true;
    }
    M->GroundFriction = 0.f;
    M->BrakingDecelerationWalking = 0.f;
}

void UHorseComponent::ReleaseFriction()
{
    if (!bFrictionSaved || !Rider) return;
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    M->GroundFriction = SavedFriction;
    M->BrakingDecelerationWalking = SavedBraking;
    bFrictionSaved = false;
}

bool UHorseComponent::IsInDeepWater() const
{
    if (!Rider) return false;
    const auto* Movement = Rider->GetCharacterMovement();
    if (Movement->IsSwimming()) return true;
    const auto* Moves = Rider->GetMoves();
    float Surface = 0.f;
    const FVector Here = Rider->GetActorLocation();
    if (!Moves || !Moves->WaterAt(Here, Surface)) return false;
    const float HalfHeight = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    // Match on-foot entry in AdvanceGround/AdvanceAir. The horse leaves the capsule unchanged, and the sea and lake
    // use authored water queries, not Unreal physics volumes or MOVE_Swimming.
    const float Depth = Movement->IsFalling() ? 10.f : HalfHeight * 1.1f;
    return float(Here.Z) - HalfHeight < Surface - Depth;
}

void UHorseComponent::StowImmediately()
{
    ReleaseFriction();
    if (Phase != EPhase::Stowed)
    {
        UCharacterMovementComponent* M = Rider->GetCharacterMovement();
        // The ride ended in water (AdvanceSimulation): the player on it is told why (offline here, online when the host's
        // stow reaches him; never the host for a guest's horse).
        if (IsInDeepWater() && Rider->IsLocallyControlled()) ULiveLibrary::Say(TEXT("The horse will not swim: you are on foot"));
        M->StopMovementImmediately();
        JapanVehicleVisuals::SetRiderPose(Rider, MeshLocation, MeshRotation.Quaternion(), false);
        Phase = EPhase::Stowed;
        Role = ForcedIdle = EHorseRole::Idle;
        ++Serial;
    }
    if (HorseRoot) HorseRoot->SetVisibility(false, true);
    PhaseTime = Speed = Steering = GaitPhase = IdleTimer = GroundPitch = BankAngle = 0.f;
    bSprint = bReinIn = bTerminal = false;
    Hint.Reset();
}

bool UHorseComponent::ToggleSprint()
{
    // A shared game's owner sends the press with his next move (the bike's sprint edge); the move toggles it below.
    bool Accepted = false;
    if (QueueNetworkAction(TEXT("bike_sprint"), Accepted)) return Accepted;
    if (Phase != EPhase::Riding || Input.bMenu) return false;
    bSprint = !bSprint;
    return true;
}

void UHorseComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    RefreshTickOrder();
    if (Phase == EPhase::Stowed || !Rider) return;
    // Online the movement component's moves (and any correction replay) have already simulated this frame.
    if (JapanNetwork::IsOnline(GetWorld())) { PresentNetwork(DeltaTime); return; }
    if (!AdvanceSimulation(DeltaTime, Input)) { StowImmediately(); return; }
    Present(DeltaTime);
}

bool UHorseComponent::AdvanceSimulation(float Dt, const FHorseInput& In)
{
    if (!Rider || Phase == EPhase::Stowed) return false;
    if (!FMath::IsFinite(Dt) || Dt <= 0.f) return true;
    Input = In;
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    PhaseTime = FMath::Min(PhaseTime + Dt, HorseRide::MaxPhaseTime);
    // The authored sea/lake query and capsule depth match on-foot swimming admission on the owner and host.
    // Offline the ride ends now; online the host's actor tick stows it on NeedsNetworkStow, outside movement replay.
    if (!bTerminal && IsInDeepWater())
    {
        if (!JapanNetwork::IsOnline(GetWorld())) return false;
        if (Phase != EPhase::Dismounting)
        {
            Phase = EPhase::Dismounting;
            PhaseTime = 0.f;
            Play(EHorseRole::Dismount);
        }
        Speed = Steering = 0.f;
        bSprint = bReinIn = false;
        bTerminal = true;
        return true;
    }
    if (bTerminal || Phase != EPhase::Riding)
    {
        // Getting on or off, the horse stands; gravity still has him.
        Speed = Steering = 0.f;
        bReinIn = false;
        M->Velocity = FVector(0.f, 0.f, M->Velocity.Z);
        if (bTerminal) return true;
        AdvanceGait(Dt);
        if (Phase == EPhase::Mounting && PhaseTime >= TransitionLength(EHorseRole::Mount))
        {
            Phase = EPhase::Riding;
            PhaseTime = 0.f;
            IdleCooldown = 5.5f;
            Play(EHorseRole::Idle);
        }
        else if (Phase == EPhase::Dismounting && PhaseTime >= TransitionLength(EHorseRole::Dismount))
        {
            if (!JapanNetwork::IsOnline(GetWorld())) return false;
            bTerminal = true;
        }
        return true;
    }

    const float StickX = In.bMenu ? 0.f : FMath::Clamp(float(In.Stick.X), -1.f, 1.f);
    const float StickY = In.bMenu ? 0.f : FMath::Clamp(float(In.Stick.Y), -1.f, 1.f);
    const bool bGround = M->IsMovingOnGround();
    const float SpeedBefore = Speed;
    // Walls: the movement component slid or stopped him last step (his velocity is what he really moved).
    const float Moved = FVector::DotProduct(M->Velocity, Rider->GetActorForwardVector());
    if (bGround && Speed > 60.f && Moved < Speed * .4f) Speed = FMath::Min(Speed, FMath::Max(0.f, Moved));
    // Ride on to the stick's share of the gallop (or the sprint), coast with the reins slack, rein in. Only the ground
    // changes his speed; in the air he carries it.
    float Ride = StickY;
    if (Ride > 0.f) Ride *= In.bWalk ? HorseRide::WalkShare : In.bJog ? HorseRide::JogShare : 1.f;
    bReinIn = In.bMenu || Ride < -.1f;
    if (bGround)
    {
        if (bReinIn) Speed = FMath::Max(0.f, Speed - HorseRide::ReinIn * Dt);
        else if (Ride > .05f) Speed = FMath::FInterpConstantTo(Speed, Ride * (bSprint ? HorseRide::SprintMaxSpeed : HorseRide::GallopMaxSpeed), Dt, bSprint ? HorseRide::SprintPush : HorseRide::Push);
        else Speed = FMath::FInterpConstantTo(Speed, 0.f, Dt, HorseRide::Coast);
    }
    // The horse's chest and muzzle reach past his capsule: what they meet stops it there. It has no fall to throw him with
    // (the bike's crash), so at any speed it pulls up.
    if (Speed > 0.f)
    {
        const bool Online = JapanNetwork::IsOnline(GetWorld());
        FCollisionQueryParams Q = Online ? JapanGameplayCollision::Query(GetWorld(), SCENE_QUERY_STAT(HorseAhead), false)
                                         : FCollisionQueryParams(SCENE_QUERY_STAT(HorseAhead), false, Rider);
        Q.AddIgnoredActor(Rider);
        const FVector Feet = Rider->GetActorLocation() - FVector(0.f, 0.f, Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
        const FVector Ahead = Rider->GetActorForwardVector();
        for (const HorseRide::FProbe& AheadProbe : HorseRide::Probes)
        {
            const FVector From = Feet + FVector(0.f, 0.f, AheadProbe.Height);
            FHitResult Hit;
            if (GetWorld()->LineTraceSingleByChannel(Hit, From, From + Ahead * (AheadProbe.Reach + Speed * Dt),
                    Online ? JapanGameplayCollision::Channel : ECC_Visibility, Q) && Hit.ImpactNormal.Z < .6f)
            {
                Speed = 0.f;
                break;
            }
        }
    }
    // Coming to a halt (reined in, coasted down or stopped by a wall) ends the sprint, as the bike's coast does.
    if (SpeedBefore >= HorseRide::IdleSpeed && Speed < HorseRide::IdleSpeed) bSprint = false;
    // Nimble at a walk, a wide arc at the gallop; loose in the air.
    Steering = StickX;
    const float TurnRate = FMath::Lerp(135.f, 68.f, FMath::Clamp(Speed / HorseRide::SprintMaxSpeed, 0.f, 1.f)) * Steering * (bGround ? 1.f : .35f);
    Rider->AddActorWorldRotation(FRotator(0.f, TurnRate * Dt, 0.f));
    FVector V = Rider->GetActorForwardVector() * Speed;
    V.Z = M->Velocity.Z;
    M->Velocity = V;
    // A refused dismount's reason stays until it no longer applies: stopped, on the ground.
    if (!Hint.IsEmpty() && Speed <= HorseRide::DismountSpeed && bGround) Hint.Reset();

    // Standing, now and then an idle variant plays out: chosen from the clip serial, not a random stream, so every machine
    // replaying this step picks the same one.
    if (Speed < HorseRide::IdleSpeed)
    {
        if (ForcedIdle != EHorseRole::Idle)
        {
            IdleTimer -= Dt;
            if (IdleTimer <= 0.f) { ForcedIdle = EHorseRole::Idle; IdleTimer = 0.f; }
        }
        else if ((IdleCooldown -= Dt) <= 0.f)
        {
            ForcedIdle = HorseRide::IdleVariants[Serial % UE_ARRAY_COUNT(HorseRide::IdleVariants)];
            IdleTimer = ClipLength(ForcedIdle);
            IdleCooldown = 6.5f + .8f * float(Serial % 7);
        }
    }
    else
    {
        ForcedIdle = EHorseRole::Idle;
        IdleTimer = 0.f;
    }
    const EHorseRole Want = SelectRole();
    if (Want != Role) Play(Want);
    AdvanceGait(Dt);
    return true;
}

void UHorseComponent::Play(EHorseRole NewRole)
{
    // From one gait to the next the cycle carries on (the legs stay in step); a one-shot starts at its beginning.
    if (!HorseRide::RoleOf(Role).bLoop || !HorseRide::RoleOf(NewRole).bLoop) GaitPhase = 0.f;
    Role = NewRole;
    ++Serial;
}

EHorseRole UHorseComponent::SelectRole() const
{
    if (Speed < HorseRide::IdleSpeed) return ForcedIdle;
    if (Speed <= HorseRide::WalkMaxSpeed) return EHorseRole::Walk;
    if (Speed <= HorseRide::TrotMaxSpeed) return EHorseRole::Trot;
    if (Speed <= HorseRide::CanterMaxSpeed) return EHorseRole::Canter;
    return Speed <= HorseRide::GallopMaxSpeed || !bSprint ? EHorseRole::Gallop : EHorseRole::Sprint;
}

bool UHorseComponent::Loops(EHorseRole Of) { return int32(Of) < HorseRide::RoleCount && HorseRide::RoleOf(Of).bLoop; }

float UHorseComponent::ClipLength(EHorseRole Of) const
{
    // A role without a rider clip plays the Idle one (GetSequence).
    const int32 Index = RiderClips.IsValidIndex(int32(Of)) && RiderClips[int32(Of)] ? int32(Of) : int32(EHorseRole::Idle);
    const UAnimSequence* Clip = RiderClips.IsValidIndex(Index) ? RiderClips[Index].Get() : nullptr;
    return Clip ? FMath::Max(Clip->GetPlayLength(), .033f) : 1.f;
}

float UHorseComponent::TransitionLength(EHorseRole Of) const
{
    // Getting on or off lasts the rider's clip (HorseMount 1.60 s, HorseDismount 1.40 s as authored): the same asset on
    // every machine, since session admission hashes Content/.
    return FMath::Min(ClipLength(Of), HorseRide::MaxPhaseTime);
}

void UHorseComponent::AdvanceGait(float Dt)
{
    const float Length = ClipLength(Role);
    if (Phase != EPhase::Riding) { GaitPhase = FMath::Clamp(PhaseTime / Length, 0.f, 1.f); return; }
    // Each gait's clip plays faster as the horse runs up through its range.
    auto Rate = [this](float Low, float High, float Slow, float Fast) { return FMath::GetMappedRangeValueClamped(FVector2f(Low, High), FVector2f(Slow, Fast), Speed); };
    float PlayRate = 1.f;
    switch (Role)
    {
        case EHorseRole::Walk: PlayRate = Rate(10.f, HorseRide::WalkMaxSpeed, .82f, 1.22f); break;
        case EHorseRole::Trot: PlayRate = Rate(HorseRide::WalkMaxSpeed, HorseRide::TrotMaxSpeed, .88f, 1.20f); break;
        case EHorseRole::Canter: PlayRate = Rate(HorseRide::TrotMaxSpeed, HorseRide::CanterMaxSpeed, .90f, 1.18f); break;
        case EHorseRole::Gallop: PlayRate = Rate(HorseRide::CanterMaxSpeed, HorseRide::GallopMaxSpeed, .92f, 1.16f); break;
        case EHorseRole::Sprint: PlayRate = Rate(HorseRide::GallopMaxSpeed, HorseRide::SprintMaxSpeed, .95f, 1.22f); break;
        default: break;
    }
    const float Next = GaitPhase + Dt * PlayRate / Length;
    GaitPhase = HorseRide::RoleOf(Role).bLoop ? FMath::Frac(Next) : FMath::Min(Next, 1.f);
}

void UHorseComponent::Present(float Dt)
{
    if (Dt <= 0.f) return;
    Dt = FMath::Min(Dt, .05f);   // the springs below stay stable through a hitch
    UAnimSequence* const Clip = GetHorseSequence();
    if (PresentedSerial != Serial || bHorseClipStale)
    {
        // A new clip on the horse; its first frame is no footfall.
        if (Clip)
        {
            HorseMesh->SetAnimation(Clip);
            HorseMesh->SetPlayRate(0.f);
        }
        PresentedSerial = Serial;
        bHorseClipStale = false;
    }
    else EmitHoofsteps(PresentedGaitPhase, GaitPhase);
    PresentedGaitPhase = GaitPhase;
    if (Clip)
    {
        const float Length = FMath::Max(Clip->GetPlayLength(), .033f);
        HorseMesh->SetPosition(FMath::Min(GaitPhase * Length, Length - .001f), false);
    }
    const float RawAccel = (Speed - PresentedSpeed) / Dt;
    PresentedSpeed = Speed;
    SmoothedAccelForward = FMath::FInterpTo(SmoothedAccelForward, RawAccel, Dt, 10.f);
    // He and the horse lean into a turn together.
    BankAngle = FMath::FInterpTo(BankAngle, Phase == EPhase::Riding ? FMath::Clamp(Steering * (Speed / HorseRide::GallopMaxSpeed) * 14.f, -16.f, 16.f) : 0.f, Dt, 7.f);
    FollowGround(Dt);
    StepTorsoSpring(Dt);
    // The horse hangs off his mesh, so both tilt together about the ground under him, with no drift between saddle and seat.
    const FQuat Tilt = FRotator(GroundPitch, 0.f, BankAngle).Quaternion();
    JapanVehicleVisuals::SetRiderPose(Rider, MeshLocation, (Tilt * MeshRotation.Quaternion()).GetNormalized());
}

void UHorseComponent::FollowGround(float Dt)
{
    // The walking capsule stands on one point under him; the horse pitches to the ground between its front and back hooves.
    float Want = 0.f;
    if (Rider->GetCharacterMovement()->IsMovingOnGround())
    {
        const bool Online = JapanNetwork::IsOnline(GetWorld());
        FCollisionQueryParams Q = Online ? JapanGameplayCollision::Query(GetWorld(), SCENE_QUERY_STAT(HorseGround), false)
                                         : FCollisionQueryParams(SCENE_QUERY_STAT(HorseGround), false, Rider);
        Q.AddIgnoredActor(Rider);
        const float Span = HorseRide::HoofSpan * (Breeds.IsValidIndex(Appearance.Breed) ? Breeds[Appearance.Breed].ScaleRatio : 1.f);
        const FVector At = Rider->GetActorLocation(), Ahead = Rider->GetActorForwardVector() * Span;
        FHitResult Front, Back;
        const ECollisionChannel Channel = Online ? JapanGameplayCollision::Channel : ECC_Visibility;
        if (GetWorld()->LineTraceSingleByChannel(Front, At + Ahead + FVector(0, 0, 120), At + Ahead - FVector(0, 0, 240), Channel, Q) &&
            GetWorld()->LineTraceSingleByChannel(Back, At - Ahead + FVector(0, 0, 120), At - Ahead - FVector(0, 0, 240), Channel, Q))
            Want = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(float(Front.ImpactPoint.Z - Back.ImpactPoint.Z), 2.f * Span)), -25.f, 25.f);
    }
    GroundPitch = FMath::FInterpTo(GroundPitch, Want, Dt, 10.f);
}

void UHorseComponent::EmitHoofsteps(float From, float To)
{
    if (Phase != EPhase::Riding || Speed < 15.f || int32(Role) < int32(EHorseRole::Walk) || int32(Role) > int32(EHorseRole::Sprint)) return;
    UJapanFootstepComponent* Steps = Rider->GetFootsteps();
    if (!Steps) return;
    auto Crossed = [From, To](float At) { return To >= From ? From < At && To >= At : From < At || To >= At; };
    // Footfalls in the cycle: the walk's four beats, the trot's two diagonals, the canter and gallop's three.
    bool bStrike = false;
    if (Role == EHorseRole::Walk) bStrike = Crossed(.10f) || Crossed(.35f) || Crossed(.60f) || Crossed(.85f);
    else if (Role == EHorseRole::Trot) bStrike = Crossed(.15f) || Crossed(.65f);
    else bStrike = Crossed(.12f) || Crossed(.38f) || Crossed(.68f);
    if (!bStrike) return;
    FCollisionQueryParams Q(SCENE_QUERY_STAT(HorseHoof), true, Rider);
    Q.bReturnFaceIndex = true;   // the surface's material
    const FVector At = Rider->GetActorLocation();
    FHitResult Hit;
    if (!GetWorld()->LineTraceSingleByChannel(Hit, At, At - FVector(0.f, 0.f, Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 40.f), ECC_Visibility, Q))
        return;
    Steps->Hoof(Hit, FMath::GetMappedRangeValueClamped(FVector2f(80.f, 950.f), FVector2f(.45f, 1.15f), Speed));
}

void UHorseComponent::StepTorsoSpring(float Dt)
{
    const float TwoPiPhase = GaitPhase * 2.f * PI;
    const float SpeedAlpha = FMath::Clamp(Speed / HorseRide::GallopMaxSpeed, 0.f, 1.25f);
    // The gait rocks him: pitch, roll and the pelvis's lift.
    float GaitPitch = 0.f, GaitRoll = 0.f, GaitHeave = 0.f;
    if (Phase == EPhase::Riding && Speed > HorseRide::IdleSpeed)
    {
        if (Role == EHorseRole::Walk)
        {
            // Four-beat walk: a gentle figure-of-eight sway with a nod twice a cycle.
            GaitPitch = 1.6f * FMath::Sin(2.f * TwoPiPhase - .5f);
            GaitRoll = 2.0f * FMath::Sin(TwoPiPhase - .35f);
            GaitHeave = .65f * FMath::Sin(2.f * TwoPiPhase);
        }
        else if (Role == EHorseRole::Trot)
        {
            // Two-beat trot: a crisp lift each diagonal, the upper body absorbing it.
            GaitPitch = 2.4f * FMath::Sin(2.f * TwoPiPhase - .4f);
            GaitRoll = 1.5f * FMath::Cos(TwoPiPhase);
            GaitHeave = 1.4f * FMath::Sin(2.f * TwoPiPhase - .3f);
        }
        else
        {
            // Canter and gallop: one long rocking wave a stride, cushioned in the suspension.
            GaitPitch = (3.8f + 1.5f * SpeedAlpha) * FMath::Sin(TwoPiPhase - .55f);
            GaitRoll = 1.8f * FMath::Cos(TwoPiPhase - .3f);
            GaitHeave = (1.8f + .6f * SpeedAlpha) * FMath::Sin(TwoPiPhase - .4f);
        }
    }
    // Speeding up leaves him behind (pitched back), reining in throws him forward; a slope leans him with it.
    const float Pitch = FMath::Clamp(-SmoothedAccelForward * .0085f, -7.5f, 7.5f) + GroundPitch * .35f + GaitPitch;
    const float Roll = FMath::Clamp(Steering * SpeedAlpha * 7.5f, -9.f, 9.f) + GaitRoll;
    const float Yaw = FMath::Clamp(Steering * 8.5f, -10.f, 10.f);   // a look into the turn
    auto Spring = [Dt](float& Value, float& Velocity, float Target, float Omega, float Zeta)
    {
        Velocity += (Omega * Omega * (Target - Value) - 2.f * Zeta * Omega * Velocity) * Dt;
        Value += Velocity * Dt;
    };
    Spring(TorsoPitchDeg, TorsoPitchVel, Pitch, 11.5f, .62f);
    Spring(TorsoRollDeg, TorsoRollVel, Roll, 10.5f, .65f);
    Spring(TorsoYawDeg, TorsoYawVel, Yaw, 9.0f, .78f);
    Spring(PelvisHeaveCm, PelvisHeaveVel, GaitHeave, 14.0f, .68f);
}

void UHorseComponent::PopulateRiderNode(FHorseRiderNode& OutNode) const
{
    if (Phase == EPhase::Stowed || !Breeds.IsValidIndex(Appearance.Breed))
    {
        OutNode.TorsoWeight = OutNode.IKWeight = 0.f;
        return;
    }
    // In the saddle from late in mounting to early in dismounting.
    const float Saddle = Phase == EPhase::Mounting ? FMath::SmoothStep(.58f, .92f, PhaseTime / TransitionLength(EHorseRole::Mount))
        : Phase == EPhase::Dismounting ? 1.f - FMath::SmoothStep(.08f, .42f, PhaseTime / TransitionLength(EHorseRole::Dismount)) : 1.f;
    OutNode.TorsoWeight = OutNode.IKWeight = Saddle;
    // The rider mesh's component space: pitch about +Y (right), roll about +X (forward), yaw about +Z.
    auto Turn = [](float PitchDeg, float RollDeg, float YawDeg)
    {
        const FQuat P(FVector(0.f, 1.f, 0.f), FMath::DegreesToRadians(PitchDeg));
        const FQuat R(FVector(1.f, 0.f, 0.f), FMath::DegreesToRadians(RollDeg));
        const FQuat Y(FVector(0.f, 0.f, 1.f), FMath::DegreesToRadians(YawDeg));
        return (Y * R * P).GetNormalized();
    };
    const FBreed& Breed = Breeds[Appearance.Breed];
    OutNode.PelvisOffsetCS = Breed.Seat + FVector(0.f, 0.f, PelvisHeaveCm);
    OutNode.PelvisDeltaCS = Turn(TorsoPitchDeg * .18f, TorsoRollDeg * .22f, 0.f);
    OutNode.SpineDeltaCS = Turn(TorsoPitchDeg * .26f, TorsoRollDeg * .25f, TorsoYawDeg * .20f);
    OutNode.SpineMidDeltaCS = Turn(TorsoPitchDeg * .28f, TorsoRollDeg * .25f, TorsoYawDeg * .25f);
    OutNode.ChestDeltaCS = Turn(TorsoPitchDeg * .28f, TorsoRollDeg * .28f, TorsoYawDeg * .30f);
    // The neck and head take back about two thirds of the chest's pitch and roll: his gaze stays on the horizon.
    OutNode.NeckDeltaCS = Turn(-TorsoPitchDeg * .32f, -TorsoRollDeg * .35f, TorsoYawDeg * .15f);
    OutNode.HeadDeltaCS = Turn(-TorsoPitchDeg * .35f, -TorsoRollDeg * .35f, TorsoYawDeg * .10f);
    // Steering pulls the inside rein back and opens it out; reining in pulls both.
    const float Rein = bReinIn ? 2.8f : 0.f;
    const float Left = FMath::Max(-Steering, 0.f), Right = FMath::Max(Steering, 0.f);
    OutNode.LeftHandOffsetCS = Breed.GripL + FVector(-(Left * 3.2f + Rein), -Left * 2.2f, 0.f);
    OutNode.RightHandOffsetCS = Breed.GripR + FVector(-(Right * 3.2f + Rein), Right * 2.2f, 0.f);
    // The instep in the stirrup's hoop: the boot's toe through it, centred between its sides, on the tread.
    OutNode.LeftFootOffsetCS = Breed.StirrupL + FVector(2.8f, 1.5f, -.8f);
    OutNode.RightFootOffsetCS = Breed.StirrupR + FVector(2.8f, -1.5f, -.8f);
}

UAnimSequence* UHorseComponent::GetSequence() const
{
    if (Phase == EPhase::Stowed || RiderClips.Num() != HorseRide::RoleCount) return nullptr;
    UAnimSequence* Clip = RiderClips[int32(Role)];
    return Clip ? Clip : RiderClips[int32(EHorseRole::Idle)].Get();
}

float UHorseComponent::GetPoseTime() const
{
    const float Length = ClipLength(Role);
    return FMath::Min(GaitPhase * Length, Length - .001f);
}

FName UHorseComponent::GetRiderClip() const { return HorseRide::RoleOf(Role).Rider; }

UAnimSequence* UHorseComponent::GetHorseSequence() const
{
    // A role the breed has no clip for plays its Idle, as GetSequence does for the rider: the horse never freezes.
    UAnimSequence* Clip = HorseClips.IsValidIndex(int32(Role)) ? HorseClips[int32(Role)].Get() : nullptr;
    return Clip ? Clip : HorseClips.IsValidIndex(int32(EHorseRole::Idle)) ? HorseClips[int32(EHorseRole::Idle)].Get() : nullptr;
}

FName UHorseComponent::GetHorseClip() const
{
    const UAnimSequence* Clip = GetHorseSequence();
    return Clip ? Clip->GetFName() : FName(HorseRide::RoleOf(Role).Horse);
}

FString UHorseComponent::GetStatus() const
{
    if (!Breeds.IsValidIndex(Appearance.Breed)) return Hint;
    const FString Status = FString::Printf(TEXT("%s (%s, tack %s) - %s"), *Breeds[Appearance.Breed].Name, *GetCoatId(), *GetTackId(), HorseRide::RoleOf(Role).Label);
    return Hint.IsEmpty() ? Status : Status + TEXT("   ") + Hint;
}

FTransform UHorseComponent::GetHorseTransform() const { return HorseRoot ? HorseRoot->GetComponentTransform() : FTransform::Identity; }
FString UHorseComponent::GetBreedId() const { return Breeds.IsValidIndex(Appearance.Breed) ? Breeds[Appearance.Breed].Slug : FString(); }
FString UHorseComponent::GetTackId() const { return TackIds.IsValidIndex(Appearance.Tack) ? TackIds[Appearance.Tack] : FString(); }
FString UHorseComponent::GetCoatId() const { return CoatVariants.IsValidIndex(Appearance.Coat - 1) ? CoatVariants[Appearance.Coat - 1].Id : TEXT("native"); }
FString UHorseComponent::GetMaskId() const { return CoatMasks.IsValidIndex(Appearance.Mask) ? CoatMasks[Appearance.Mask].Key : TEXT("Solid"); }
FString UHorseComponent::GetHairColorId() const { return HairColors.IsValidIndex(Appearance.HairColor - 1) ? HairColors[Appearance.HairColor - 1].Id : TEXT("native"); }
FString UHorseComponent::GetHairPatternId() const { return HairPatterns.IsValidIndex(Appearance.HairPattern) ? HairPatterns[Appearance.HairPattern].Id : TEXT("solid"); }
FString UHorseComponent::GetTintId() const { return Tints.IsValidIndex(Appearance.Tint) ? Tints[Appearance.Tint].Id : TEXT("natural"); }
