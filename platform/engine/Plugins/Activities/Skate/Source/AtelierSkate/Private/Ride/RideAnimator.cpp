#include "RideAnimator.h"
#include "RideAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Animation/MirrorDataTable.h"
#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/Actor.h"

using atelier::ride::Flick;

namespace
{
    const TCHAR* RigPath = TEXT("/Game/SkateRide/SK_SkateRider.SK_SkateRider");
    const TCHAR* MirrorPath = TEXT("/Game/SkateRide/MDT_SkateRider.MDT_SkateRider");
    const TCHAR* ClipFolders[] = {TEXT("/Game/SkateRide/Clips/B0/"), TEXT("/Game/SkateRide/Clips/B1/")};
    const FName BoardRoot(TEXT("SKATEBOARD_ROOT"));

    // The board's bones in the published order (deck, trucks, then the wheels of the front and back truck) and, for
    // the board-only fallback, their bind relative to the deck's pivot (cm, from the native rig's reference pose).
    const TCHAR* BoardBones[] = {TEXT("SKATEBOARD_ROOT"), TEXT("TRUCK_FRONT"), TEXT("TRUCK_BACK"),
        TEXT("RIGHT_WHEELFRONT"), TEXT("LEFT_WHEELFRONT"), TEXT("RIGHT_WHEELBACK"), TEXT("LEFT_WHEELBACK")};
    const FVector BoardBind[] = {{0, 0, 0}, {25.92f, 0, -2.78f}, {-25.92f, 0, -2.78f},
        {24.29f, 9.75f, -5.65f}, {24.29f, -9.75f, -5.65f}, {-24.35f, 9.75f, -5.63f}, {-24.35f, -9.75f, -5.63f}};
    // The deck's nose and tail tips in its own frame (the lowest points of a pitched board besides the wheels).
    const FVector DeckTips[] = {{40.f, 0, -1.5f}, {-40.f, 0, -1.5f}};

    // The push: the first push of a run plays its lead-in from here (the native runtime starts it here too).
    constexpr float PushIntoStart = .231f;
    // Sampling a pre-landing pose this long before the touch-down.
    constexpr float LandingLead = .217f;
    // A landing pose plays over this long.
    constexpr float LandHold = 1.f;
    // A flip's board is caught once it stays within this of its final attitude (the board is symmetric end to end).
    constexpr float CatchAngle = 25.f;
    // How much of the follow-through clip the catch search reads.
    constexpr float CatchWindow = .4f;
    // The pose's lift decays this fast once the board leaves the ground (cm/s).
    constexpr float LiftDecay = 150.f;
    // Between two clips whose boards differ by more than this (degrees), the board was turned end for end.
    constexpr float TurnedBoard = 90.f;

    float Len(const UAnimSequence* Sequence) { return Sequence ? Sequence->GetPlayLength() : 0.f; }

