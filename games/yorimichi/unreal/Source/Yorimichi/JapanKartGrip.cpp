#include "JapanKartGrip.h"
#include "WandererCharacter.h"
#include "PlayableCharacter.h"
#include "DrivingComponent.h"
#include "AtelierData.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"

namespace
{
// JSON matrices are column-major Blender metres. Reflect both basis axes and translation
// into UE centimetres once; UE's FMatrix stores basis vectors in rows.
bool ReadFrame(const FJsonObject& Object, const FString& Name, FTransform& Out)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!Object.TryGetArrayField(Name, Values) || Values->Num() != 16) return false;
    double V[16];
    for (int I = 0; I < 16; ++I)
        if (!(*Values)[I]->TryGetNumber(V[I]) || !FMath::IsFinite(V[I])) return false;
    if (FMath::Abs(V[3]) > 1.e-5 || FMath::Abs(V[7]) > 1.e-5 || FMath::Abs(V[11]) > 1.e-5 || FMath::Abs(V[15]-1.) > 1.e-5) return false;
    constexpr double H[3] = {1., -1., 1.};
    FMatrix Matrix = FMatrix::Identity;
    for (int C = 0; C < 3; ++C) for (int R = 0; R < 3; ++R) Matrix.M[C][R] = V[C*4+R] * H[C] * H[R];
    for (int R = 0; R < 3; ++R) Matrix.M[3][R] = V[12+R] * H[R] * 100.;
    Out = FTransform(Matrix);
    return !Out.ContainsNaN() && Out.GetScale3D().GetMin() > .01;
}
}

