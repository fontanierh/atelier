#pragma once
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"

/** Fingers wrapped round the handle a hand holds, after the arm IK and the wrist turns (#7633: the clips' fists, clenched
 *  round a 1.8 cm circle, buried the fingers in the sword's grip and the glider's handles). Each finger's three bones bend
 *  about the finger's own bend axis, the smallest change from the incoming pose, until the skin round each segment (a
 *  capsule round the bone, the last out to the fingertip) just meets the handle's surface: an elliptic cylinder, the
 *  sword's oval grip or the glider's tube. A segment inside opens; the outer two, left floating, close onto it. Lengths
 *  are kept and each joint stays within its flexion range, so a finger that cannot clear keeps its nearest pose (the
 *  incoming one when no bend gets nearer) and reports the depth it still has. Then, on this wrapped pose, the thumb's end
 *  joint goes onto the index finger's outside, both skins clear of the handle, or as far round the handle toward it as
 *  the thumb reaches (a two-bone IK; its last bone keeps its turn on the middle one, #7565), and bends onto it too. */
struct FFingerWrapNode final : public FAnimNode_SkeletalControlBase
{
    enum class EDigit : uint8 { Unmeasured, Straight, Solved };   // missing bones, frame or handle / measured, not bent / bent
    struct FHand
    {
        float Weight = 0.f;
        bool bInFrame = false;   // the handle moves with Frame (else: the component)
        FVector A = FVector::ZeroVector, B = FVector::ZeroVector;   // the handle's usable span, in its space
        FVector Major = FVector::ForwardVector;   // its oval's major axis, in its space
        FVector2D R0 = FVector2D(2.f, 2.f), R1 = FVector2D(2.f, 2.f);   // the oval's radii (major, minor) at A and at B
        FVector2D RM = FVector2D(2.f, 2.f);   // and at its waist, MidAt of the way from A to B (none: MidAt outside 0-1)
        float MidAt = -1.f;
        // Each finger's skin on its palm side, from its bones (index to little, then the thumb; cm: the bones' nearest
        // approach to the sword's grip less the posed mesh's, in game, #7633: the ring and little fingers' pads are
        // thinner, and a capsule as thick as the finger's half width held them off the grip) and its tip past the last
        // joint (in middle bones' lengths: with the skin round it, the posed mesh reaches 1.5-1.9 cm past it).
        float Skin[5] = { 1.f, 1.f, .8f, .75f, .95f };
        float Tip[5] = { .3f, .3f, .3f, .3f, .3f };
        FBoneReference Bones[5][3];   // each finger's base, middle and end bones, the thumb's last
        // At the last evaluation (Evaluations), each digit's state, its skin's deepest overlap with the handle anywhere
        // (cm), its nearest approach to the handle on the usable span alone (cm; 100: none of it over the span), and the
        // thumb's skin's nearest approach to the index finger's (cm; negative: overlap).
        float Evaluated = 0.f;   // the weight it was evaluated at
        EDigit State[5] = { EDigit::Unmeasured, EDigit::Unmeasured, EDigit::Unmeasured, EDigit::Unmeasured, EDigit::Unmeasured };
        float Residual[5] = { 0.f, 0.f, 0.f, 0.f, 0.f };
        float Grip[5] = { 100.f, 100.f, 100.f, 100.f, 100.f };
        float Pinch = 100.f;
        void Reset() { Evaluated = 0.f; Pinch = 100.f; for (int32 F = 0; F < 5; ++F) { State[F] = EDigit::Unmeasured; Residual[F] = 0.f; Grip[F] = 100.f; } }
    };
    FHand Hands[2];
    FBoneReference Frame;        // the bone a held sword moves with (the sword hand)
    float Units = 1.f;           // the component's units in a cm (its scale's inverse): skin and clearances are in cm
    float Contact = .05f;        // the pads' clearance once wrapped, cm
    float Floating = .15f;       // a segment further off than this closes onto the handle, cm
    float OpenLimit = 80.f, CloseLimit = 45.f;   // the most a bend may open or close from the incoming pose, degrees
    // Each joint's flexion range about the bend axis, degrees: the knuckle (from the hand's wrist-to-knuckle line), the
    // middle and the end joints. A pose already outside one is not pushed further out.
    float FlexMin[3] = { -20.f, 0.f, 0.f }, FlexMax[3] = { 95.f, 110.f, 90.f };
    float ThumbFlexMin[3] = { 0.f, -10.f, -10.f }, ThumbFlexMax[3] = { 0.f, 60.f, 80.f };   // its middle and end joints
    uint32 Evaluations = 0;      // evaluations made with a hand held, so a reader can tell a fresh measurement from a stale one