    struct FTrickNames { Flick Trick; const TCHAR* Ground; const TCHAR* Air; const TCHAR* Follow; };
    const FTrickNames TrickNames[] = {
        {Flick::Ollie, TEXT("OLLIE_HIGH_G"), TEXT("OLLIE_HIGH_A"), nullptr},
        {Flick::Nollie, TEXT("NOLLIE_HIGH_G"), TEXT("NOLLIE_HIGH_A"), nullptr},
        {Flick::Kickflip, TEXT("KICKFLIP_IN_HIGH_G"), TEXT("KICKFLIP_IN_HIGH_A"), TEXT("T_KICKFLIP_HI_4FLIPS_0_OUT1")},
        {Flick::Heelflip, TEXT("HEELFLIP_IN_HIGH_G"), TEXT("HEELFLIP_IN_HIGH_A"), TEXT("T_HEELFLIP_HI_4FLIPS_0_OUT1")},
        {Flick::ShoveIt, TEXT("POPSHUVIT_HIGH_G"), TEXT("POPSHUVIT_HIGH_A"), TEXT("T_POPSHUVIT_H_CYC")},
        {Flick::FsShoveIt, TEXT("FSPOPSHUVIT_D_HIGH_G"), TEXT("FSPOPSHUVIT_D_HIGH_A"), TEXT("T_FSPOPSHUVIT_H_CYC")},
        {Flick::Shove360, TEXT("360POPSHUVIT_HIGH_G"), TEXT("360POPSHUVIT_HIGH_A"), TEXT("T_360POPSHUVIT_H_CYC")},
        {Flick::FsShove360, TEXT("FS360POPSHUVIT_HIGH_G"), TEXT("FS360POPSHUVIT_HIGH_A"), TEXT("T_FS360POPSHUVIT_H_CYC")},
        {Flick::VarialKickflip, TEXT("VARIALKICKFLIP_HIGH_G"), TEXT("VARIALKICKFLIP_HIGH_A"), TEXT("T_VARIALKICKFLIP_H_CYC")},
        {Flick::VarialHeelflip, TEXT("VARIALHEELFLIP_D_HIGH_G"), TEXT("VARIALHEELFLIP_D_HIGH_A"), TEXT("T_VARIALHEELFLIP_H_CYC")},
        {Flick::Hardflip, TEXT("HARDFLIP_HIGH_G"), TEXT("HARDFLIP_HIGH_A"), TEXT("T_HARDFLIP_H_CYC")},
        {Flick::InwardHeelflip, TEXT("INWARDHEELFLIP_HIGH_G"), TEXT("INWARDHEELFLIP_HIGH_A"), nullptr},
        {Flick::TreFlip, TEXT("360FLIP_D_HIGH_G"), TEXT("360FLIP_D_HIGH_A"), TEXT("T_360FLIP_H_CYC")},
        {Flick::LaserFlip, TEXT("LASERFLIP_HIGH_G"), TEXT("LASERFLIP_HIGH_A"), TEXT("T_LASERFLIP_H_CYC")},
        {Flick::Hardflip360, TEXT("360HARDFLIP_HIGH_G"), TEXT("360HARDFLIP_HIGH_A"), TEXT("T_360HARDFLIP_H_CYC")},
        {Flick::InwardHeelflip360, TEXT("360INWARDHEELFLIP_HIGH_G"), TEXT("360INWARDHEELFLIP_HIGH_A"), TEXT("T_360INWARDHEELFLIP_H_CYC")},
    };
    // By ERideGrab (None first): lead-in, hold, let-go.
    const TCHAR* GrabNames[][3] = {
        {nullptr, nullptr, nullptr},
        {TEXT("GR_GRAB_N_FS_0_INTO"), TEXT("GR_GRAB_N_FS_0_CYC"), TEXT("GR_GRAB_N_FS_0_OUT")},
        {TEXT("GR_GRAB_N_BS_0_INTO"), TEXT("GR_MELON_N_BS_0_CYC"), TEXT("GR_GRAB_N_BS_0_OUT")},
        {TEXT("GR_DSMNT_CHRIST_BS_0_INTO"), TEXT("GR_DSMNT_CHRIST_BS_0_CYC"), TEXT("GR_DSMNT_CHRIST_BS_0_OUT")},
        {TEXT("1FT_AIR_GRAB_N_BSL_0_INTO"), TEXT("1FT_AIR_GRAB_N_BSL_0_CYC"), TEXT("1FT_AIR_GRAB_N_BSL_0_OUT")},
        {TEXT("GR_GRAB_N_FS_0_INTO"), TEXT("GR_TKNEE_N_FS_0_CYC"), TEXT("GR_GRAB_N_FS_0_OUT")},
    };
    // By ERideGrind: frontside, backside.
    const TCHAR* GrindNames[][2] = {
        {TEXT("G_5050_FS_HI_0_CYC"), TEXT("G_5050_BF_HI_0_CYC")},
        {TEXT("G_50_BF_HI_0_CYC"), TEXT("G_50_BS_HI_0_CYC")},
        {TEXT("G_NGRIND_BF_HI_0_CYC"), TEXT("G_NGRIND_BS_HI_0_CYC")},
        {TEXT("G_CROOKS_FS_HI_0_CYC"), TEXT("G_CROOKS_BS_HI_0_CYC")},
        {TEXT("G_BSLIDE_FS_HI_0_CYC"), TEXT("G_BSLIDE_BS_HI_0_CYC")},
        {TEXT("G_LIPSLIDE_FS_HI_0_CYC"), TEXT("G_LIPSLIDE_BS_HI_0_CYC")},
    };

    /** The angle between two board attitudes, a half turn about the board's up axis counting as none (the board is
     *  the same end to end). */
    float BoardAngle(const FQuat& A, const FQuat& B)
    {
        const FQuat Turned = B * FQuat(FVector::UpVector, PI);
        return FMath::RadiansToDegrees(FMath::Min(A.AngularDistance(B), A.AngularDistance(Turned)));
    }

    float TimeOf(const FRideAnimLayers& Layers, const UAnimSequence* Clip)
    {
        for (int32 I = 0; I < Layers.Num; ++I) if (Layers.Layer[I].Clip == Clip) return Layers.Layer[I].Time;
        return 0;
    }

    bool OnGround(ERideMotion Motion)
    {
        switch (Motion)
        {
        case ERideMotion::Air: case ERideMotion::Bail: return false;
        default: return true;
        }
    }
}

FRideAnimator::FRideAnimator() { SetBoardOnly(); }

// The pose mesh belongs to its owner actor and goes with it; the session may outlive neither.
FRideAnimator::~FRideAnimator() = default;

void FRideAnimator::SetBoardOnly()
{
    BoardNames.Reset(); BoardReference.Reset();
    for (int32 I = 0; I < 7; ++I) { BoardNames.Add(BoardBones[I]); BoardReference.Add(FTransform(BoardBind[I])); }
    SetBoardIndices(BoardNames, BoardReference);
}

bool FRideAnimator::SetBoardIndices(const TArray<FName>& InNames, const TArray<FTransform>& InReference)
{
    int32 Index[7];
    for (int32 I = 0; I < 7; ++I)
    {
        Index[I] = InNames.IndexOfByKey(FName(BoardBones[I]));
        if (Index[I] == INDEX_NONE) return false;
    }
    DeckIndex = Index[0];
    for (int32 I = 0; I < 2; ++I) TruckIndex[I] = Index[1 + I];
    for (int32 I = 0; I < 4; ++I) WheelIndex[I] = Index[3 + I];
    const FTransform& Deck = InReference[DeckIndex];
    for (int32 I = 0; I < 2; ++I)
    {
        TruckFromDeck[I] = InReference[TruckIndex[I]].GetRelativeTransform(Deck);
        TruckAxis[I] = TruckFromDeck[I].GetRotation().UnrotateVector(FVector::ForwardVector);
    }
    for (int32 I = 0; I < 4; ++I)
    {
        WheelFromTruck[I] = InReference[WheelIndex[I]].GetRelativeTransform(InReference[TruckIndex[I / 2]]);
        const FTransform InDeck = InReference[WheelIndex[I]].GetRelativeTransform(Deck);
        WheelInDeck[I] = InDeck.GetLocation();
        WheelAxis[I] = InDeck.GetRotation().UnrotateVector(FVector::RightVector);
    }
    return true;
}

