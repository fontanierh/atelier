#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Hippodrome.generated.h"

class UAnimSequence;
class USkeletalMeshComponent;
class UStaticMeshComponent;

/**
 * The Hidamari Hippodrome's oval (world/regions/hippodrome/layout.py, docs/HIPPODROME.md). Distances are metres along
 * the centre line from the finish post in the running direction (counter-clockwise seen from above); an offset is
 * metres outwards from the centre line. Points come back in Unreal cm on the flat platform.
 */
struct FHippodromeCourse
{
    FVector2D Origin = FVector2D(600., 525.);   // Blender metres
    double Half = 60., Radius = 50., Width = 14., Lap = 0., FinishX = 600., Z = 0., GateS = 0.;
    /** layout.centre: the point at S, Offset metres outwards, and the running yaw (Unreal degrees). */
    FVector At(double S, double Offset, float* Yaw = nullptr) const;
    /** layout.curvature_scale: how much further a runner Offset metres outwards travels per metre of centre line. */
    double CurvatureScale(double S, double Offset) const;
    bool InTurn(double S) const;
    /** Blender metres (x east, y north) to Unreal cm on the platform. */
    FVector World(double X, double Y, double Up = 0.) const { return FVector(X * 100., -Y * 100., (Z + Up) * 100.); }
};

/** A horse, a rider or the race master from the horse roster (Content/Data/horses/roster.json, import_horses.py). */
struct FHorseSpec
{
    FString Name, Label, Kind, Coat;
    FSoftObjectPath Mesh;
    float MeshYaw = -90.f, Scale = 1.f, HeightCm = 0.f;
    TMap<FName, float> SpeedsCm;            // walk, trot, canter, run, sprint (cm/s at the clip's rate 1)
    TMap<FName, FSoftObjectPath> Clips;
    TMap<FName, float> Lengths;
    TMap<FName, FName> Roles;
    FName Role(FName R) const { const FName* C = Roles.Find(R); return C ? *C : NAME_None; }
    static const TMap<FString, FHorseSpec>& All();
    static const FHorseSpec* Find(const FString& Name);
    /** The player in the saddle: Cairo (RiderCairo, cairo_rider.py) when imported, else Link. */
    static FString PlayerRider();
};

/**
 * A horse with its rider, or a person on foot: skeletal meshes playing roster clips directly (no AnimBP), as
 * ABotwCreature does. The rider sits on the horse's Saddle_Root bone (its root on the saddle, as the BOTW rigs share
 * it) and plays the matching Horse_ clip; a gait restarts both clips together and keeps their cycles in step.
 */
UCLASS()
class YORIMICHI_API AHippodromeFigure : public AActor
{
    GENERATED_BODY()
public:
    AHippodromeFigure();
    /** Body is a horse (or a person on foot); Rider may be empty. Ground is the point under it (cm). */
    static AHippodromeFigure* Spawn(UWorld* World, const FString& Body, const FString& Rider, const FVector& Ground, float Yaw);
    /** Loop a role on the horse and the rider together (the rider's role, else its run), Rate on the horse's clip.
     *  The clips restart only when they change; the rate always follows. */
    void Gait(FName HorseRole, FName RiderRole, float Rate);
    /** One clip (role or clip name) on the horse or the rider alone; returns its length in seconds at Rate. */
    float PlayBody(FName RoleOrClip, bool bLoop, float Rate = 1.f);
    float PlayRider(FName RoleOrClip, bool bLoop, float Rate = 1.f);
    /** A one-off on the rider (the spur's kick): Gait leaves the rider alone until it ends, then puts it back in step. */
    float PlayRiderOnce(FName RoleOrClip, float Rate = 1.f);
    bool RiderHas(FName Role) const;
    const FHorseSpec& GetBody() const { return BodySpec; }
    const FHorseSpec& GetRider() const { return RiderSpec; }
    bool HasRider() const { return bHasRider; }
    FName BodyClip() const { return BodyCurrent; }
    USkeletalMeshComponent* GetBodyMesh() const { return Body; }
    USkeletalMeshComponent* GetRiderMesh() const { return Rider; }

private:
    UPROPERTY() TObjectPtr<USceneComponent> Root;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Body;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Rider;
    UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> BodyClips;
    UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> RiderClips;
    FHorseSpec BodySpec, RiderSpec;
    bool bHasRider = false;
    FName BodyCurrent, RiderCurrent;
    double RiderBusyUntil = 0.;
    void Initialize(const FHorseSpec& BodyData, const FHorseSpec* RiderData);
    static FName Resolve(const FHorseSpec& Spec, FName RoleOrClip);
    static void LoadClips(const FHorseSpec& Spec, TMap<FName, TObjectPtr<UAnimSequence>>& Out);
};

/**
 * The Hidamari Hippodrome (docs/HIPPODROME.md): the racecourse on the slope north of the city. Places the imported
 * meshes (Content/Data/hippodrome/hippodrome.json, import_hippodrome.py) round the course origin, stands Hudson the race
 * master by the grandstand and starts the race manager (AHorseRace).
 */
UCLASS()
class YORIMICHI_API AHippodrome : public AActor
{
    GENERATED_BODY()
public:
    bool bGameplayReady = false;
    AHippodrome();
    /** The hippodrome described by Path (hippodrome.json); null when the file or its meshes are missing. */
    static AHippodrome* Spawn(UWorld* World, const FString& Path);
    static AHippodrome* Find(const UObject* WorldContext);

    FHippodromeCourse Course;
    FVector MasterGround = FVector::ZeroVector, ReturnGround = FVector::ZeroVector;
    float MasterYaw = 0.f, ReturnYaw = 0.f, GateYaw = 0.f;
    FVector GateCentre = FVector::ZeroVector;
    AHippodromeFigure* GetMaster() const { return Master.Get(); }
    /** The starting gate stands across the back straight for the start; it is taken off once the field is away. */
    void SetGateOnTrack(bool bOn);

private:
    UPROPERTY() TObjectPtr<USceneComponent> Root;
    TWeakObjectPtr<AHippodromeFigure> Master;
    TWeakObjectPtr<UStaticMeshComponent> GateMesh;
    bool bGateOn = true;
    bool Initialize(const FString& Path);
};
