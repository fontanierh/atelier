// The station arrival boards of the Belmonte train service: at Hidamari and at Belmonte, the next train and the one
// after, counted down in real minutes. Everything shown is a pure function of the shared service clock and the
// timetable's samples, so every player reads the same board without any replication of its own.
#include "BelmonteTrainService.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

// A train within this many metres of a terminus's stop stands there.
static constexpr double TrainStopTolerance = 1.;

static double WrapServiceTime(double Time, double Cycle)
{
    return Cycle > 0. ? FMath::Fmod(FMath::Fmod(Time, Cycle) + Cycle, Cycle) : Time;
}

TArray<FBelmonteTrainStop> FBelmonteTrainLine::Stops(double At) const
{
    TArray<FBelmonteTrainStop> Out;
    for (int32 Train = 0; Train < Trains.Num(); ++Train)
    {
        const FBelmonteTrainRun& Run = Trains[Train];
        const int32 N = Run.S.Num();
        if (N <= 0) continue;
        auto Standing = [&](int32 K) { return FMath::Abs(double(Run.S[((K % N) + N) % N]) - At) < TrainStopTolerance; };
        int32 First = INDEX_NONE;
        for (int32 K = 0; K < N && First == INDEX_NONE; ++K) if (!Standing(K)) First = K;
        if (First == INDEX_NONE) continue;      // a train that never leaves has no arrivals
        // From a sample away from the station, around the cycle once: each stand from its first sample to its last.
        for (int32 K = First + 1; K <= First + N; ++K)
            if (Standing(K) && !Standing(K - 1))
            {
                int32 End = K;
                while (Standing(End + 1)) ++End;
                Out.Add({Train, WrapServiceTime(Run.T0 + K * Run.Dt, Cycle), WrapServiceTime(Run.T0 + End * Run.Dt, Cycle)});
            }
    }
    Out.Sort([](const FBelmonteTrainStop& A, const FBelmonteTrainStop& B) { return A.Arrive < B.Arrive; });
    return Out;
}

TArray<FBelmonteTrainArrival> FBelmonteTrainLine::NextArrivals(const TArray<FBelmonteTrainStop>& Stops, double Cycle, double Time, int32 Count)
{
    TArray<FBelmonteTrainArrival> Standing, Coming;
    if (Cycle <= 0. || Count <= 0) return Standing;
    const double Local = WrapServiceTime(Time, Cycle);
    for (const FBelmonteTrainStop& Stop : Stops)
    {
        // Seconds since its latest arrival here: within its stand, it is at the platform; its next arrival is one cycle on.
        const double Since = WrapServiceTime(Local - Stop.Arrive, Cycle);
        if (Since <= WrapServiceTime(Stop.Depart - Stop.Arrive, Cycle)) Standing.Add({Stop.Train, 0., true});
        for (int32 K = 0; K < Count; ++K) Coming.Add({Stop.Train, Cycle - Since + K * Cycle, false});
    }
    Coming.Sort([](const FBelmonteTrainArrival& A, const FBelmonteTrainArrival& B) { return A.In < B.In; });
    Standing.Append(Coming);
    if (Standing.Num() > Count) Standing.SetNum(Count);
    return Standing;
}

FString FBelmonteTrainLine::Countdown(const FBelmonteTrainArrival& Arrival, double Scale)
{
    if (Arrival.Train == INDEX_NONE) return TEXT("-");
    if (Arrival.bAtPlatform) return TEXT("at platform");
    const double Real = Arrival.In / FMath::Max(Scale, 1e-3);
    if (Real < 60.) return TEXT("arriving");
    return FString::Printf(TEXT("in %d min"), FMath::FloorToInt(Real / 60.));
}

// ------------------------------------------------------------------------------------------------------------ Boards

namespace
{
// A dark board with a dark wood frame and warm amber lettering, like a period split-flap board.
const FLinearColor BoardFace(.012f, .011f, .010f), BoardFrame(.09f, .05f, .025f), BoardIron(.03f, .035f, .03f);
const FColor HeaderColour(236, 214, 168), LabelColour(232, 170, 92), ValueColour(255, 178, 64);
const TCHAR* TextMaterialPath = TEXT("/Game/BelmonteTrain/Materials/M_BT_BoardText.M_BT_BoardText");
// Board, frame and posts: flat colours on Belmonte's master material, set as the track's MI_TK_* instances are
// (import_belmonte_track.py): the engine cube's own material is a grid.
const TCHAR* BodyMaterialPath = TEXT("/Game/Belmonte/Materials/M_Belmonte.M_Belmonte");
constexpr float TextCullCm = 5000.f, BoardCullCm = 20000.f;

FVector BoardVector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return A.Num() >= 3 ? FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()) : FVector::ZeroVector;
}
}