UAnimSequence* FRideAnimator::Load(const TCHAR* Name)
{
    if (!Name) return nullptr;
    const FName Key(Name);
    if (const TStrongObjectPtr<UAnimSequence>* Found = Library.Find(Key)) return Found->Get();
    UAnimSequence* Sequence = nullptr;
    for (const TCHAR* Folder : ClipFolders)
    {
        const FString Path = FString::Printf(TEXT("%s%s.%s"), Folder, Name, Name);
        Sequence = LoadObject<UAnimSequence>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
        if (Sequence) break;
    }
    if (!Sequence) UE_LOG(LogTemp, Warning, TEXT("SKATE ride: no clip %s"), Name);
    Library.Add(Key, TStrongObjectPtr<UAnimSequence>(Sequence));
    return Sequence;
}

UAnimSequence* FRideAnimator::Clip(FName Name)
{
    if (!bRig || Name.IsNone()) return nullptr;
    UAnimSequence* Sequence = Load(*Name.ToString());
    if (Sequence && Instance.IsValid()) Instance->Hold({Sequence});
    return Sequence;
}

void FRideAnimator::Resolve()
{
    C.Roll[0] = Load(TEXT("R_IDLE_HCOM_000")); C.Roll[1] = Load(TEXT("R_IDLE_HCOM_P100"));
    C.Roll[2] = Load(TEXT("R_IDLE_HCOM_N100")); C.Roll[3] = Load(TEXT("R_IDLE_LCOM_000"));
    C.PushInto = Load(TEXT("R_PUSHLSP_HSTR_N_0_INTO")); C.PushOut = Load(TEXT("R_PUSH_H_N_OUT_FRONT"));
    C.PushContact[0] = Load(TEXT("R_PUSHLSP_HSTR_N_0_CYC1")); C.PushRecover[0] = Load(TEXT("R_PUSHLSP_HSTR_N_0_CYC2"));
    C.PushContact[1] = Load(TEXT("R_PUSHHSP_HSTR_N_0_CYC1")); C.PushRecover[1] = Load(TEXT("R_PUSHHSP_HSTR_N_0_CYC2"));
    C.BrakeInto = Load(TEXT("R_BRAKE_N_N_0_INTO")); C.BrakeCycle = Load(TEXT("R_BRAKE_N_N_0_CYC")); C.BrakeOut = Load(TEXT("R_BRAKE_N_N_0_OUT"));
    C.StandFromBrake = Load(TEXT("R_STAND_FROMLSBRAKE_N_0_TR")); C.Stand = Load(TEXT("R_STAND_IDLE2_N_0_CYC")); C.StandOut = Load(TEXT("R_STAND_IDLE2_N_0_OUT"));
    C.SlideInto[0] = Load(TEXT("R_SLIDE_FS_LSP_INTO")); C.SlideCycle[0] = Load(TEXT("R_SLIDE_FS_LSP_CYC")); C.SlideOut[0] = Load(TEXT("R_SLIDE_FS_LSP_OUT_000"));
    C.SlideInto[1] = Load(TEXT("R_SLIDE_BS_LSP_INTO")); C.SlideCycle[1] = Load(TEXT("R_SLIDE_BS_LSP_CYC")); C.SlideOut[1] = Load(TEXT("R_SLIDE_BS_LSP_OUT_000"));
    C.Manual = Load(TEXT("M_IDLE_N_0_CYC"));
    C.NoseInto = Load(TEXT("M_NOSEIDLE_N_0_INTO")); C.NoseCycle = Load(TEXT("M_NOSEIDLE_N_0_CYC")); C.NoseOut = Load(TEXT("M_NOSEIDLE_N_0_OUT"));
    C.Load = Load(TEXT("R_ANTIC_OLLIE_N_0_INTO")); C.NoseLoad = Load(TEXT("R_ANTIC_NOLLIE_N_0_INTO"));
    C.AirIdle = Load(TEXT("IA_IDLE_N_N_0_CYC")); C.AirLow = Load(TEXT("IA_IDLE_LO_N_0_CYC")); C.AirExtend = Load(TEXT("IA_EXTEND_LO_N_0_CYC"));
    C.LandLow = Load(TEXT("L_HCOM_LIMP_3")); C.LandHigh = Load(TEXT("L_HCOM_HIMP_3")); C.LandGrab = Load(TEXT("L_LCOM_3"));
    C.LandSketchy = Load(TEXT("L_SKETCH_FS_HCOM_LIMP"));
    for (const FTrickNames& T : TrickNames)
    {
        FTrickClips& Clips = C.Tricks[uint8(T.Trick)];
        Clips.Ground = Load(T.Ground); Clips.Air = Load(T.Air); Clips.Follow = Load(T.Follow);
    }
    for (int32 G = 1; G < 6; ++G)
    {
        C.Grabs[G].Into = Load(GrabNames[G][0]); C.Grabs[G].Cycle = Load(GrabNames[G][1]); C.Grabs[G].Out = Load(GrabNames[G][2]);
    }
    for (int32 G = 0; G < 6; ++G) for (int32 S = 0; S < 2; ++S) C.Grinds[G][S] = Load(GrindNames[G][S]);
}