    /** A point's signed distance from an ellipse (radii Ra, Rb) in its plane, negative inside: the nearest point by four
     *  fixed-point steps on its parameter (the radial gap overstates it off the axes, #7735; against a dense brute force
     *  on these radii it never overstates the distance outside and is within 1e-7 cm inside). */
    static double EllipseDistance(double Px, double Py, double Ra, double Rb)
    {
        const double X = FMath::Abs(Px), Y = FMath::Abs(Py);
        double Tx = UE_DOUBLE_INV_SQRT_2, Ty = UE_DOUBLE_INV_SQRT_2;
        for (int32 I = 0; I < 4; ++I)
        {
            const double Ex = (Ra * Ra - Rb * Rb) * Tx * Tx * Tx / Ra, Ey = (Rb * Rb - Ra * Ra) * Ty * Ty * Ty / Rb;
            const double Rx = Ra * Tx - Ex, Ry = Rb * Ty - Ey, Qx = X - Ex, Qy = Y - Ey;
            const double R = FMath::Sqrt(Rx * Rx + Ry * Ry), Q = FMath::Max(FMath::Sqrt(Qx * Qx + Qy * Qy), 1e-9);
            Tx = FMath::Clamp((Qx * R / Q + Ex) / Ra, 0., 1.); Ty = FMath::Clamp((Qy * R / Q + Ey) / Rb, 0., 1.);
            const double T = FMath::Max(FMath::Sqrt(Tx * Tx + Ty * Ty), 1e-9); Tx /= T; Ty /= T;
        }
        const double D = FMath::Sqrt(FMath::Square(X - Ra * Tx) + FMath::Square(Y - Rb * Ty));
        return X * X / (Ra * Ra) + Y * Y / (Rb * Rb) < 1. ? -D : D;
    }
    /** A joint's flexion: the signed turn from one bone's direction to the next about the bend axis, degrees. */
    static double Flexion(const FVector& In, const FVector& Out, const FVector& Bend)
    {
        return FMath::RadiansToDegrees(FMath::Atan2((In ^ Out) | Bend, In | Out));
    }
    /** One pass of a digit's bends about its own bend axis (Bend) onto a surface, from bone From: a segment inside opens;
     *  one from CloseFrom on left floating closes; each joint within its flexion range (Min, Max: the first from Wrist's
     *  line to the base joint). The nearest bend that meets the surface; with none in reach, the one nearest to meeting it,
     *  the incoming pose unless a bend gets nearer by Improve (#7733, #7735). Guarded, a bend with a later joint inside
     *  opens for the whole chain beyond it (#8025) and a closing bend may not bury a segment (#8034). Turns: each bend's
     *  turn, applied in order, the joints J moved with them. */
    template <typename FClearance, typename FOutside>
    static void Bends(FVector (&J)[4], FQuat (&Turns)[3], const FVector& Bend, const FVector& Wrist, int32 From, int32 CloseFrom,
        const float* Min, const float* Max, double Contact, double Floating, double OpenLimit, double CloseLimit, double Weight,
        double Improve, bool bGuarded, const FClearance& Clearance, const FOutside& Outside)
    {
        for (FQuat& Q : Turns) Q = FQuat::Identity;
        for (int32 K = From; K < 3; ++K)
        {
            auto Turn = [&](double Degrees) { return FQuat(Bend, FMath::DegreesToRadians(Degrees)); };
            // The segments from this joint on, carried by a turn about it: the least clearance from segment K to Last
            auto Through = [&](double Degrees, int32 Last)
            {
                const FQuat R = Turn(Degrees);
                double Least = TNumericLimits<double>::Max();
                for (int32 I = K; I <= Last; ++I) Least = FMath::Min(Least, Clearance(J[K] + R.RotateVector(J[I] - J[K]), J[K] + R.RotateVector(J[I + 1] - J[K])));
                return Least - Contact;
            };
            // With a later joint already inside, no bend about it can clear its bone, so this bend opens for the whole
            // chain beyond it
            bool bStuck = false;
            for (int32 I = K + 1; I < 3; ++I) bStuck |= Outside(J[I]) < Contact;
            const bool bLift = bGuarded && bStuck && Through(0., 2) < 0.;
            auto Gap = [&](double Degrees) { return Through(Degrees, bLift ? 2 : K); };
            const double Now = Gap(0.);
            const bool bOpen = Now < 0.;
            if (!bOpen && (K < CloseFrom || Now <= Floating)) continue;
            const FVector In = K ? J[K] - J[K - 1] : J[0] - Wrist;
            const double Flex = In.IsNearlyZero() ? 0. : Flexion(In, J[K + 1] - J[K], Bend);
            const double Room = In.IsNearlyZero() ? (bOpen ? OpenLimit : 0.) : (bOpen ? Flex - Min[K] : Max[K] - Flex);
            const double Sign = bOpen ? -1. : 1., Limit = FMath::Min(bOpen ? OpenLimit : CloseLimit, FMath::Max(Room, 0.));
            double Lo = 0., Hi = Limit, Best = 0., BestGap = Now;
            bool bCrossed = false;
            for (double Prev = 0.; Prev < Limit; )
            {
                const double Degrees = FMath::Min(Prev + 2., Limit), G = Gap(Sign * Degrees);
                if (bOpen ? G >= 0. : G <= 0.) { Lo = Prev; Hi = Degrees; bCrossed = true; break; }
                if (bOpen ? G > BestGap + Improve : G < BestGap - Improve) { BestGap = G; Best = Degrees; }
                Prev = Degrees;
            }
            if (bCrossed)
            {
                for (int32 Step = 0; Step < 8; ++Step)
                {
                    const double Mid = (Lo + Hi) * .5, G = Gap(Sign * Mid);
                    ((bOpen ? G >= 0. : G <= 0.) ? Hi : Lo) = Mid;
                }
                Best = bOpen ? Hi : Lo;   // on the clear side of contact either way
            }
            if (Best <= 0.) continue;
            const FQuat Q = Turn(Sign * Best * Weight);
            if (bGuarded && !bOpen)
            {
                // A closing turn, as applied at the weight, may not bury a segment: each keeps its own gap or contact,
                // whichever is less (#8034: the base reached the grip with the next bone 1.6 cm inside it)
                bool bBuries = false;
                for (int32 I = K; I < 3 && !bBuries; ++I)
                    bBuries = Clearance(J[K] + Q.RotateVector(J[I] - J[K]), J[K] + Q.RotateVector(J[I + 1] - J[K])) - Contact
                        < FMath::Min(0., Clearance(J[I], J[I + 1]) - Contact);
                if (bBuries) continue;
            }
            Turns[K] = Q;
            for (int32 I = K + 1; I < 4; ++I) J[I] = J[K] + Q.RotateVector(J[I] - J[K]);
        }
    }
    /** A digit wrapped onto a surface: of its incoming pose and its two passes of bends (Bends, plain and guarded), each
     *  from the same joints at the weight, those whose every segment ends with its own gap or contact, whichever is less
     *  (#8086: so none is buried that was not, or deeper); and of them the one least deep inside at its worst, then in all
     *  (its segments' depths summed), then least far off (their gaps beyond contact, summed), then the least turned, so
     *  the incoming pose on a tie (#8091). A pass is judged on its result, not each bend (#8081: opening a clenched fist
     *  sinks a later bone for a bend, which a guard on each bend refused; a half fist, or a pass at part weight, can end
     *  deeper than it came). Clearance(P, Q): a segment's skin clearance; Outside(P): a point's; with Contact, Floating
     *  and Improve in the same units. Turns: the chosen pass's bends' turns, applied in order, the joints J moved with
     *  them. False for a straight digit (no bend axis). */
    template <typename FClearance, typename FOutside>
    static bool WrapDigit(FVector (&J)[4], FQuat (&Turns)[3], const FVector& Wrist, int32 From, int32 CloseFrom, const float* Min,
        const float* Max, double Contact, double Floating, double OpenLimit, double CloseLimit, double Weight, double Improve,
        const FClearance& Clearance, const FOutside& Outside)
    {
        for (FQuat& Q : Turns) Q = FQuat::Identity;
        const FVector Bend = ((J[1] - J[0]) ^ (J[2] - J[1])).GetSafeNormal();
        if (Bend.IsZero()) return false;
        double Was[3];
        for (int32 K = 0; K < 3; ++K) Was[K] = Clearance(J[K], J[K + 1]) - Contact;
        // A pose's rank (worst depth, summed depth, summed gap off, turn), false when it buries a segment
        auto Rank = [&](const FVector (&C)[4], const FQuat (&T)[3], double (&Key)[4])
        {
            bool bKept = true;
            Key[0] = Key[1] = Key[2] = Key[3] = 0.;
            for (int32 K = 0; K < 3; ++K)
            {
                const double G = Clearance(C[K], C[K + 1]) - Contact;
                bKept &= G >= FMath::Min(0., Was[K]);
                Key[0] = FMath::Max(Key[0], -G); Key[1] += FMath::Max(-G, 0.); Key[2] += FMath::Max(G, 0.);
                Key[3] += T[K].GetAngle();
            }
            return bKept;
        };
        double Chosen[4];
        Rank(J, Turns, Chosen);
        FVector Pose[4] = { J[0], J[1], J[2], J[3] };
        for (const bool bGuarded : { false, true })
        {
            FVector C[4] = { J[0], J[1], J[2], J[3] };
            FQuat T[3];
            Bends(C, T, Bend, Wrist, From, CloseFrom, Min, Max, Contact, Floating, OpenLimit, CloseLimit, Weight, Improve, bGuarded, Clearance, Outside);
            double Key[4];
            if (!Rank(C, T, Key)) continue;
            int32 I = 0;
            while (I < 3 && Key[I] == Chosen[I]) ++I;
            if (Key[I] >= Chosen[I]) continue;
            for (int32 K = 0; K < 4; ++K) { Chosen[K] = Key[K]; Pose[K] = C[K]; }
            for (int32 K = 0; K < 3; ++K) Turns[K] = T[K];
        }
        for (int32 I = 0; I < 4; ++I) J[I] = Pose[I];
        return true;
    }