void ABelmonteTrainService::BuildBoards(const TSharedPtr<FJsonObject>& Root)
{
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (GetNetMode() == NM_DedicatedServer || !Root->TryGetArrayField(TEXT("stations"), Rows)) return;
    UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    UMaterialInterface* TextMaterial = LoadObject<UMaterialInterface>(nullptr, TextMaterialPath);
    UMaterialInterface* BodyMaterial = LoadObject<UMaterialInterface>(nullptr, BodyMaterialPath);
    if (!TextMaterial) UE_LOG(LogTemp, Warning, TEXT("TRAIN BOARDS missing %s: unlit text falls back to the lit default"), TextMaterialPath);
    if (!Cube) return;
    auto Box = [&](const FString& Name, const FTransform& Where, const FVector& SizeCm, const FLinearColor& Colour, bool bCollide)
    {
        auto* C = NewObject<UStaticMeshComponent>(this, *Name);
        C->SetMobility(EComponentMobility::Static);
        C->SetupAttachment(RootComponent);
        C->SetStaticMesh(Cube);
        C->SetWorldTransform(FTransform(Where.GetRotation(), Where.GetLocation(), SizeCm / 100.));
        C->SetCollisionProfileName(bCollide ? TEXT("BlockAll") : TEXT("NoCollision"));
        C->SetAffectDistanceFieldLighting(false);
        C->SetCachedMaxDrawDistance(BoardCullCm);
        C->RegisterComponent();
        if (BodyMaterial)
        {
            if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(0, BodyMaterial))
            {
                M->SetVectorParameterValue(TEXT("Colour"), Colour);
                for (const TPair<const TCHAR*, float>& P : {TPair<const TCHAR*, float>(TEXT("WhiteVertex"), 1.f), {TEXT("Strength"), 0.f},
                                                            {TEXT("Terrain"), 0.f}, {TEXT("Brightness"), 1.f}, {TEXT("Roughness"), .85f}})
                    M->SetScalarParameterValue(P.Key, P.Value);
            }
        }
        else if (UMaterialInterface* Base = C->GetMaterial(0))
            if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(0, Base)) M->SetVectorParameterValue(TEXT("Color"), Colour);
        Parts.Add(C);
    };
    for (int32 Index = 0; Index < Rows->Num() && Index < Stations.Num(); ++Index)
    {
        const TSharedPtr<FJsonObject> S = (*Rows)[Index] ? (*Rows)[Index]->AsObject() : nullptr;
        const TArray<TSharedPtr<FJsonValue>>* BoardRows = nullptr;
        if (!S || !S->TryGetArrayField(TEXT("boards"), BoardRows)) continue;
        // Trains arrive here from the other terminus ("Belmonte Station" -> "BELMONTE").
        // Older generated data may still carry the former "Gare de" prefix.
        FString From;
        for (const FStation& Other : Stations)
            if (&Other != &Stations[Index])
            {
                FString Name = Other.Name.TrimStartAndEnd();
                if (Name.EndsWith(TEXT("Station")))
                    Name.LeftChopInline(7);
                else
                {
                    int32 Space = INDEX_NONE;
                    if (Name.FindLastChar(TEXT(' '), Space)) Name = Name.RightChop(Space + 1);
                }
                From = Name.ToUpper();
            }
        const FString Header = From.IsEmpty() ? FString(TEXT("ARRIVALS")) : TEXT("ARRIVALS FROM ") + From;
        for (const auto& Value : *BoardRows)
        {
            const TSharedPtr<FJsonObject> B = Value ? Value->AsObject() : nullptr;
            const TArray<TSharedPtr<FJsonValue>>* SizeArr = nullptr;
            const TArray<TSharedPtr<FJsonValue>>* LocArr = nullptr;
            if (!B || !B->TryGetArrayField(TEXT("size"), SizeArr) || !B->TryGetArrayField(TEXT("location"), LocArr)) continue;
            FBoard& Board = Boards.AddDefaulted_GetRef();
            B->TryGetStringField(TEXT("id"), Board.Id);
            Board.Station = Index;
            const FVector Size = BoardVector(*SizeArr);      // width, height, depth (cm)
            const double W = Size.X, H = Size.Y, D = Size.Z;
            double Yaw = 0., MountZ = 0.;
            bool bDouble = false;
            FString Mount;
            B->TryGetNumberField(TEXT("yaw"), Yaw);
            B->TryGetBoolField(TEXT("double_sided"), bDouble);
            B->TryGetStringField(TEXT("mount"), Mount);
            B->TryGetNumberField(TEXT("mount_z"), MountZ);
            const FTransform Frame(FRotator(0., Yaw, 0.), BoardVector(*LocArr));
            // The board: a wood frame and a black face proud of it on each side read (board x: its front).
            Box(Board.Id + TEXT("_Frame"), Frame, FVector(D - 2., W + 14., H + 14.), BoardFrame, false);
            Box(Board.Id + TEXT("_Face"), Frame, FVector(D, W, H), BoardFace, false);
            // Posts down to the platform, or rods up to the beam it hangs from, near its ends.
            for (const double Y : {-.4 * W, .4 * W})
            {
                const FVector Top = Frame.TransformPosition(FVector(0., Y, Mount == TEXT("posts") ? -H / 2 : H / 2));
                const double Span = Mount == TEXT("posts") ? Top.Z - MountZ : MountZ - Top.Z;
                if ((Mount != TEXT("posts") && Mount != TEXT("rods")) || Span <= 1.) continue;
                const bool bPost = Mount == TEXT("posts");
                const FVector Mid(Top.X, Top.Y, (Top.Z + MountZ) / 2);
                Box(Board.Id + (bPost ? TEXT("_Post") : TEXT("_Rod")) + (Y < 0. ? TEXT("R") : TEXT("L")), FTransform(Frame.GetRotation(), Mid),
                    FVector(bPost ? 10. : 3., bPost ? 10. : 3., Span), BoardIron, bPost);
            }
            // Lettering on each face: the header centred, the labels from the reader's left (+y of the face), the
            // countdowns to their right. Sized from the board so it reads from about 10 m.
            const double Row = FMath::Min(.2 * H, .062 * W), Margin = .06 * W;
            for (int32 Side = 0; Side < (bDouble ? 2 : 1); ++Side)
            {
                const FRotator FaceYaw(0., Side ? 180. : 0., 0.);
                auto Text = [&](const FString& Name, const FString& Content, double Y, double Z, double Size, EHorizTextAligment Align, const FColor& Colour)
                {
                    auto* T = NewObject<UTextRenderComponent>(this, *(Board.Id + Name + (Side ? TEXT("B") : TEXT("F"))));
                    T->SetMobility(EComponentMobility::Static);
                    T->SetupAttachment(RootComponent);
                    const FVector Local = FaceYaw.RotateVector(FVector(D / 2 + .6, Y, Z));
                    T->SetWorldLocationAndRotation(Frame.TransformPosition(Local), Frame.GetRotation() * FaceYaw.Quaternion());
                    if (TextMaterial) T->SetTextMaterial(TextMaterial);
                    T->SetText(FText::FromString(Content));
                    T->SetWorldSize(float(Size));
                    T->SetHorizontalAlignment(Align);
                    T->SetVerticalAlignment(EVRTA_TextCenter);
                    T->SetTextRenderColor(Colour);
                    T->SetCastShadow(false);
                    T->SetCollisionEnabled(ECollisionEnabled::NoCollision);
                    T->SetCachedMaxDrawDistance(TextCullCm);
                    T->RegisterComponent();
                    Parts.Add(T);
                    return T;
                };
                Text(TEXT("_Header"), Header, 0., .30 * H, .72 * Row, EHTA_Center, HeaderColour);
                Text(TEXT("_Label1"), TEXT("Next train"), W / 2 - Margin, .02 * H, Row, EHTA_Left, LabelColour);
                Text(TEXT("_Label2"), TEXT("Following train"), W / 2 - Margin, -.26 * H, Row, EHTA_Left, LabelColour);
                Board.Next.Add(Text(TEXT("_Next"), TEXT(""), -(W / 2 - Margin), .02 * H, Row, EHTA_Right, ValueColour));
                Board.After.Add(Text(TEXT("_After"), TEXT(""), -(W / 2 - Margin), -.26 * H, Row, EHTA_Right, ValueColour));
            }
        }
    }
    if (Boards.Num()) UE_LOG(LogTemp, Display, TEXT("TRAIN BOARDS %d boards text_material=%d"), Boards.Num(), TextMaterial != nullptr);
}

void ABelmonteTrainService::UpdateBoards(double Time)
{
    const double Scale = ClockScale();
    for (FBoard& Board : Boards)
    {
        if (!Stations.IsValidIndex(Board.Station)) continue;
        const TArray<FBelmonteTrainArrival> Arrivals = FBelmonteTrainLine::NextArrivals(Stations[Board.Station].Stops, Line.Cycle, Time, 2);
        for (int32 K = 0; K < 2; ++K)
        {
            const FString Shown = FBelmonteTrainLine::Countdown(Arrivals.IsValidIndex(K) ? Arrivals[K] : FBelmonteTrainArrival(), Scale);
            if (Shown == Board.Shown[K]) continue;      // the text (and its mesh) changes about once a minute
            Board.Shown[K] = Shown;
            for (UTextRenderComponent* T : K ? Board.After : Board.Next) if (T) T->SetText(FText::FromString(Shown));
        }
    }
}
