#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "SprintStamina.h"
#include "AtelierFX.h"
#include "SkateRider.h"
#include "WandererCharacter.generated.h"

class UWandererDefinition;
class USpringArmComponent;
class UCameraComponent;
class UInputAction;
class UInputMappingContext;
class AJapanWorld;
class UJapanPreferences;
class USkateboardComponent;
class USkateComponent;
class USailboatComponent;
class FJsonObject;
class FJapanStreamingInput;
class UJapanMap;
class UJapanFootstepComponent;
class UWandererSwordComponent;
class ASwordDummy;

/** A skinned adventurer driven by CharacterMovement and the native animation graph. */
UCLASS()
class YORIMICHI_API AWandererCharacter : public ACharacter, public IAtelierFXTarget, public ISkateRider
{
    GENERATED_BODY()
public:
    AWandererCharacter(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    virtual void Landed(const FHitResult& Hit) override;
    void EnterWorld(AJapanWorld* World);
    UWandererDefinition* GetDefinition() const { return Definition; }
    FName GetAnimationAction() const { return AnimationAction; }
    /** The clip that shows the current action. With the sword out, jumps, falls, landings, dashes, the double jump and the
     *  roll and the knock-down play their armed versions ("Sword" + action, game-r16): the clip's own arm movement with the
     *  sword in the hand. */
    FName GetAnimationClip() const;
    uint32 GetActionSerial() const { return ActionSerial; }
    float GetActionBlendTime() const { return ActionBlendTime; }
    float GetActionSourceStartTime() const { return ActionSourceStartTime; }
    float GetActionPlayRate() const { return ActionPlayRate; }
    float GetActionTime() const { return ActionTime; }
    float GetActionSourceTime() const { return ActionSourceStartTime+ActionTime*ActionPlayRate; }
    bool HasMovementIntent() const { return !MoveIntent.IsNearlyZero(); }
    bool DoesActionLoop() const { return bActionLoops; }
    bool IsReady() const { return bReady; }
    bool IsMouseReleased() const { return bMouseReleased; }
    USkateboardComponent* GetSkateboard() const { return Skateboard; }
    /** skate.-style skateboarding (docs/SKATE.md; the platform's Skate plugin). */
    USkateComponent* GetSkate() const { return SkateRide; }
    // ISkateRider: skate roles from the definition's SkateActions, other roles from its Actions; the sword is sheathed
    // and any action stopped on mounting; the menu and the map take the board's input.
    virtual UAnimSequence* FindSkateClip(FName Role) const override;
    virtual void PrepareToSkate() override;
    virtual bool IsSkateInputBlocked() const override;
    virtual bool IsSkateMouseFree() const override { return bMouseReleased; }
    virtual float GetSkateMouseSensitivity() const override { return MouseSensitivity; }
    virtual FString GetSkateContactsFile() const override { return TEXT("characters/warm-original/skate-build.json"); }
    FVector2D GetMoveIntent() const { return MoveIntent; }
    float GetMouseSensitivity() const { return MouseSensitivity; }
    UJapanFootstepComponent* GetFootsteps() const { return Footsteps; }
    UWandererSwordComponent* GetSword() const { return Sword; }
    ASwordDummy* GetSwordDummy() const { return SwordDummy; }
    USailboatComponent* GetSailboat() const { return Sailboat; }
    UJapanPreferences* GetPreferences() const { return Preferences; }
    UJapanMap* GetMap() const { return Map; }
    /** Travel to a world position (Unreal cm) facing Yaw: stows the board and sailboat, clears momentum, lands on the ground actually built there. */
    bool TravelTo(FVector Location, float Yaw, const TCHAR* Reason = TEXT("map"));
    void SetMenuOpen(bool bOpen);
    void SetStaminaRings(int Rings) { Stamina.SetCapacity(Rings); }
    const FSprintStamina& GetStamina() const { return Stamina; }
    float GetSprintSpeed() const;
    void ApplyCameraPreferences(float Sensitivity, float Distance, float FieldOfView);
    /** Combat feedback: camera trauma (0..1, decays; the shake grows with its square) and the red damage flash the HUD draws. */
    virtual void AddCameraShake(float Trauma) override { ShakeTrauma = FMath::Min(1.f, ShakeTrauma + Trauma); }
    void FlashDamage(float Amount) { DamageFlash = FMath::Max(DamageFlash, Amount); }
    float GetDamageFlash() const { return DamageFlash; }
    /** The current shake as a camera-space offset (cm) and rotation (degrees). */
    void SampleShake(FVector& Offset, FRotator& Rotation) const;
    UCameraComponent* GetFollowCamera() const { return FollowCamera; }
    USpringArmComponent* GetCameraArm() const { return CameraArm; }
    /** -fightfilm: the scripted, filmed fight against the fox hunter (JapanFightFilm.cpp). */
    TSharedPtr<struct FFightFilm> FightFilm;
    void Review_Move(FVector2D Intent) { MoveIntent = Intent; }
    /** Live bridge: hold a movement intent (camera-relative, like the stick) at a gait: 0 walk, 1 run, 2 sprint. Input replaces it. */
    /** Live bridge: press a button through the real input handler: "jump", "jump_release", "roll", "crouch". */
    bool Live_Press(FName Button);
    /** Live bridge: leave the camera where it is (no automatic follow) for Seconds. */
    void Live_HoldCamera(float Seconds) { MegaCameraGrace = Seconds; }
    void Live_Drive(FVector2D Intent, int32 Gait) { MoveIntent = Intent; bWalk = Gait == 0; bJog = false; bSprintHeld = Gait == 2; }
    void Review_Dodge();

protected:
    FString DefinitionAssetPath = TEXT("/Game/Wanderer/DA_Wanderer.DA_Wanderer");
    // Gameplay tuning; the definition keeps the clip's authored stride speed.
    float SprintSpeedMultiplier = 1.f;

private:
    friend class FJapanStreamingInput;
    friend class UWandererSwordComponent;
    friend class AZeppelinService;
    float MegaCameraGrace=0.f, SkateCameraBlend=0.f, PreferredArmLength=0.f;
    bool bRemountSkate=false;
    TSharedPtr<FJapanStreamingInput> PhoneInput;
    UPROPERTY() TObjectPtr<USkateboardComponent> Skateboard;
    UPROPERTY() TObjectPtr<USkateComponent> SkateRide;
    UPROPERTY() TObjectPtr<USailboatComponent> Sailboat;
    UPROPERTY() TObjectPtr<UJapanFootstepComponent> Footsteps;
    UPROPERTY() TObjectPtr<UWandererSwordComponent> Sword;
    UPROPERTY() TObjectPtr<ASwordDummy> SwordDummy;
    // -swordqa: scripted combat timing/state review; -sworddummy: a training post in front of the spawn
    bool bSwordReview=false; float SwordReviewTime=0.f; int32 SwordReviewStep=-1; TArray<FString> SwordErrors; FString SwordTelemetry=TEXT("time,state,action,source_time,locked,armed,strikes,dummy_hits,hits_taken,parries,x,y,z,vz,falling,yaw,tip_x,tip_y,tip_z\n");
    void AdvanceSwordReview(float Dt);
    void SpawnSwordDummy();
    UPROPERTY() TObjectPtr<UWandererDefinition> Definition;
    UPROPERTY() TObjectPtr<USpringArmComponent> CameraArm;
    UPROPERTY() TObjectPtr<UCameraComponent> FollowCamera;
    UPROPERTY() TObjectPtr<UInputMappingContext> Mapping;
    UPROPERTY() TMap<FName,TObjectPtr<UInputAction>> Inputs;
    UPROPERTY() TObjectPtr<UJapanPreferences> Preferences;
    UPROPERTY() TObjectPtr<UJapanMap> Map;
    UPROPERTY() TObjectPtr<AJapanWorld> Landscape;
    FVector2D MoveIntent = FVector2D::ZeroVector;
    FName AnimationAction;
    uint32 ActionSerial = 0;
    float ActionBlendTime = .16f, ActionTime = 0.f, ActionDuration = 0.f;
    float ActionSourceStartTime = 0.f, ActionPlayRate = 1.f;
    FSprintStamina Stamina;
    bool bSprintHeld=false;
    float MouseSensitivity = .4f, PreferredFOV = 70.f, ReadyTime = 0.f;
    float ShakeTrauma = 0.f, ShakeClock = 0.f, DamageFlash = 0.f;
    bool bActionLoops = false, bJog = false, bWalk = false;
    bool bReady = false, bMouseReleased = false, bMenuOpen = false;
    bool bPendingTakeoff = false, bGroundJumped = false, bAirJumpUsed = false;
    float JumpBuffer = 0.f, SinceGrounded = 0.f, FallSpeed = 0.f;
    FVector DodgeDirection = FVector::ZeroVector;
    bool bAirDashUsed = false;
    float DashCooldown = 0.f;
    float RollCooldown = 0.f;
    float RollBuffer = 0.f;
    bool bReview = false, bWorldReview = false, bFixedView = false, bRecordReview = false;
    int32 ReviewFrame = 0;
    int32 InputReviewStage = 0;
    float InputReviewPitch = 0, UpPitchDelta = 0, DownPitchDelta = 0;
    FString ReviewTelemetry = TEXT("time,step,speed,falling,crouched,pitch,foot_l_x,foot_l_y,foot_l_z,foot_r_x,foot_r_y,foot_r_z,capsule_half_height,mesh_offset_z\n");
    FVector ReviewForward = FVector::ForwardVector;
    float ReviewTime = 0.f;
    int32 ReviewStep = -1;
    FString ReviewDirectory;
    FString BenchmarkView, BenchmarkDirectory;
    FString BenchmarkCompareBefore, BenchmarkCompareAfter;
    int32 BenchmarkComparePhase=0, BenchmarkCompareScreenshot=-1;
    float BenchmarkTime = 0.f, BenchmarkSeconds = 25.f;
    bool bBenchmarkCapturing = false, bBenchmarkFinished = false;
    void AdvanceBenchmark(float Dt);
    void AdvanceWarmReview(float Dt);
    bool bWarmReview=false, WarmInverted=false;
    float WarmTime=0.f, WarmMaxWaist=0.f, WarmMaxHair=0.f;
    FVector WarmOrigin=FVector::ZeroVector;
    FVector WarmRollOrigin=FVector::ZeroVector;
    bool WarmRollInverted=false;
    float WarmRollEntrySpeed=0.f, WarmRollMinSpeed=0.f;
    float WarmRollEndDistance=0.f;
    bool WarmRollWasAirborne=false;
    int32 WarmRollGroundContacts=0;
    float WarmRollMinEntrySpeed=0.f, WarmRollEndSpeed=0.f, WarmRollElapsed=0.f;
    uint32 WarmRollChainSerial=0;
    int32 WarmRollChainCount=0, WarmRollChainTucks=0;
    float WarmRollChainSecondTime=-1.f;
    FVector WarmAirVelocity=FVector::ZeroVector, WarmAirOrigin=FVector::ZeroVector;
    float WarmAirLaunchTime=-1.f;
    UPROPERTY() TObjectPtr<AActor> WarmRollObstacle;
    TArray<FString> WarmErrors;
    FString WarmTelemetry=TEXT("time,action,speed,height,falling,air_jump,air_dash,pelvis_up,waist_curve\n");
    void AdvanceGroundContactReview(float Dt);
    void RecordGroundContactPose();
    bool bGroundContactReview=false;
    float GroundReviewTime=0.f;
    int32 GroundReviewStage=-1;
    FVector GroundReviewAnchor=FVector::ZeroVector;
    FString GroundReviewTelemetry=TEXT("stage,time,side,point,gap_cm,falling\n");
    void AdvanceMegaReview(float Dt);
    void AdvanceSailboatReview(float Dt);
    // scripted demos of the south-west detour: a ground run from spawn to the temple, and a bird's-eye flyover
    void AdvanceSouthwestDemo(float Dt);
    void AdvanceSouthwestFly(float Dt);
    bool LoadSouthwestData();
    bool FollowTo(const FVector& Target, float Dt, float Tolerance = 110.f);
    void RecordFrame();
    bool bSouthwestDemo=false, bSouthwestFly=false, bCinematic=false; float DemoTime=0.f, PhaseTime=0.f; int32 DemoPhase=-1, DemoIndex=0, DemoFrame=0;
    TArray<FVector> DemoLane, DemoRamp, DemoCrossing; FVector StuckAnchor=FVector::ZeroVector; float StuckTime=0.f; FVector DemoLanding=FVector::ZeroVector, DemoStand=FVector::ZeroVector, DemoSide=FVector::ZeroVector, DemoLaunch=FVector::ZeroVector, DemoSummit=FVector::ZeroVector;
public:
    bool IsCinematic() const { return bCinematic; }
    class AZeppelinService* GetZeppelin() const;
    bool IsZeppelinPassenger() const;
private:
    bool bSailboatReview=false; float SailboatReviewTime=0.f; int32 SailboatReviewStep=-1; FString SailboatTelemetry;
    float SailboatReviewElapsed=0.f, SailboatReviewYaw=0.f;
    bool bSailboatReviewEntered=false, bSailboatReviewShot=false;
    int32 SailboatReviewChecks=0;
    FVector SailboatReviewAnchor=FVector::ZeroVector, SailboatReviewLaunch=FVector::ZeroVector;
    float SailboatReviewLaunchYaw=0.f;
    FTransform SailboatReviewInitialMesh;
    FVector SailboatReviewRecoveryTarget=FVector::ZeroVector;
    bool bSailboatReviewObservedFall=false;
    TArray<FString> SailboatReviewErrors;
    UPROPERTY() TObjectPtr<AActor> SailboatReviewObstacle;
    void SaveMegaFilmFrame(int32 Width,int32 Height,const TArray<FColor>& Pixels);
    int32 MegaFilmFrame=0,MegaFilmPending=-1;
    bool bMegaReview=false;
    float MegaReviewTime=0;
    FString MegaTelemetry=TEXT("time,phase,section,s,speed,x,y,z,gap_landings,vert_landings,clip,head_distance,foot_error,grip_error\n");
    // Opt-in cinematic capture. Does not run in ordinary play.
    FVector LastSafeCoastLocation=FVector::ZeroVector;
    bool bHasSafeCoastLocation=false;
    FVector LastSafeCityLocation=FVector::ZeroVector;
    bool bHasSafeCityLocation=false;
    FString BuildingReviewSpecPath;
    TSharedPtr<struct FBuildingReviewState> BuildingReview;
    void AdvanceBuildingReview(float Dt);
    FString TrailerSpecPath;
    TSharedPtr<FJsonObject> TrailerSpec;
    int32 TrailerFrame = -180;
    float TrailerHeading = 0.f;
    FString TrailerTelemetry = TEXT("frame,speed,x,y,z,falling,skating,clip,camera_x,camera_y,camera_z,action,sprinting,sailing,sail,zeppelin_stage,propeller_angle\n");
    void AdvanceTrailer(float Dt);
    void SaveTrailerFilmFrame(int32 Width,int32 Height,const TArray<FColor>& Pixels);
    int32 TrailerPending=-1;
    TSharedPtr<struct FVillageJourney> VillageJourney;
    void AdvanceVillageJourney(float Dt);
    void SaveJourneyFrame(int32 Width,int32 Height,const TArray<FColor>& Pixels);
    void EndVillageJourney();
    void BuildInput();
    void Move(const FInputActionValue& Value);
    void MouseLook(const FInputActionValue& Value);
    void StickLook(const FInputActionValue& Value);
    void Jog(const FInputActionValue& Value);
    void Sprint(const FInputActionValue& Value);
    void Walk(const FInputActionValue& Value);
    void RequestJump(const FInputActionValue& Value);
    void Dash(const FInputActionValue& Value);
    void ReleaseJump(const FInputActionValue& Value);
    void ToggleSkateboard(const FInputActionValue& Value);
    void ReturnToSpawn();
    void ToggleSailboat(const FInputActionValue& Value);
    void ToggleCrouch(const FInputActionValue& Value);
    void Dodge(const FInputActionValue& Value);
    void Wave(const FInputActionValue& Value);
    void Interact(const FInputActionValue& Value);
    void AttackPressed(const FInputActionValue& Value);
    void AttackReleased(const FInputActionValue& Value);
    void ParryPressed(const FInputActionValue& Value);
    void ToggleWeapon(const FInputActionValue& Value);
    /** Slow the zeppelin ride down or speed it up while aboard; ignored on foot. */
    void FlightSlower(const FInputActionValue& Value);
    void FlightFaster(const FInputActionValue& Value);
    void ToggleMenu(const FInputActionValue& Value);
    void ToggleMap(const FInputActionValue& Value);
    // -mapqa: travel to every map zone in turn, screenshot each, then the open map; writes map_qa.json
    bool bMapReview = false; float MapReviewTime = 0.f; int32 MapReviewStep = -1; FString MapTelemetry;
    void AdvanceMapReview(float Dt);
    void ToggleMouse(const FInputActionValue& Value);
    void Screenshot(const FInputActionValue& Value);
    bool CanAct() const;
    bool StandForAction();
    bool MovementLocked() const;
    bool IsRollRecovering() const;
    void SetAction(FName Action, bool bLoop = false, float BlendSeconds = .16f, bool bRestart = false);
    void SetMouseReleased(bool bReleased);
    void AdvanceAction(float Dt);
    void AdvanceReview(float Dt);
    void AdvanceLocomotionReview(float Dt);
    void RecordLocomotionPose();
    bool bLocomotionReview = false;
    bool bJumpReview = false;
    void AdvanceJumpReview(float Dt);
    float JumpReviewTime=0.f, JumpReviewSinglePeak=0.f, JumpReviewDoublePeak=0.f;
    float JumpReviewMinSpeed=100000.f;
    FVector JumpReviewOrigin=FVector::ZeroVector;
    FString JumpReviewTelemetry=TEXT("time,speed,z,vz,falling,air_used,action,root_up_z\n");
    TArray<FString> JumpReviewErrors;
    bool bJumpReviewInverted=false;
    FString LocomotionTelemetry = TEXT("time,speed,walk,jog,head_z,pelvis_z,foot_l_x,foot_l_y,foot_l_z,foot_r_x,foot_r_y,foot_r_z\n");
    void AdvanceSkateReview(float Dt);
    void RecordSkatePose();
    float GetRoadSteering();
    TArray<FVector> SkateReviewRoad;
    // Review routes are open paths, not loops: the scripted rider patrols them so a long traversal
    // keeps moving instead of parking on the last waypoint. Progress is logged as evidence.
    int32 SkateReviewDirection = 1;
    int32 SkateReviewIndex = 0;
    int32 SkateReviewTurns = 0;
    int32 SkateReviewRecoveries = 0;
    FVector SkateReviewStuckAt = FVector::ZeroVector;
    double SkateReviewStuckSince = -1.;
    bool bSkateReview = false, bSkateVideo = false, bOllieVideo = false, bRearSkateVideo = false, bSkateStanceReview = false;
    float SkateReviewTime = 0.f;
    FString SkateTelemetry = TEXT("time,clip,pose_time,speed,equipped,falling,crouched,menu,yaw,x,y,z,left_x,left_y,left_z,right_x,right_y,right_z,foot_world_x,foot_world_y,foot_world_z,contact_x,contact_y,contact_z,contact_weight,velocity_z,board_left_z,board_right_z,board_pitch,board_z,bag_pitch,bag_z,cloth_pitch,board_stencil,character_stencil,goofy,preferred_goofy,continuous_push\n");
};
