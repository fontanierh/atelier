#include "YorimichiCombatFX.h"
#include "JapanNetwork.h"
#include "WandererCharacter.h"
#include "Engine/World.h"

// Yorimichi's combat reactions, composed from the platform's effects (AAtelierFX): which sparks, flashes, rings, light,
// shake, slow motion and sound each moment of the sword fight gets.

AYorimichiCombatFX* AYorimichiCombatFX::Get(const UObject* WorldContext) { return Cast<AYorimichiCombatFX>(AAtelierFX::Get(WorldContext)); }

void AYorimichiCombatFX::HitStop(float Seconds, AActor* A, AActor* B)
{
    if (!JapanNetwork::IsOnline(GetWorld())) Super::HitStop(Seconds, A, B);
}
void AYorimichiCombatFX::SlowMotion(float Seconds, float Dilation)
{
    if (!JapanNetwork::IsOnline(GetWorld())) Super::SlowMotion(Seconds, Dilation);
}

static FVector RandomUnit(FRandomStream& R) { return R.GetUnitVector(); }

void AYorimichiCombatFX::SwordSwing(const FVector& At, int32 Strength)
{
    Play(Strength >= 2 ? TEXT("sword_swing_heavy") : TEXT("sword_swing"), At, Strength >= 2 ? 1.f : .8f, .06f);
}

void AYorimichiCombatFX::SwordHit(const FVector& At, const FVector& SwingDir, int32 Strength, AActor* Wielder, AActor* Victim)
{
    const float K = Strength >= 3 ? 1.45f : Strength == 2 ? 1.2f : 1.f;
    HitStop(Strength >= 3 ? .13f : Strength == 2 ? .08f : .055f, Wielder, Victim);
    Flash(At, 70.f * K, FLinearColor(1.f, .84f, .6f) * 4.5f, .09f + .02f * Strength);
    Flash(At, 28.f * K, FLinearColor(1.f, 1.f, .95f) * 9.f, .05f);
    Burst(At, SwingDir.GetSafeNormal(), FMath::RoundToInt(14 * K), 1150.f * K, FLinearColor(1.f, .6f, .22f) * 9.f, .3f, 3.2f);
    Streaks(At, Strength >= 2 ? 7 : 4, 7.f * K, FLinearColor(1.f, .92f, .8f) * 6.f);
    if (Strength >= 2)
    {
        FParticle& Ring = Spawn(ESprite::Ring, At); Ring.Size0 = 25.f; Ring.Size1 = 140.f * K; Ring.Life = .2f; Ring.Color = FLinearColor(1.f, .75f, .45f) * 2.6f;
    }
    LightFlash(At, FLinearColor(1.f, .72f, .42f), 11000.f * K, 450.f, .11f);
    Shake(Strength >= 3 ? .75f : Strength == 2 ? .45f : .28f);
    Play(Strength >= 2 ? TEXT("hit_heavy") : TEXT("hit_body"), At, Strength >= 2 ? 1.f : .9f, .06f);
    if (Strength >= 3) SlowMotion(.32f, .3f);
    if (Victim) Dust(Victim->GetActorLocation() - FVector(0, 0, 85.f), .4f + .3f * Strength, SwingDir.GetSafeNormal2D());
}

void AYorimichiCombatFX::Parry(const FVector& At, AActor* Defender, AActor* Attacker)
{
    HitStop(.09f, Defender, Attacker);
    Flash(At, 80.f, FLinearColor(1.f, .93f, .78f) * 3.f, .12f);
    Flash(At, 30.f, FLinearColor(1.f, 1.f, 1.f) * 6.f, .05f);
    Burst(At, FVector::UpVector * .4f, 30, 1500.f, FLinearColor(1.f, .85f, .5f) * 7.f, .36f, 3.f);
    Streaks(At, 7, 6.f, FLinearColor(.9f, .95f, 1.f) * 4.f);
    FParticle& Ring = Spawn(ESprite::Ring, At); Ring.Size0 = 20.f; Ring.Size1 = 170.f; Ring.Life = .2f; Ring.Color = FLinearColor(.75f, .88f, 1.f) * 2.2f;
    FParticle& Ring2 = Spawn(ESprite::Ring, At); Ring2.Size0 = 10.f; Ring2.Size1 = 120.f; Ring2.Life = .15f; Ring2.Color = FLinearColor(1.f, .9f, .7f) * 3.f;
    LightFlash(At, FLinearColor(.95f, .95f, 1.f), 16000.f, 520.f, .15f);
    Shake(.5f);
    Play(TEXT("parry"), At, 1.f, .04f);
    SlowMotion(.34f, .28f);
}