void FRideAnimator::Preload()
{
    if (bTried) return;
    bTried = true;
    USkeletalMesh* Rig = LoadObject<USkeletalMesh>(nullptr, RigPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
    UMirrorDataTable* Table = LoadObject<UMirrorDataTable>(nullptr, MirrorPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
    if (!Rig)
    {
        UE_LOG(LogTemp, Display, TEXT("SKATE ride: no rider rig in this build; the board rides alone"));
        return;
    }
    // The published names and reference: the rig's bones in its own order, in its reference pose (RIG_TPOSE)
    // composed to root space.
    const FReferenceSkeleton& Skeleton = Rig->GetRefSkeleton();
    const TArray<FTransform>& Local = Skeleton.GetRefBonePose();
    TArray<FName> RigNames; TArray<FTransform> RigReference;
    for (int32 I = 0; I < Skeleton.GetNum(); ++I)
    {
        const int32 Parent = Skeleton.GetParentIndex(I);
        RigNames.Add(Skeleton.GetBoneName(I));
        RigReference.Add(Parent == INDEX_NONE ? Local[I] : Local[I] * RigReference[Parent]);
    }
    if (!SetBoardIndices(RigNames, RigReference))
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride: the rider rig has no board bones; the board rides alone"));
        SetBoardOnly();
        return;
    }
    Names = MoveTemp(RigNames); Reference = MoveTemp(RigReference);
    RigMesh.Reset(Rig); MirrorTable.Reset(Table);
    Resolve();
    if (!C.Roll[0] || !C.AirIdle || !C.Tricks[uint8(Flick::Ollie)].Air)
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride: the riding clips are missing; the board rides alone"));
        SetBoardOnly();
        return;
    }
    for (FTrickClips& T : C.Tricks) if (T.Air) T.Catch = FindCatch(T);
    bRig = true;
    const int32 Hips = Names.IndexOfByKey(FName(TEXT("HIPS")));
    UE_LOG(LogTemp, Display, TEXT("SKATE ride: rider rig with %d bones and %d clips (hips %.1f cm, deck %.1f cm; mirror %s); kickflip pop %.3f s, catch %.3f s"),
        Names.Num(), Library.Num(), Hips != INDEX_NONE ? Reference[Hips].GetLocation().Z : 0.f, Reference[DeckIndex].GetLocation().Z,
        Table ? TEXT("yes") : TEXT("no"), PopDelay(Flick::Kickflip, 0.f), CatchTime(Flick::Kickflip, 0.f));
}

float FRideAnimator::FindCatch(const FTrickClips& T) const
{
    // The board's attitude through the flip and the start of its follow-through; it is caught from the first key
    // after which it stays near where it ends.
    TArray<TPair<float, FQuat>> Keys;
    const FFrameRate RateA = T.Air->GetSamplingFrameRate();
    const int32 CountA = T.Air->GetNumberOfSampledKeys();
    for (int32 K = 0; K < CountA; ++K)
    {
        const float Time = float(RateA.AsSeconds(K));
        Keys.Add({Time, Track(T.Air, BoardRoot, Time).GetRotation()});
    }
    if (T.Follow)
    {
        const FFrameRate RateF = T.Follow->GetSamplingFrameRate();
        for (int32 K = 1; K < T.Follow->GetNumberOfSampledKeys(); ++K)
        {
            const float Time = float(RateF.AsSeconds(K));
            if (Time > CatchWindow) break;
            Keys.Add({Len(T.Air) + Time, Track(T.Follow, BoardRoot, Time).GetRotation()});
        }
    }
    if (Keys.IsEmpty()) return -1;
    const FQuat Final = Keys.Last().Value;
    float Catch = 0;
    for (int32 K = 0; K < Keys.Num(); ++K)
        if (BoardAngle(Keys[K].Value, Final) > CatchAngle) Catch = Keys[FMath::Min(K + 1, Keys.Num() - 1)].Key;
    return Catch;
}

const FRideAnimator::FTrickClips* FRideAnimator::TrickFor(Flick Trick) const
{
    const uint8 Index = uint8(Trick);
    if (Index == 0 || Index >= UE_ARRAY_COUNT(C.Tricks)) return nullptr;
    const FTrickClips& T = C.Tricks[Index];
    if (T.Ground && T.Air) return &T;
    const FTrickClips& Ollie = C.Tricks[uint8(Flick::Ollie)];
    return Ollie.Ground && Ollie.Air ? &Ollie : nullptr;
}

float FRideAnimator::PopDelay(Flick Trick, float Default) const
{
    const FTrickClips* T = bRig ? TrickFor(Trick) : nullptr;
    return T ? Len(T->Ground) : Default;
}

float FRideAnimator::CatchTime(Flick Trick, float Default) const
{
    const FTrickClips* T = bRig ? TrickFor(Trick) : nullptr;
    return T && T->Catch >= 0 ? T->Catch : Default;
}

bool FRideAnimator::PushTiming(bool bFirstPush, float Strong, float& Lead, float& Contact, float& Recover) const
{
    if (!bRig || !C.PushContact[0] || !C.PushRecover[0]) return false;
    // The first push of a run starts from the slow push; later ones blend toward the fast push with speed.
    const float S = bFirstPush ? 0.f : FMath::Clamp(Strong, 0.f, 1.f);
    Lead = bFirstPush && C.PushInto ? FMath::Max(0.f, Len(C.PushInto) - PushIntoStart) : 0.f;
    Contact = FMath::Lerp(Len(C.PushContact[0]), C.PushContact[1] ? Len(C.PushContact[1]) : Len(C.PushContact[0]), S);
    Recover = FMath::Lerp(Len(C.PushRecover[0]), C.PushRecover[1] ? Len(C.PushRecover[1]) : Len(C.PushRecover[0]), S);
    return true;
}

