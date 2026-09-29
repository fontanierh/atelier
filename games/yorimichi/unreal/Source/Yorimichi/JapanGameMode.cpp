#include "JapanGameMode.h"
#include "JapanWorld.h"
#include "WandererCharacter.h"
#include "CapeBoyCharacter.h"
#include "Kismet/GameplayStatics.h"
#include "JapanHUD.h"
#include "FoxHunter.h"
#include "Components/CapsuleComponent.h"
#include "CollisionQueryParams.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

/** Scripted sessions (reviews, benchmarks, films, demos, the phone stream) keep the road clear unless asked. */
static bool ScriptedSession()
{
    const TCHAR* Cmd = FCommandLine::Get();
    for (const TCHAR* Key : { TEXT("qa"), TEXT("benchmark"), TEXT("trailershot"), TEXT("buildingreview"), TEXT("AtelierStream") })
        if (FCString::Stristr(Cmd, Key)) return true;
    return false;
}

/** The fox-masked hunter waits 12 m up the road from the start, a little off to the left, standing on whatever ground is built there. */
void AJapanGameMode::SpawnFoxHunter(AJapanWorld* W, AWandererCharacter* Player)
{
    if (!W || !W->bLoaded || FParse::Param(FCommandLine::Get(), TEXT("nofox"))) return;
    if (ScriptedSession() && !FParse::Param(FCommandLine::Get(), TEXT("foxhunter")) && !FParse::Param(FCommandLine::Get(), TEXT("foxqa"))) return;
    const FRotator Facing = W->PlayerStart.Rotator();
    FVector Where = W->PlayerStart.GetLocation() + Facing.Vector() * 1200.f + FRotationMatrix(Facing).GetUnitAxis(EAxis::Y) * -350.f;
    FHitResult Hit; FCollisionQueryParams Params(SCENE_QUERY_STAT(FoxSpawn), false, Player);
    const float HalfHeight = 86.f;
    if (GetWorld()->LineTraceSingleByChannel(Hit, Where + FVector(0, 0, 400), Where - FVector(0, 0, 800), ECC_Visibility, Params)) Where.Z = Hit.ImpactPoint.Z + HalfHeight + 2.f;
    else Where.Z = W->PlayerStart.GetLocation().Z + HalfHeight + 3.f;
    FActorSpawnParameters Spawn; Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
    AFoxHunter* Fox = GetWorld()->SpawnActor<AFoxHunter>(Where, FRotator(0, Facing.Yaw + 180.f, 0), Spawn);
    UE_LOG(LogTemp, Display, TEXT("Fox hunter %s at %s (ground %s)"), Fox ? TEXT("spawned") : TEXT("NOT spawned"), *Where.ToString(), Hit.bBlockingHit ? TEXT("traced") : TEXT("assumed"));
}

AJapanGameMode::AJapanGameMode()
{
    // Wanderer is a village NPC; the yellow kid is the player character.
    DefaultPawnClass = ACapeBoyCharacter::StaticClass();
    HUDClass = AJapanHUD::StaticClass();
}

void AJapanGameMode::BeginPlay()
{
    Super::BeginPlay();
    AJapanWorld* W = GetWorld()->SpawnActor<AJapanWorld>(FVector::ZeroVector, FRotator::ZeroRotator);
    AWandererCharacter* T = Cast<AWandererCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
    if (T) T->EnterWorld(W);
    SpawnFoxHunter(W, T);
}