void AYorimichiCombatFX::PlayerHurt(const FVector& At, const FVector& From, float Damage, AActor* Victim, AActor* Attacker, bool bKnockDown)
{
    const FVector Dir = (At - From).GetSafeNormal();
    HitStop(bKnockDown ? .12f : .07f, Victim, Attacker);
    Flash(At, 55.f, FLinearColor(1.f, .45f, .3f) * 3.f, .09f);
    Burst(At, Dir, 12, 900.f, FLinearColor(1.f, .4f, .22f) * 7.f, .26f, 2.8f);
    Streaks(At, 4, 7.f, FLinearColor(1.f, .75f, .65f) * 5.f);
    LightFlash(At, FLinearColor(1.f, .5f, .35f), 9000.f, 380.f, .09f);
    Shake(bKnockDown ? .9f : .6f);
    Play(TEXT("player_hurt"), At, 1.f, .05f);
    if (AWandererCharacter* P = Cast<AWandererCharacter>(Victim)) P->FlashDamage(bKnockDown ? 1.f : .7f);
    if (bKnockDown && Victim)
    {
        const FVector Ground = Victim->GetActorLocation() - FVector(0, 0, 70.f);
        PlayLater(.55f, TEXT("body_fall"), Ground, 1.f);
        DustLater(.55f, Ground, 1.2f);
    }
}

void AYorimichiCombatFX::ChargeTick(const FVector& Base, const FVector& Tip, float Fraction, float Dt)
{
    // Embers lift off the blade; the rate and brightness grow with the charge. A soft glow gathers at the tip.
    ChargeAccumulator += Dt * (26.f + 70.f * Fraction);
    while (ChargeAccumulator >= 1.f)
    {
        ChargeAccumulator -= 1.f;
        FParticle& P = Spawn(ESprite::Glow, FMath::Lerp(Base, Tip, Rand.FRandRange(.15f, 1.f)) + RandomUnit(Rand) * 3.f);
        P.V = FVector(0, 0, Rand.FRandRange(40.f, 110.f)) + RandomUnit(Rand) * 35.f; P.Drag = 1.4f; P.Gravity = -60.f;
        P.Life = Rand.FRandRange(.35f, .7f); P.Size0 = Rand.FRandRange(3.f, 6.f) * (1.f + Fraction); P.Size1 = P.Size0 * .3f;
        P.Color = FLinearColor(1.f, .62f + .2f * Rand.FRand(), .25f) * (5.f + 7.f * Fraction); P.FadeIn = .05f;
    }
    FParticle& G = Spawn(ESprite::Glow, Tip); G.Life = .05f; G.Size0 = G.Size1 = 14.f + 34.f * Fraction; G.Color = FLinearColor(1.f, .7f, .35f) * (1.5f + 4.f * Fraction);
    FParticle& H = Spawn(ESprite::Glow, FMath::Lerp(Base, Tip, .55f)); H.Life = .05f; H.Size0 = H.Size1 = 30.f + 30.f * Fraction; H.Color = FLinearColor(1.f, .6f, .3f) * (.5f + 1.5f * Fraction);
}

void AYorimichiCombatFX::ChargeReady(const FVector& At)
{
    Flash(At, 90.f, FLinearColor(1.f, .8f, .45f) * 5.f, .18f);
    FParticle& Ring = Spawn(ESprite::Ring, At); Ring.Size0 = 20.f; Ring.Size1 = 150.f; Ring.Life = .26f; Ring.Color = FLinearColor(1.f, .78f, .4f) * 3.f;
    Burst(At, FVector::UpVector, 14, 700.f, FLinearColor(1.f, .75f, .35f) * 8.f, .35f, 2.6f);
    LightFlash(At, FLinearColor(1.f, .78f, .45f), 8000.f, 400.f, .18f);
    Play(TEXT("charge_ready"), At, .9f, .0f);
}

void AYorimichiCombatFX::SpiritEmbers(const FVector& At, int32 Count, float Radius, float Rise)
{
    for (int32 I = 0; I < Count; ++I)
    {
        FVector Offset = RandomUnit(Rand) * Rand.FRandRange(0.f, Radius); Offset.Z *= 1.8f;
        FParticle& P = Spawn(ESprite::Glow, At + Offset);
        P.V = FVector(0, 0, Rise * Rand.FRandRange(.5f, 1.3f)) + FVector(Offset.Y, -Offset.X, 0).GetSafeNormal() * Rand.FRandRange(20.f, 70.f);
        P.Drag = .9f; P.Gravity = -Rise * .6f; P.Life = Rand.FRandRange(.8f, 1.8f); P.Size0 = Rand.FRandRange(3.5f, 9.f); P.Size1 = P.Size0 * .25f;
        P.Color = (Rand.FRand() < .7f ? FLinearColor(1.f, .38f, .12f) : FLinearColor(1.f, .82f, .6f)) * Rand.FRandRange(5.f, 10.f); P.FadeIn = .12f; P.Wobble = Rand.FRandRange(20.f, 60.f);
    }
}