FTransform FRideAnimator::Track(const UAnimSequence* Sequence, FName Bone, float Time)
{
    const USkeleton* Skeleton = Sequence ? Sequence->GetSkeleton() : nullptr;
    const int32 Index = Skeleton ? Skeleton->GetReferenceSkeleton().FindBoneIndex(Bone) : INDEX_NONE;
    if (Index == INDEX_NONE) return FTransform::Identity;
    FTransform Out;
    Sequence->GetBoneTransform(Out, FSkeletonPoseBoneIndex(Index), FAnimExtractContext(double(Time)), false);
    return Out;
}

FTransform FRideAnimator::RootMotion(const UAnimSequence* Sequence, float From, float To)
{
    return Sequence ? Sequence->ExtractRootMotionFromRange(From, To, FAnimExtractContext()) : FTransform::Identity;
}

float FRideAnimator::SampleTime(const UAnimSequence* Sequence, float Time, bool bLoop)
{
    const float Length = Len(Sequence);
    if (Length <= 0) return 0;
    return bLoop ? FMath::Fmod(FMath::Max(Time, 0.f), Length) : FMath::Clamp(Time, 0.f, Length);
}

// ---------------------------------------------------------------------------------------------------------------
// The pose mesh.

void FRideAnimator::Attach(AActor* Owner)
{
    if (!bRig || !Owner) return;
    if (Mesh.IsValid() && Mesh->GetOwner() == Owner && Instance.IsValid()) return;
    Detach();
    // A hidden, unattached, stationary mesh: the session moves the rider, so the graph (and its inertialization)
    // only ever sees the clips' own root space.
    USkeletalMeshComponent* M = NewObject<USkeletalMeshComponent>(Owner, MakeUniqueObjectName(Owner, USkeletalMeshComponent::StaticClass(), TEXT("RidePose")), RF_Transient);
    M->SetUsingAbsoluteLocation(true); M->SetUsingAbsoluteRotation(true); M->SetUsingAbsoluteScale(true);
    M->PrimaryComponentTick.bCanEverTick = false;
    M->SetSkeletalMeshAsset(RigMesh.Get());
    M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
    M->SetAnimInstanceClass(USkateRideAnimInstance::StaticClass());
    M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    M->bEnableUpdateRateOptimizations = false;
    M->SetHiddenInGame(true); M->SetVisibility(false); M->SetCastShadow(false);
    M->SetCollisionEnabled(ECollisionEnabled::NoCollision); M->SetGenerateOverlapEvents(false);
    M->SetCanEverAffectNavigation(false);
    M->SetForcedLOD(1);
    M->RegisterComponent();
    USkateRideAnimInstance* I = Cast<USkateRideAnimInstance>(M->GetAnimInstance());
    if (!I)
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride: the rider's anim instance did not start; the board rides alone"));
        M->DestroyComponent();
        return;
    }
    I->SetMirrorTable(Cast<UMirrorDataTable>(MirrorTable.Get()));
    I->SetBoardBone(BoardRoot);
    TArray<UAnimSequence*> Clips;
    for (const TPair<FName, TStrongObjectPtr<UAnimSequence>>& Pair : Library) if (Pair.Value) Clips.Add(Pair.Value.Get());
    I->Hold(Clips);
    Mesh = M; Instance = I;
    bFirst = true; Lock = 0; Lift = 0; LastKey = nullptr; Last = FRideAnimLayers();
}

void FRideAnimator::Detach()
{
    if (USkeletalMeshComponent* M = Mesh.Get()) if (!M->IsBeingDestroyed()) M->DestroyComponent();
    Mesh.Reset(); Instance.Reset();
}

void FRideAnimator::Run(const FRideAnimLayers& Layers, float Inertialize, float Dt, bool bCutBoard)
{
    FRideAnimFrame Frame;
    Frame.Layers = Layers; Frame.Inertialize = Inertialize; Frame.bCutBoard = bCutBoard;
    Instance->SetFrame(Frame);
    USkeletalMeshComponent* M = Mesh.Get();
    M->TickAnimation(FMath::Max(Dt, 0.f), false);
    M->RefreshBoneTransforms(nullptr);
    Last = Layers;
}

float FRideAnimator::GetCurve(FName Curve) const
{
    return Instance.IsValid() ? Instance->GetCurveValue(Curve) : 0.f;
}

const TArray<FTransform>& FRideAnimator::GetComponentPose() const
{
    return Mesh.IsValid() ? Mesh->GetComponentSpaceTransforms() : Empty;
}

FName FRideAnimator::GetMainClip() const
{
    const UAnimSequence* Main = Last.Main();
    return Main ? Main->GetFName() : NAME_None;
}

void FRideAnimator::SetOverride(const FRideAnimLayers& Layers, float BlendIn)
{
    if (!bOverride || Layers.Main() != Override.Main()) PendingBlend = FMath::Max(PendingBlend, BlendIn);
    bOverride = true; Override = Layers; OverrideBlend = BlendIn;
}

void FRideAnimator::ClearOverride(float BlendOut)
{
    if (!bOverride) return;
    bOverride = false;
    if (BlendOut > 0) PendingBlend = FMath::Max(PendingBlend, BlendOut);
    else { bCutNext = true; PendingBlend = 0; }
}

// ---------------------------------------------------------------------------------------------------------------
// The clip choice.