    virtual void InitializeBoneReferences(const FBoneContainer& C) override
    {
        Frame.Initialize(C);
        for (FHand& H : Hands) for (auto& Digit : H.Bones) for (FBoneReference& B : Digit) B.Initialize(C);
    }
    virtual bool IsValidToEvaluate(const USkeleton*, const FBoneContainer&) override
    {
        bool bAny = false;
        for (FHand& H : Hands) if (H.Weight > 0.f) bAny = true; else H.Reset();
        return bAny;
    }
    virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& Result) override
    {
        ++Evaluations;
        const FBoneContainer& C = Output.Pose.GetPose().GetBoneContainer();
        for (FHand& H : Hands)
        {
            H.Reset();
            if (H.Weight <= 0.f) continue;
            const float Weight = FMath::Clamp(H.Weight, 0.f, 1.f);
            H.Evaluated = Weight;
            FTransform Space = FTransform::Identity;
            if (H.bInFrame)
            {
                if (!Frame.IsValidToEvaluate(C)) continue;
                Space = Output.Pose.GetComponentSpaceTransform(Frame.GetCompactPoseIndex(C));
            }
            const FVector A = Space.TransformPosition(H.A), B = Space.TransformPosition(H.B);
            const double Length = (B - A).Size();
            if (Length < Units) continue;
            const FVector U = (B - A) / Length;
            const FVector X = FVector::VectorPlaneProject(Space.TransformVectorNoScale(H.Major), U).GetSafeNormal();
            if (X.IsZero()) continue;
            const FVector Y = U ^ X;
            // A point's signed distance from the handle's surface. The wood goes on past the usable span (the pommel and
            // guard, the glider's bends): there it is its end's oval for Beyond more, then capped, so a finger cannot
            // clear it by slipping off an end (#7733). A capped cylinder's signed distance, convex; the oval's taper along
            // the span (a few %; the sword grip's waist narrows .25 cm over 9 cm, so nearly convex) is taken as a
            // cross-section.
            const double Beyond = 2. * Units;
            const bool bWaist = H.MidAt > 0.f && H.MidAt < 1.f;
            auto RadiiAt = [&](double T)
            {
                const float At = float(FMath::Clamp(T / Length, 0., 1.));
                return !bWaist ? FMath::Lerp(H.R0, H.R1, At)
                    : At < H.MidAt ? FMath::Lerp(H.R0, H.RM, At / H.MidAt) : FMath::Lerp(H.RM, H.R1, (At - H.MidAt) / (1.f - H.MidAt));
            };
            auto Outside = [&](const FVector& P) -> double
            {
                const FVector D = P - A;
                const double T = D | U;
                const FVector2D R = RadiiAt(T);
                const double Side = EllipseDistance(D | X, D | Y, R.X, R.Y);
                const double Past = FMath::Max(-T, T - Length) - Beyond;
                return Side > 0. && Past > 0. ? FMath::Sqrt(Side * Side + Past * Past) : FMath::Max(Side, Past);
            };
            auto InSpan = [&](const FVector& P) { const double T = (P - A) | U; return T >= 0. && T <= Length; };
            // A segment's skin clearance: its capsule's nearest approach. Along a line a convex body's signed distance is
            // convex (this one's nearly), so the least of nine samples brackets the minimum and a golden-section search on
            // that bracket finds it (to under .005 of the segment); and the nearest approach over the usable span alone,
            // sampled.
            auto Clearance = [&](const FVector& P, const FVector& Q, float Skin)
            {
                double Sample[9], Least = TNumericLimits<double>::Max();
                int32 At = 0;
                for (int32 K = 0; K <= 8; ++K) { Sample[K] = Outside(FMath::Lerp(P, Q, K / 8.)); if (Sample[K] < Least) { Least = Sample[K]; At = K; } }
                double Lo = FMath::Max(At - 1, 0) / 8., Hi = FMath::Min(At + 1, 8) / 8.;
                constexpr double Golden = .6180339887498949;
                double S1 = Hi - Golden * (Hi - Lo), S2 = Lo + Golden * (Hi - Lo);
                double F1 = Outside(FMath::Lerp(P, Q, S1)), F2 = Outside(FMath::Lerp(P, Q, S2));
                for (int32 I = 0; I < 8; ++I)
                {
                    if (F1 < F2) { Hi = S2; S2 = S1; F2 = F1; S1 = Hi - Golden * (Hi - Lo); F1 = Outside(FMath::Lerp(P, Q, S1)); }
                    else { Lo = S1; S1 = S2; F1 = F2; S2 = Lo + Golden * (Hi - Lo); F2 = Outside(FMath::Lerp(P, Q, S2)); }
                }
                return FMath::Min3(Least, F1, F2) - Skin * Units;
            };
            auto OnSpan = [&](const FVector& P, const FVector& Q, float Skin)
            {
                double Least = 100. * Units;
                for (int32 K = 0; K <= 16; ++K) { const FVector S = FMath::Lerp(P, Q, K / 16.); if (InSpan(S)) Least = FMath::Min(Least, Outside(S) - Skin * Units); }
                return Least;
            };
            // A digit's joints and tip (past the end joint along the end bone, as the middle bone runs along its own), and
            // what it keeps: its deepest overlap anywhere and its nearest approach over the span.
            auto Joints = [&](const FTransform (&T)[3], float Tip, FVector (&J)[4])
            {
                const FVector Along = T[1].InverseTransformVectorNoScale(T[2].GetLocation() - T[1].GetLocation());
                J[0] = T[0].GetLocation(); J[1] = T[1].GetLocation(); J[2] = T[2].GetLocation();
                J[3] = J[2] + T[2].TransformVectorNoScale(Along) * Tip;
            };
            auto Measure = [&](int32 F, const FVector (&J)[4])
            {
                double Least = 100. * Units, Grip = 100. * Units;
                for (int32 K = 0; K < 3; ++K) { Least = FMath::Min(Least, Clearance(J[K], J[K + 1], H.Skin[F])); Grip = FMath::Min(Grip, OnSpan(J[K], J[K + 1], H.Skin[F])); }
                H.Residual[F] = float(FMath::Max(0., -Least) / Units);
                H.Grip[F] = float(Grip / Units);
            };
            auto Read = [&](int32 F, FCompactPoseBoneIndex (&Bone)[3], FTransform (&T)[3])
            {
                for (int32 K = 0; K < 3; ++K)
                {
                    if (!H.Bones[F][K].IsValidToEvaluate(C)) return false;
                    Bone[K] = H.Bones[F][K].GetCompactPoseIndex(C); T[K] = Output.Pose.GetComponentSpaceTransform(Bone[K]);
                }
                return true;
            };
            // A digit wrapped (WrapDigit, its skin's clearances), its bones' transforms turned with it
            auto Wrap = [&](int32 F, FVector (&J)[4], FTransform (&T)[3], const FVector& Wrist, int32 From, int32 CloseFrom, const float* Min, const float* Max)
            {
                FQuat Turns[3];
                if (!WrapDigit(J, Turns, Wrist, From, CloseFrom, Min, Max, Contact * Units, Floating * Units, OpenLimit, CloseLimit, Weight,
                        .01 * Units, [&](const FVector& P, const FVector& Q) { return Clearance(P, Q, H.Skin[F]); },
                        [&](const FVector& P) { return Outside(P) - H.Skin[F] * Units; }))
                    return false;
                for (int32 K = From; K < 3; ++K) for (int32 I = K; I < 3; ++I) T[I].SetRotation((Turns[K] * T[I].GetRotation()).GetNormalized());
                for (int32 I = 0; I < 3; ++I) T[I].SetLocation(J[I]);
                return true;
            };
            FVector Index[4];
            for (int32 F = 0; F < 4; ++F)
            {
                FCompactPoseBoneIndex Bone[3] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
                FTransform T[3];
                if (!Read(F, Bone, T)) continue;
                FVector J[4];
                Joints(T, H.Tip[F], J);
                const FCompactPoseBoneIndex Hand = C.GetParentBoneIndex(Bone[0]);
                const FVector Wrist = Hand.IsValid() ? Output.Pose.GetComponentSpaceTransform(Hand).GetLocation() : J[0];
                // From the knuckle out, each bone closes onto the handle (the base one too, so the finger wraps from its root
                // rather than curling its tips round a floating base); a straight finger is measured as it is.
                H.State[F] = Wrap(F, J, T, Wrist, 0, 0, FlexMin, FlexMax) ? EDigit::Solved : EDigit::Straight;
                Measure(F, J);
                if (F == 0) for (int32 I = 0; I < 4; ++I) Index[I] = J[I];
                for (int32 K = 0; K < 3; ++K) Result.Emplace(Bone[K], T[K]);
            }
            // The thumb's end joint onto the middle of the wrapped index finger's outer half, pushed out from the handle by
            // both skins so the pads meet outside it. Out of the thumb's reach (on a thick grip the index finger's middle
            // lies on the far side, #7735: a stretched thumb ran straight through the wood), as far round the handle
            // toward it as the thumb reaches, its end joint a skin off the surface. Its middle joint bows out from the
            // handle; then its last two bones bend onto the surface as the fingers do.
            FCompactPoseBoneIndex Bone[3] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
            FTransform T[3];
            if (H.State[0] == EDigit::Unmeasured || !Read(4, Bone, T)) continue;
            const FVector Pad = (Index[1] + Index[2]) * .5;
            const FVector Root = T[0].GetLocation();
            auto Radial = [&](const FVector& P) { return FVector::VectorPlaneProject(P - A, U).GetSafeNormal(); };
            FVector Target = Pad + Radial(Pad) * (H.Skin[0] + H.Skin[4]) * Units;
            const double Reach = .98 * ((T[1].GetLocation() - Root).Size() + (T[2].GetLocation() - T[1].GetLocation()).Size());
            if ((Target - Root).Size() > Reach)
            {
                // Round the handle from the pad back toward the thumb's root, on the oval grown by the thumb's skin, at the
                // pad's place along it or nearer the root's (a thumb lies across the grip at a slant): the reachable point
                // furthest round (else the root's side, at its place along the handle). The thumb goes round the other way
                // from the fingers (they curl from the palm past the knuckles).
                auto AngleOf = [&](const FVector& V) { const FVector N = Radial(V); return FMath::Atan2(N | Y, N | X); };
                const double Grow = (H.Skin[4] + Contact) * Units;
                auto On = [&](double Place, double Angle)
                {
                    const FVector2D R = RadiiAt(Place);
                    return A + U * Place + X * (FMath::Cos(Angle) * (R.X + Grow)) + Y * (FMath::Sin(Angle) * (R.Y + Grow));
                };
                const double Start = AngleOf(Root), Way = FMath::UnwindRadians(AngleOf(Index[0]) - Start) > 0. ? -1. : 1.;
                const double Sweep = Way * FMath::Fmod(Way * (AngleOf(Pad) - Start) + 4. * UE_DOUBLE_PI, 2. * UE_DOUBLE_PI);
                const double PadAt = FMath::Clamp((Pad - A) | U, 0., Length), RootAt = FMath::Clamp((Root - A) | U, 0., Length);
                int32 Best = 37;
                Target = On(RootAt, Start);
                for (int32 Along = 0; Along <= 4; ++Along)
                {
                    const double Place = FMath::Lerp(PadAt, RootAt, Along / 4.);
                    for (int32 Step = 0; Step < Best; ++Step)
                    {
                        const FVector P = On(Place, Start + Sweep * (1. - Step / 36.));
                        if ((P - Root).Size() <= Reach) { Best = Step; Target = P; break; }
                    }
                }
            }
            const FVector Pole = T[1].GetLocation() + Radial(T[1].GetLocation()) * 4. * Units;
            const FQuat EndOnMiddle = T[1].GetRotation().Inverse() * T[2].GetRotation();
            AnimationCore::SolveTwoBoneIK(T[0], T[1], T[2], FMath::Lerp(T[1].GetLocation(), Pole, double(Weight)), FMath::Lerp(T[2].GetLocation(), Target, double(Weight)), false, 1., 1.);
            T[2].SetRotation((T[1].GetRotation() * EndOnMiddle).GetNormalized());
            FVector J[4];
            Joints(T, H.Tip[4], J);
            Wrap(4, J, T, Root, 1, 2, ThumbFlexMin, ThumbFlexMax);
            for (int32 K = 0; K < 3; ++K) Result.Emplace(Bone[K], T[K]);
            H.State[4] = EDigit::Solved;
            Measure(4, J);
            // The two skins' nearest approach: the thumb's outer two segments against the index finger's.
            double Pinch = 100. * Units;
            for (int32 K = 1; K < 3; ++K)
                for (int32 I = 0; I < 3; ++I)
                {
                    FVector P, Q;
                    FMath::SegmentDistToSegmentSafe(J[K], J[K + 1], Index[I], Index[I + 1], P, Q);
                    Pinch = FMath::Min(Pinch, (P - Q).Size() - (H.Skin[4] + H.Skin[0]) * Units);
                }
            H.Pinch = float(Pinch / Units);
        }
        Result.Sort(FCompareBoneTransformIndex());
    }
};