void ReadKartGrip(AWandererCharacter* Pawn, UDrivingComponent* Car)
{
    Car->SetAuthoredGrips({});
    const FPlayableCharacter* Character = FPlayableCharacter::Find(FPlayableCharacter::NameOf(Pawn));
    const USkeletalMeshComponent* Body = Pawn->GetMesh();
    const USkeletalMesh* Mesh = Body ? Body->GetSkeletalMeshAsset() : nullptr;
    if (!Character || !Mesh) { UE_LOG(LogTemp, Warning, TEXT("Kart grip has no playable character or skeletal mesh")); return; }
    auto Reject = [&](const FString& Reason) { UE_LOG(LogTemp, Error, TEXT("Kart grip %s rejected: %s"), *Character->Id, *Reason); };
    const TSharedPtr<FJsonObject> Data = AtelierReadJson(AtelierDataPath(TEXT("kart/grips/") + Character->Id + TEXT(".json")));
    if (!Data) { Reject(TEXT("profile is missing; save and import the grip")); return; }
    const TSharedPtr<FJsonObject>* Hands = nullptr;
    const TSharedPtr<FJsonObject>* Bind = nullptr;
    FString Id;
    double Schema = 0., Scale = 0.;
    double ExpectedScale = 0., ScaleTolerance = 1e-4, ReceiptSchema = 0.;
    const TSharedPtr<FJsonObject> Receipt = AtelierReadJson(AtelierDataPath(TEXT("kart/prepared-models.json")));
    const TSharedPtr<FJsonObject>* Models = nullptr;
    const TSharedPtr<FJsonObject>* Entry = nullptr;
    if (!Receipt || !Receipt->TryGetNumberField(TEXT("schema"), ReceiptSchema) || ReceiptSchema != 1. ||
        !Receipt->TryGetObjectField(TEXT("models"), Models) || !(*Models)->TryGetObjectField(Character->Id, Entry) ||
        !(*Entry)->TryGetNumberField(TEXT("scale"), ExpectedScale) || !FMath::IsFinite(ExpectedScale) || ExpectedScale <= 0.)
    {
        Reject(TEXT("prepared-model receipt is missing or does not name this character"));
        return;
    }
    if (!Data->TryGetNumberField(TEXT("schema"), Schema) || Schema != 1. ||
        !Data->TryGetStringField(TEXT("character"), Id) || Id != Character->Id ||
        !Data->TryGetNumberField(TEXT("scale"), Scale) || !FMath::IsFinite(Scale) ||
        FMath::Abs(Scale - ExpectedScale) > ScaleTolerance ||
        !Data->TryGetObjectField(TEXT("hands"), Hands) || !Data->TryGetObjectField(TEXT("bind_world"), Bind))
    {
        UE_LOG(LogTemp, Error, TEXT("Kart grip is invalid or stale for %s"), *Character->Id); return;
    }
    const double LiveScale = Car->GetKartScale();
    const double RelativeScaleGap = FMath::Abs(LiveScale / ExpectedScale - 1.);
    UE_LOG(LogTemp, Log, TEXT("Kart grip %s scale: live %.6f prepared %.6f gap %.3f%% mesh %s"),
        *Character->Id, LiveScale, ExpectedScale, RelativeScaleGap * 100., *Mesh->GetPathName());
    if (RelativeScaleGap > .01)
        UE_LOG(LogTemp, Warning, TEXT("Kart grip %s live scale differs from the authored fit by more than 1%%; inspect reach at playtest"), *Character->Id);
    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    auto Reference = [&Ref](int Index)
    {
        FTransform Result = FTransform::Identity;
        for (int I = Index; I != INDEX_NONE; I = Ref.GetParentIndex(I)) Result = Result * Ref.GetRefBonePose()[I];
        return Result;
    };
    TMap<FName, FTransform> Frames;
    float WorstBind = 0.f;
    FString WorstBindName;
    for (const TCHAR* Side : {TEXT("L"), TEXT("R")})
    {
        const TSharedPtr<FJsonObject>* Hand = nullptr;
        if (!(*Hands)->TryGetObjectField(Side, Hand)) { Reject(TEXT("hand side is missing")); return; }
        const FString HandName = FString::Printf(TEXT("hand_%s"), Side);
        const int HandIndex = Ref.FindBoneIndex(Pawn->GetSkateBone(FName(*HandName)));
        FTransform BlenderHand;
        if (HandIndex == INDEX_NONE || !ReadFrame(**Bind, HandName, BlenderHand)) { Reject(TEXT("hand bind frame is missing")); return; }
        const FVector UEHand = Reference(HandIndex).GetLocation();
        TArray<FString> Names = {FString::Printf(TEXT("hand_%s"), Side)};
        for (int F = 0; F < 5; ++F) for (int K = 0; K < 3; ++K)
        {
            const TCHAR* const Finger[] = {TEXT("finger_"), TEXT("finger_tip_"), TEXT("finger_end_")};
            const TCHAR* const Thumb[] = {TEXT("thumb_"), TEXT("thumb_tip_"), TEXT("thumb_end_")};
            Names.Add(F < 4 ? FString::Printf(TEXT("%s%d_%s"), Finger[K], F, Side) : FString::Printf(TEXT("%s%s"), Thumb[K], Side));
        }
        for (const FString& Name : Names)
        {
            const FName Bone = Pawn->GetSkateBone(FName(*Name));
            const int Index = Ref.FindBoneIndex(Bone);
            FTransform Local, BlenderBind;
            if (Index == INDEX_NONE || !ReadFrame(**Hand, Name, Local) || !ReadFrame(**Bind, Name, BlenderBind))
            {
                UE_LOG(LogTemp, Error, TEXT("Kart grip missing bone/frame %s"), *Name); return;
            }
            const FTransform UEReference = Reference(Index);
            // The prepared offsets are native-size cm. Rotate only; the mesh component's
            // relative scale is presentation of a character, not a grip-axis transform.
            const FVector ImportedOffset = Body->GetRelativeRotation().RotateVector(UEReference.GetLocation()-UEHand);
            const FVector PreparedOffset = BlenderBind.GetLocation()-BlenderHand.GetLocation();
            // A 3 mm allowance covers FBX float/export rounding, not a different rest pose or rig.
            const float BindDistance = FVector::Distance(ImportedOffset, PreparedOffset);
            if (BindDistance > WorstBind) { WorstBind = BindDistance; WorstBindName = Name; }
            if (BindDistance > .3)
            {
                Reject(FString::Printf(TEXT("prepared/imported bind differs at %s by %.3f cm"), *Name,
                                      BindDistance)); return;
            }
            // Blender's prepared world is actor-forward. FBX may use different bone axes and a
            // mesh-facing rotation: calibrate those axes from both bind skeletons, never guessed Euler angles.
            const FQuat Correction = BlenderBind.GetRotation().Inverse() * Body->GetRelativeRotation().Quaternion() * UEReference.GetRotation();
            Local.SetRotation((Local.GetRotation() * Correction).GetNormalized());
            Frames.Add(Bone, Local);
        }
    }
    UE_LOG(LogTemp, Display, TEXT("Kart grip %s imported bind margin: %.3f cm worst (%s)"),
           *Character->Id, WorstBind, *WorstBindName);
    const TSharedPtr<FJsonObject>* Poles = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Left = nullptr;
    if (!Data->TryGetObjectField(TEXT("arm_poles"), Poles) || !(*Poles)->TryGetArrayField(TEXT("L"), Left) || Left->Num() != 3)
    { Reject(TEXT("elbow guide is missing")); return; }
    double Pole[3];
    for (int I = 0; I < 3; ++I) if (!(*Left)[I]->TryGetNumber(Pole[I]) || !FMath::IsFinite(Pole[I]))
    { Reject(TEXT("elbow guide is invalid")); return; }
    double Lean = 0., Height = 0., Tilt = 0.;
    if (!Data->TryGetNumberField(TEXT("shoulder_lean_degrees"), Lean) || !FMath::IsFinite(Lean) || Lean < -15. || Lean > 45. ||
        !Data->TryGetNumberField(TEXT("wheel_height_offset"), Height) || !FMath::IsFinite(Height) || FMath::Abs(Height) > .25)
    { Reject(TEXT("shoulder lean or wheel height is invalid")); return; }
    if (!Data->TryGetNumberField(TEXT("wheel_tilt_offset_degrees"), Tilt) || !FMath::IsFinite(Tilt) ||
        Car->GetSteeringTilt()+Tilt < 15.-1e-5 || Car->GetSteeringTilt()+Tilt > 75.+1e-5)
    { Reject(TEXT("wheel angle must be between 15 and 75 degrees")); return; }
    if (!Car->SetAuthoredFit(Lean, Height * 100., Tilt)) { Reject(TEXT("column fit could not be applied")); return; }
    Car->SetAuthoredElbow(FVector(Pole[0], -Pole[1], Pole[2]) * 100.);
    Car->SetAuthoredGrips(MoveTemp(Frames));
}