const UAnimSequence* FRideAnimator::Choose(const FRideBodyPose& B, FRideAnimLayers& L, float& Blend) const
{
    L.Reset(); L.Lock = 0; L.bMirror = !B.bGoofy;
    Blend = .15f;
    // The session's times are at its last tick; the drawn frame trails it by Lag.
    auto At = [&B](float Time) { return FMath::Max(0.f, Time - B.Lag); };
    const float Motion = At(B.MotionTime), Clock = At(B.Clock);
    auto Exit = [&L](UAnimSequence* Out, float Time)
    {
        if (!Out || Time >= Len(Out)) return false;
        L.Add(Out, Time, 1.f);
        return true;
    };
    auto Roll = [&]() -> const UAnimSequence*
    {
        // Leaning toward the toes or the heels, crouched or standing.
        const float Lean = FMath::Clamp(B.Lean, -1.f, 1.f);
        const float Low = FMath::Clamp((B.Crouch - .25f) / .75f, 0.f, 1.f);
        L.Add(C.Roll[0], SampleTime(C.Roll[0], Clock, true), (1.f - FMath::Abs(Lean)) * (1.f - Low));
        L.Add(C.Roll[1], SampleTime(C.Roll[1], Clock, true), FMath::Max(Lean, 0.f) * (1.f - Low));
        L.Add(C.Roll[2], SampleTime(C.Roll[2], Clock, true), FMath::Max(-Lean, 0.f) * (1.f - Low));
        L.Add(C.Roll[3], SampleTime(C.Roll[3], Clock, true), Low);
        if (L.Num == 0) L.Add(C.Roll[0], SampleTime(C.Roll[0], Clock, true), 1.f);
        return C.Roll[0];
    };

    switch (B.Motion)
    {
    case ERideMotion::Push:
    {
        // One cycle: the lead-in (first push of a run), the kick (foot on the ground) and the recovery, each clip
        // stretched over the session's phase; later pushes blend the slow and the fast push by speed.
        const float T = At(FMath::Max(B.PushTime, 0.f));
        const bool bFirstPush = B.PushCount == 0;
        Blend = B.MotionTime < .1f ? .15f : 0.f;
        if (bFirstPush && C.PushInto && T < B.PushLead)
        {
            const float Rate = (Len(C.PushInto) - PushIntoStart) / FMath::Max(.05f, B.PushLead);
            L.Add(C.PushInto, FMath::Min(PushIntoStart + T * Rate, Len(C.PushInto)), 1.f);
            return C.PushInto;
        }
        const float U = T - (bFirstPush ? B.PushLead : 0.f);
        const float Strong = bFirstPush ? 0.f : FMath::Clamp(B.PushStrong, 0.f, 1.f);
        if (U < B.PushContact)
        {
            const float F = FMath::Clamp(U / FMath::Max(.01f, B.PushContact), 0.f, 1.f);
            L.Add(C.PushContact[0], F * Len(C.PushContact[0]), 1.f - Strong);
            L.Add(C.PushContact[1], F * Len(C.PushContact[1]), Strong);
            return C.PushContact[0];
        }
        const float F = FMath::Clamp((U - B.PushContact) / FMath::Max(.01f, B.PushRecover), 0.f, 1.f);
        L.Add(C.PushRecover[0], F * Len(C.PushRecover[0]), 1.f - Strong);
        L.Add(C.PushRecover[1], F * Len(C.PushRecover[1]), Strong);
        return C.PushRecover[0];
    }
    case ERideMotion::Brake:
        if (B.StillTime >= 0)
        {
            // Stopped: step off into the standing idle.
            const float T = At(B.StillTime);
            if (Exit(C.StandFromBrake, T)) return C.StandFromBrake;
            Blend = .1f;
            L.Add(C.Stand, SampleTime(C.Stand, T - Len(C.StandFromBrake), true), 1.f);
            return C.Stand;
        }
        if (Exit(C.BrakeInto, Motion)) return C.BrakeInto;
        Blend = .1f;
        L.Add(C.BrakeCycle, SampleTime(C.BrakeCycle, Motion - Len(C.BrakeInto), true), 1.f);
        return C.BrakeCycle;
    case ERideMotion::Powerslide:
    {
        const int32 Side = B.bSlideFront ? 0 : 1;
        Blend = .1f;
        if (Exit(C.SlideInto[Side], Motion)) return C.SlideInto[Side];
        Blend = .08f;
        L.Add(C.SlideCycle[Side], SampleTime(C.SlideCycle[Side], Motion - Len(C.SlideInto[Side]), true), 1.f);
        return C.SlideCycle[Side];
    }
    case ERideMotion::Manual:
        L.Add(C.Manual, SampleTime(C.Manual, Motion, true), 1.f);
        return C.Manual;
    case ERideMotion::NoseManual:
        if (Exit(C.NoseInto, Motion)) return C.NoseInto;
        Blend = .08f;
        L.Add(C.NoseCycle, SampleTime(C.NoseCycle, Motion - Len(C.NoseInto), true), 1.f);
        return C.NoseCycle;
    case ERideMotion::Load:
    {
        // The stick resting on the rim: the anticipation, held at its end.
        UAnimSequence* Clip = B.bNoseLoad && C.NoseLoad ? C.NoseLoad : C.Load;
        Blend = .12f;
        L.Add(Clip, FMath::Min(At(B.LoadTime), Len(Clip)), 1.f);
        return Clip;
    }
    case ERideMotion::Pop:
    {
        const FTrickClips* T = TrickFor(B.Trick == Flick::None ? Flick::Ollie : B.Trick);
        if (!T) return Roll();
        Blend = .05f;
        const float Scale = Len(T->Ground) / FMath::Max(.05f, B.PopDelay);
        L.Add(T->Ground, FMath::Min(At(FMath::Max(B.PopTime, 0.f)) * Scale, Len(T->Ground)), 1.f);
        return T->Ground;
    }
    case ERideMotion::Air:
    {
        const FTrickClips* T = B.Trick != Flick::None && B.TrickTime >= 0 ? TrickFor(B.Trick) : nullptr;
        const float TT = At(FMath::Max(B.TrickTime, 0.f));
        const float Catch = T ? (T->Catch >= 0 ? T->Catch : Len(T->Air)) : 0.f;
        // A grab once the board is under the feet again.
        if (B.Grab != ERideGrab::None && (!T || TT >= Catch))
        {
            const FGrabClips& G = C.Grabs[uint8(B.Grab)];
            const float GT = At(B.GrabTime);
            Blend = .1f;
            if (Exit(G.Into, GT)) return G.Into;
            Blend = .05f;
            L.Add(G.Cycle, SampleTime(G.Cycle, GT - Len(G.Into), true), 1.f);
            if (L.Num > 0) return G.Cycle;
        }
        if (B.SinceGrab >= 0 && B.LastGrab != ERideGrab::None)
        {
            Blend = .08f;
            UAnimSequence* Out = C.Grabs[uint8(B.LastGrab)].Out;
            if (Exit(Out, At(B.SinceGrab))) return Out;
        }
        const bool bLow = B.TimeToLand >= 0 && B.TimeToLand <= LandingLead;
        if (T && TT < Len(T->Air))
        {
            // Straight on from the pop clip (a cut, as the clips are cut to follow on); a flick later in the air
            // cross-fades in.
            Blend = B.PreviousMotion == ERideMotion::Pop && B.TrickTime < .1f ? 0.f : .1f;
            L.Add(T->Air, TT, 1.f);
            return T->Air;
        }
        if (T && T->Follow && !bLow && TT - Len(T->Air) < Len(T->Follow))
        {
            Blend = 0.f;
            L.Add(T->Follow, TT - Len(T->Air), 1.f);
            return T->Follow;
        }
        if (bLow && C.AirLow)
        {
            // Reaching for the landing.
            Blend = .1f;
            const float AT = At(B.AirTime);
            L.Add(C.AirLow, SampleTime(C.AirLow, AT, true), .5f);
            L.Add(C.AirExtend, SampleTime(C.AirExtend, AT, true), .5f);
            return C.AirLow;
        }
        Blend = .18f;
        L.Add(C.AirIdle, SampleTime(C.AirIdle, At(B.AirTime), true), 1.f);
        return C.AirIdle;
    }
    case ERideMotion::Land:
    {
        // The landing's give, harder for a harder touch-down; a sketchy landing wobbles.
        const float F = FMath::Clamp(At(FMath::Max(B.LandAge, 0.f)) / LandHold, 0.f, 1.f);
        const float Sketchy = C.LandSketchy ? FMath::Clamp(B.Sketchy, 0.f, 1.f) : 0.f;
        Blend = .067f;
        const UAnimSequence* Key = C.LandLow;
        if (B.bLandedFromGrab && C.LandGrab)
        {
            L.Add(C.LandGrab, F * Len(C.LandGrab), 1.f - Sketchy);
            Key = C.LandGrab;
        }
        else
        {
            const float High = C.LandHigh ? FMath::Clamp((B.LandImpact - 250.f) / 500.f, 0.f, 1.f) : 0.f;
            L.Add(C.LandLow, F * Len(C.LandLow), (1.f - High) * (1.f - Sketchy));
            L.Add(C.LandHigh, F * Len(C.LandHigh), High * (1.f - Sketchy));
        }
        L.Add(C.LandSketchy, F * Len(C.LandSketchy), Sketchy);
        if (L.Num == 0) return Roll();
        return Key;
    }
    case ERideMotion::Grind:
    {
        UAnimSequence* Clip = C.Grinds[uint8(B.Grind)][B.bGrindFront ? 0 : 1];
        if (!Clip) return Roll();
        Blend = .1f;
        L.Add(Clip, SampleTime(Clip, Motion, true), 1.f);
        return Clip;
    }
    case ERideMotion::GetUp:
        Blend = .4f;
        return Roll();
    default:
        break;
    }
    // Rolling, after the way out of what came before.
    switch (B.PreviousMotion)
    {
    case ERideMotion::Push: if (Exit(C.PushOut, Motion)) return C.PushOut; break;
    case ERideMotion::Brake:
    {
        UAnimSequence* Out = B.bWasStill ? C.StandOut : C.BrakeOut;
        if (Exit(Out, Motion)) return Out;
        break;
    }
    case ERideMotion::Powerslide:
    {
        UAnimSequence* Out = C.SlideOut[B.bSlideFront ? 0 : 1];
        if (Exit(Out, Motion)) return Out;
        break;
    }
    case ERideMotion::NoseManual: if (Exit(C.NoseOut, Motion)) return C.NoseOut; break;
    case ERideMotion::Land: Blend = .25f; break;
    default: break;
    }
    return Roll();
}

// ---------------------------------------------------------------------------------------------------------------
// Evaluation.

void FRideAnimator::PlaceBoard(const FRideBoardPose& Board, TArray<FTransform>& Bones) const
{
    const FTransform& Deck = Bones[DeckIndex];
    for (int32 I = 0; I < 2; ++I)
    {
        // Trucks roll about the deck's length (the kingpin's give) as the rider turns.
        const FTransform Lean(FQuat(TruckAxis[I], FMath::DegreesToRadians(Board.TruckLean)));
        Bones[TruckIndex[I]] = Lean * TruckFromDeck[I] * Deck;
    }
    for (int32 I = 0; I < 4; ++I)
    {
        const FTransform Spin(FQuat(WheelAxis[I], FMath::DegreesToRadians(Board.WheelSpin)));
        Bones[WheelIndex[I]] = Spin * WheelFromTruck[I] * Bones[TruckIndex[I / 2]];
    }
}

void FRideAnimator::Evaluate(const FRideBodyPose& Body, const FRideBoardPose& Board, float Dt, TArray<FTransform>& Bones)
{
    if (!HasRig())
    {
        Bones = BoardReference;
        Bones[DeckIndex] = Board.Deck;
        PlaceBoard(Board, Bones);
        return;
    }
    // What plays: the caller's override, the pose the bail started from (held; the physical rider takes over), or
    // the session's choice.
    FRideAnimLayers Layers;
    float Blend = 0;
    const UAnimSequence* Key = nullptr;
    const bool bHold = Body.Motion == ERideMotion::Bail && !bFirst;
    if (bOverride) { Layers = Override; Key = Layers.Main(); Blend = OverrideBlend; }
    else if (bHold) { Layers = Last; Key = LastKey; }
    else Key = Choose(Body, Layers, Blend);
    float Inertialize = 0;
    const bool bCut = bCutNext;     // ClearOverride(0): no blend this once
    bCutNext = false;
    if (bCut) Inertialize = 0;
    else if (PendingBlend > 0) Inertialize = PendingBlend;
    else if (!bFirst && Blend > 0)
    {
        // A new clip, or the same move starting over (a second landing straight after the first).
        const bool bRestart = !bOverride && Body.Motion == LastMotion && Body.MotionTime + 1e-3f < LastMotionTime;
        if (Key != LastKey || bRestart) Inertialize = Blend;
    }
    PendingBlend = 0;
    const float KeyTime = TimeOf(Layers, Key);
    bool bCutBoard = false;
    if (Inertialize > 0 && Key && LastKey && Key != LastKey)
    {
        // A clip that ends with the board turned end for end (a hardflip or an inward heelflip catches it backwards)
        // hands the board to the next clip at once: it looks the same either way round, and a cross-fade would spin
        // it back in the air. The body still blends.
        const FQuat From = Track(LastKey, BoardRoot, LastKeyTime).GetRotation();
        const FQuat To = Track(Key, BoardRoot, KeyTime).GetRotation();
        bCutBoard = FMath::RadiansToDegrees(From.AngularDistance(To)) > TurnedBoard;
    }
    Run(Layers, Inertialize, Dt, bCutBoard);
    LastKey = Key; LastKeyTime = KeyTime; LastMotion = Body.Motion; LastMotionTime = Body.MotionTime;

    const TArray<FTransform>& Pose = Mesh->GetComponentSpaceTransforms();
    if (Pose.Num() != Names.Num())
    {
        Bones = Reference;
        return;
    }
    // Place the clips' root space on the session's deck: as authored under the root (Lock 0), or moved so the clip's
    // board lies exactly on the deck (Lock 1).
    const float Target = bHold ? Lock : FMath::Clamp(Layers.Lock, 0.f, 1.f);
    Lock = bFirst || bCut ? Target : FMath::FInterpConstantTo(Lock, Target, Dt, Target < Lock ? 30.f : 10.f);
    FTransform Place;
    Place.Blend(Board.Deck, Pose[DeckIndex].Inverse() * Board.Deck, Lock);
    Bones.SetNum(Pose.Num(), EAllowShrinking::No);
    for (int32 I = 0; I < Pose.Num(); ++I) Bones[I] = Pose[I] * Place;
    // On the ground, a board the clip tilts (a pop's tail, a manual, a 5-0) keeps its lowest wheel or tip on the
    // ground: the whole pose rises by what would sink.
    const bool bSlide = Body.Motion == ERideMotion::Grind && (Body.Grind == ERideGrind::Boardslide || Body.Grind == ERideGrind::Lipslide);
    if (OnGround(Body.Motion) && !bSlide)
    {
        const FTransform& Deck = Bones[DeckIndex];
        float Lowest = TNumericLimits<float>::Max();
        for (const FVector& Tip : DeckTips) Lowest = FMath::Min(Lowest, float(Deck.TransformPosition(Tip).Z));
        for (const FVector& Wheel : WheelInDeck) Lowest = FMath::Min(Lowest, float(Deck.TransformPosition(Wheel).Z) - WheelRadius);
        Lift = FMath::Max(0.f, -Board.DeckHeight - Lowest);
    }
    else if (!bHold) Lift = FMath::Max(0.f, Lift - LiftDecay * Dt);
    if (Lift > 0) for (FTransform& Bone : Bones) Bone.AddToTranslation(FVector(0, 0, Lift));
    PlaceBoard(Board, Bones);
    bFirst = false;
}

void FRideAnimator::EvaluateFree(float Dt, TArray<FTransform>& Bones)
{
    if (!HasRig())
    {
        Bones = BoardReference;
        return;
    }
    FRideAnimLayers Layers = bOverride ? Override : Last;
    const UAnimSequence* Key = Layers.Main();
    float Inertialize = bCutNext ? 0.f : PendingBlend;
    if (Inertialize <= 0 && !bCutNext && !bFirst && Key != LastKey && bOverride) Inertialize = OverrideBlend;
    PendingBlend = 0; bCutNext = false;
    Run(Layers, Inertialize, Dt);
    LastKey = Key; LastKeyTime = TimeOf(Layers, Key);
    Lock = FMath::Clamp(Layers.Lock, 0.f, 1.f); Lift = 0;
    const TArray<FTransform>& Pose = Mesh->GetComponentSpaceTransforms();
    Bones = Pose.Num() == Names.Num() ? Pose : Reference;
    bFirst = false;
}
