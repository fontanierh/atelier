#include "JapanMap.h"
#include "JapanAtlasWidget.h"
#include "JapanMapControls.h"
#include "AtelierData.h"
#include "CraterParkTower.h"
#include "JapanGameMode.h"
#include "JapanHUD.h"
#include "JapanNetwork.h"
#include "SkatePark.h"
#include "WandererCharacter.h"
#include "JapanWorld.h"
#include "LiveLibrary.h"
#include "BelmonteTrainService.h"
#include "FerryService.h"
#include "SkateComponent.h"
#include "Engine/World.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Texture2D.h"
#include "ImageUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"

static const FString MarkerPrefix = TEXT("marker_");

static FSlateBrush ShapeBrush(float Radius)
{
    FSlateBrush B;
    B.DrawAs = ESlateBrushDrawType::RoundedBox;
    B.ImageSize = FVector2D(16,16);
    B.TintColor = FLinearColor::White;
    if (Radius <= 0.f) B.OutlineSettings.RoundingType = ESlateBrushRoundingType::HalfHeightRadius;   // a disc for square boxes
    else { B.OutlineSettings.RoundingType = ESlateBrushRoundingType::FixedRadius; B.OutlineSettings.CornerRadii = FVector4(Radius,Radius,Radius,Radius); }
    return B;
}

/** The saved-places bar: markers from the game itself, with a controller and no keyboard. Holding View opens it at the
 *  bottom of the screen. The d-pad, left stick or shoulders choose a place, the top button saves here, the bottom or left
 *  button returns, d-pad Down twice deletes, and the right button, View or Menu closes. The keyboard has the same
 *  actions: arrows, F5, Enter or F9, Delete twice and Esc. Every other key is swallowed: no jump or sword behind it. */
class SMarkerBar : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SMarkerBar) : _Map(nullptr), _PadStyle(0) {}
        SLATE_ARGUMENT(UJapanMap*, Map)
        SLATE_ARGUMENT(int32, PadStyle)
    SLATE_END_ARGS()
    void Construct(const FArguments& In)
    {
        Map = In._Map; PadStyle = In._PadStyle; bPad = PadStyle != 0;
        const FLinearColor Muted(.78f,.79f,.72f,1);
        ChildSlot.HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(FMargin(16,0,16,110))
        [SNew(SBorder).BorderImage(&PanelBrush).BorderBackgroundColor(FLinearColor(.02f,.03f,.03f,.86f)).Padding(FMargin(28,12,28,14))
            [SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
                    [SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(Muted).Text_Lambda([this] { return FText::FromString(Heading()); })]
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0,4,0,6)
                    [SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Bold",24)).ColorAndOpacity(FLinearColor(1,.96f,.86f,1)).Text_Lambda([this] { return FText::FromString(Place()); })]
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
                    [SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(FLinearColor(1,.9f,.6f,1)).Text_Lambda([this] { return FText::FromString(Controls()); })]]];
    }
    virtual bool SupportsKeyboardFocus() const override { return true; }
    virtual void Tick(const FGeometry& G,const double Now,const float Dt) override
    {
        SCompoundWidget::Tick(G,Now,Dt);
        if (Map.IsValid() && !HasKeyboardFocus()) FSlateApplication::Get().SetKeyboardFocus(AsShared(),EFocusCause::SetDirectly);
    }
    virtual FReply OnKeyDown(const FGeometry&,const FKeyEvent& E) override
    {
        UJapanMap* M = Map.Get();
        if (!M) return FReply::Unhandled();
        const FKey K = E.GetKey();
        if (K.IsGamepadKey()) bPad = true; else if (!K.IsMouseButton()) bPad = false;
        const bool bPrevious = K == EKeys::Gamepad_DPad_Left || K == EKeys::Gamepad_LeftStick_Left || K == EKeys::Gamepad_LeftShoulder || K == EKeys::Left;
        const bool bNext = K == EKeys::Gamepad_DPad_Right || K == EKeys::Gamepad_LeftStick_Right || K == EKeys::Gamepad_RightShoulder || K == EKeys::Right;
        if (bPrevious || bNext) { bConfirmDelete = false; M->CycleMarker(bNext ? 1 : -1); return FReply::Handled(); }
        if (E.IsRepeat()) return FReply::Handled();
        const bool bConfirmed = bConfirmDelete; bConfirmDelete = false;
        if (K == EKeys::Gamepad_FaceButton_Top || K == EKeys::F5) { if (M->SetMarker()) M->CloseMarkerBar(); }
        else if (K == EKeys::Gamepad_FaceButton_Bottom || K == EKeys::Gamepad_FaceButton_Left || K == EKeys::Enter || K == EKeys::F9)
        { if (M->ReturnToMarker()) M->CloseMarkerBar(); }
        else if (K == EKeys::Gamepad_DPad_Down || K == EKeys::Delete || K == EKeys::BackSpace)
        { if (bConfirmed) M->DeleteMarker(); else bConfirmDelete = M->HasMarker(); }
        else if (K == EKeys::Gamepad_FaceButton_Right || K == EKeys::Gamepad_Special_Left || K == EKeys::Gamepad_Special_Right || K == EKeys::Escape)
            M->CloseMarkerBar();
        return FReply::Handled();
    }
    virtual FReply OnAnalogValueChanged(const FGeometry&,const FAnalogInputEvent& E) override
    {
        return E.GetKey().IsGamepadKey() ? FReply::Handled() : FReply::Unhandled();
    }
    virtual FNavigationReply OnNavigation(const FGeometry&,const FNavigationEvent&) override { return FNavigationReply::Stop(); }
private:
    TWeakObjectPtr<UJapanMap> Map;
    int32 PadStyle = 0; bool bPad = false, bConfirmDelete = false;
    FSlateBrush PanelBrush = ShapeBrush(10.f);
    FString Heading() const
    {
        const UJapanMap* M = Map.Get();
        const TArray<FString> Keys = M ? M->GetMarkerKeys() : TArray<FString>();
        if (!M || !M->HasMarker()) return TEXT("Saved places");
        FString Text = FString::Printf(TEXT("Saved places  ·  %d of %d"),Keys.Find(M->GetSelectedMarkerKey())+1,Keys.Num());
        if (const AWandererCharacter* Pawn = M->GetOwnerPawn())
            Text += FString::Printf(TEXT("  ·  %.0f m away"),FVector::Dist(Pawn->GetActorLocation(),M->GetMarkerTransform().GetLocation())/100.0);
        return Text;
    }
    FString Place() const
    {
        const UJapanMap* M = Map.Get();
        if (!M || !M->HasMarker()) return TEXT("No saved places yet");
        return M->GetMarkerKeys().Num() > 1 ? TEXT("<   ")+M->GetMarkerName()+TEXT("   >") : M->GetMarkerName();
    }
    FString Controls() const
    {
        const UJapanMap* M = Map.Get();
        if (bConfirmDelete && M) return FString::Printf(TEXT("Delete %s?  %s again deletes it  ·  any other button keeps it"),*M->GetMarkerName(),bPad ? TEXT("D-pad Down") : TEXT("Delete"));
        if (!bPad) return TEXT("F5 save  ·  Enter go  ·  arrows choose, Delete twice deletes  ·  Esc close");
        const FMapPadLabels L = MapPadLabels(PadStyle ? PadStyle : 4);
        return FString::Printf(TEXT("%s save  ·  %s go  ·  d-pad choose, Down twice deletes  ·  %s close"),L.Mark,L.Travel,L.Close);
    }
};

void UJapanMap::Initialize(AWandererCharacter* Pawn)
{
    Owner = Pawn;
    const FString Dir = AtelierDataPath(TEXT("map"));
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*(Dir/TEXT("map.json")))) { UE_LOG(LogTemp,Warning,TEXT("world map: %s/map.json missing (run atelier build yorimichi)"),*Dir); return; }
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) || !Root.IsValid()) { UE_LOG(LogTemp,Warning,TEXT("world map: map.json unreadable")); return; }
    const TArray<TSharedPtr<FJsonValue>>* B = nullptr;
    if (Root->TryGetArrayField(TEXT("bounds"),B) && B->Num() == 4)
        Bounds = FBox2D(FVector2D((*B)[0]->AsNumber(),(*B)[1]->AsNumber()),FVector2D((*B)[2]->AsNumber(),(*B)[3]->AsNumber()));
    auto ReadProjection=[&](const TCHAR* Key,TArray<FVector2D>& Dest)
    {
        const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
        if(Root->TryGetArrayField(Key,Rows))for(const auto& Row:*Rows)
        {const auto& A=Row->AsArray();if(A.Num()==2)Dest.Add(FVector2D(A[0]->AsNumber(),A[1]->AsNumber()));}
    };
    ReadProjection(TEXT("projection_x"),ProjectionX);ReadProjection(TEXT("projection_y"),ProjectionY);
    const TArray<TSharedPtr<FJsonValue>>* Z = nullptr;
    if (Root->TryGetArrayField(TEXT("zones"),Z))
        for (const auto& V : *Z)
        {
            const TSharedPtr<FJsonObject>* O = nullptr;
            if (!V->TryGetObject(O)) continue;
            FJapanMapZone Zone;
            Zone.Key = (*O)->GetStringField(TEXT("key")); Zone.Name = (*O)->GetStringField(TEXT("name"));
            (*O)->TryGetStringField(TEXT("hint"),Zone.Hint);
            Zone.Location = AJapanWorld::ToUE((*O)->GetNumberField(TEXT("x")),(*O)->GetNumberField(TEXT("y")),(*O)->GetNumberField(TEXT("z")));
            Zone.Yaw = -(*O)->GetNumberField(TEXT("yaw"));
            double AboveM = 0.;
            if ((*O)->TryGetNumberField(TEXT("above_m"),AboveM) && FMath::IsFinite(AboveM) && AboveM >= 0. && AboveM <= 60.)
                Zone.Above = float(AboveM * 100.);
            if (!Zone.Key.IsEmpty()) Zones.Add(Zone);
        }
    // Ropeway stops use their fitted access path's actual ground end.
    if(const auto Ropeway=AtelierReadJson(AtelierDataPath(TEXT("gondola/runtime.json"))))
        for(const auto& V:Ropeway->GetArrayField(TEXT("stations")))
        {
            const auto S=V->AsObject();const auto& Walk=S->GetArrayField(TEXT("walk_cm"));if(Walk.IsEmpty())continue;
            const auto& P=Walk.Last()->AsArray();FJapanMapZone Zone;
            Zone.Key=TEXT("gondola_")+S->GetStringField(TEXT("id"));Zone.Name=TEXT("Télécabine — ")+S->GetStringField(TEXT("name"));
            Zone.Hint=TEXT("Montez par l’escalier et attendez une cabine à quai.");
            Zone.Location=FVector(P[0]->AsNumber(),P[1]->AsNumber(),P[2]->AsNumber());
            Zone.Yaw=S->GetNumberField(TEXT("yaw"));Zone.Above=150.f;
            if(!Zones.ContainsByPredicate([&](const FJapanMapZone& Z){return Z.Key==Zone.Key;}))Zones.Add(Zone);
        }
    // The skate pier (world/regions/skatepark) is newer than the painted sheet: add its stop unless map.json already has one.
    if (!Zones.ContainsByPredicate([](const FJapanMapZone& Zone) { return Zone.Key == TEXT("skatepier"); }))
    {
        FVector World; float Yaw = 0.f;
        if (ASkatePark::ReadParkSpawn(AtelierDataPath(TEXT("skatepark/park.json")), World, Yaw))
        {
            FJapanMapZone Zone; Zone.Key = TEXT("skatepier"); Zone.Name = TEXT("Skate pier");
            Zone.Hint = TEXT("Concrete plaza on the sea: ramps, rails and ledges (B for the board)");
            Zone.Location = AJapanWorld::ToUE(World.X, World.Y, World.Z); Zone.Yaw = -Yaw;
            Zones.Add(Zone);
        }
    }
    // The hippodrome (docs/HIPPODROME.md) is newer than the painted sheet too: its stop is the grandstand's walk, by the grandstand.
    if (!Zones.ContainsByPredicate([](const FJapanMapZone& Zone) { return Zone.Key == TEXT("hippodrome"); }))
    {
        FString HippodromeText; TSharedPtr<FJsonObject> Hippodrome;
        const TArray<TSharedPtr<FJsonValue>>* Origin = nullptr; const TSharedPtr<FJsonObject>* Return = nullptr; const TArray<TSharedPtr<FJsonValue>>* At = nullptr;
        if (FFileHelper::LoadFileToString(HippodromeText, *AtelierDataPath(TEXT("hippodrome/hippodrome.json")))
            && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(HippodromeText), Hippodrome) && Hippodrome.IsValid()
            && Hippodrome->TryGetArrayField(TEXT("origin"), Origin) && Origin->Num() >= 3
            && Hippodrome->TryGetObjectField(TEXT("return"), Return) && (*Return)->TryGetArrayField(TEXT("at"), At) && At->Num() >= 2)
        {
            FJapanMapZone Zone; Zone.Key = TEXT("hippodrome"); Zone.Name = TEXT("Hidamari Hippodrome");
            Zone.Hint = TEXT("The oval north of the city: explore the grounds and grandstand");
            Zone.Location = AJapanWorld::ToUE((*Origin)[0]->AsNumber() + (*At)[0]->AsNumber(), (*Origin)[1]->AsNumber() + (*At)[1]->AsNumber(), (*Origin)[2]->AsNumber());
            Zone.Yaw = -float((*Return)->GetNumberField(TEXT("yaw")));
            Zones.Add(Zone);
        }
    }
    const bool bCampSpawned = !JapanNetwork::IsOnline(Owner ? Owner->GetWorld() : nullptr) &&
        !FParse::Param(FCommandLine::Get(), TEXT("noronincamp")) &&
        (!AJapanGameMode::IsScriptedSession() || FParse::Param(FCommandLine::Get(), TEXT("ronincamp")));
    if (bCampSpawned && !Zones.ContainsByPredicate([](const FJapanMapZone& Zone) { return Zone.Key == TEXT("ronin_camp"); }))
    {
        FJapanMapZone Zone; Zone.Key = TEXT("ronin_camp"); Zone.Name = TEXT("Kasa Ronin camp");
        Zone.Hint = TEXT("Coastal bluff overlook: test your blade against the three Kasa Ronin");
        Zone.Location = AJapanWorld::ToUE(-55.0, -74.0, 11.5);
        Zone.Yaw = 92.f;
        Zones.Add(Zone);
    }
    // Crater Park's stop is its tower: the hero line's roll-in crest from the generated park (park.json `lines`), not
    // the r4 drop-in map.json was built with (CraterParkTower.h).
    if (CraterParkTower::HasLines())
        for (FJapanMapZone& Zone : Zones)
            if (Zone.Key == TEXT("craterpark"))
            {
                const FCraterParkStart& Tower = CraterParkTower::Starts()[0];
                Zone.Location = Tower.Ground; Zone.Yaw = Tower.Yaw;
                Zone.Hint = TEXT("The skate park in the volcano's caldera, from the top of its tower. Triangle / Y or B for the board");
            }
    // The Belmonte train's termini (tools/belmonte_train_service.py): arrive on the platform as the next train comes in.
    if (ABelmonteTrainService::IsEnabled() && FPaths::FileExists(AtelierDataPath(TEXT("belmonte_train/service.json"))))
        if (const TSharedPtr<FJsonObject> Train = AtelierReadJson(AtelierDataPath(TEXT("belmonte_train/service.json"))))
        {
            const TArray<TSharedPtr<FJsonValue>>* Stations = nullptr;
            if (Train->TryGetArrayField(TEXT("stations"), Stations))
                for (const auto& Value : *Stations)
                {
                    const auto S = Value->AsObject();
                    const auto Arrival = S->GetObjectField(TEXT("arrival"));
                    const auto& L = Arrival->GetArrayField(TEXT("location"));
                    if (L.Num() < 3) continue;
                    FJapanMapZone Zone; Zone.Key = S->GetStringField(TEXT("key")); Zone.Name = S->GetStringField(TEXT("name"));
                    Zone.Name = Zone.Key == TEXT("hidamari_station") ? TEXT("Hidamari Station") : TEXT("Belmonte Station");
                    Zone.Hint = TEXT("The Belmonte railway: arrive on the platform for the next train");
                    Zone.Location = FVector(L[0]->AsNumber(), L[1]->AsNumber(), L[2]->AsNumber());
                    Zone.Yaw = float(Arrival->GetNumberField(TEXT("yaw")));
                    if (!Zones.ContainsByPredicate([&](const FJapanMapZone& Z) { return Z.Key == Zone.Key; })) Zones.Add(Zone);
                }
        }
    if (const TSharedPtr<FJsonObject> Ferry = AtelierReadJson(AtelierDataPath(TEXT("ferry/service/service.json"))))
    {
        for (const auto& Value : Ferry->GetArrayField(TEXT("terminals")))
        {
            const auto Terminal = Value->AsObject();
            const auto& Walk = Terminal->GetArrayField(TEXT("walk_cm"));
            if (Walk.IsEmpty()) continue;
            const auto& At = Walk[0]->AsArray();
            if (At.Num() != 3) continue;
            FJapanMapZone Zone;
            Zone.Key = TEXT("ferry_") + Terminal->GetStringField(TEXT("key"));
            Zone.Name = Terminal->GetStringField(TEXT("name")) + TEXT(" ferry terminal");
            Zone.Hint = TEXT("The passenger ferry: wait for the ship and board when the gangway is down");
            Zone.Location = FVector(At[0]->AsNumber(), At[1]->AsNumber(), At[2]->AsNumber());
            Zone.Yaw = float(Terminal->GetNumberField(TEXT("walk_yaw"))); Zone.Above = 200.f;
            Zones.Add(Zone);
        }
    }
    ImageFile = Dir/TEXT("map.png");
    Texture = FImageUtils::ImportFileAsTexture2D(ImageFile);
    if (Texture)
    {
        Brush.SetResourceObject(Texture);
        Brush.ImageSize = FVector2D(Texture->GetSizeX(),Texture->GetSizeY());
        Brush.DrawAs = ESlateBrushDrawType::Image;
        Brush.TintColor = FLinearColor::White;
    }
    else UE_LOG(LogTemp,Warning,TEXT("world map: %s failed to load"),*ImageFile);
    InitializeAtlas(Root,Dir);
    bLoaded = Zones.Num() > 0 && Texture != nullptr;
    UE_LOG(LogTemp,Display,TEXT("world map: %d zones, sheet %s, bounds x %.0f..%.0f y %.0f..%.0f"),Zones.Num(),Texture ? *FString::Printf(TEXT("%dx%d"),Texture->GetSizeX(),Texture->GetSizeY()) : TEXT("missing"),Bounds.Min.X,Bounds.Max.X,Bounds.Min.Y,Bounds.Max.Y);
}

FJapanMarkers* UJapanMap::MarkerStore() const
{
    if (!Owner || !Owner->GetLandscape()) return nullptr;
    auto* Store = &Owner->GetLandscape()->Markers; Store->Load(); return Store;
}

const TArray<FJapanMapZone>& UJapanMap::GetZones() const
{
    RefreshPlayerZones();
    const auto* Store = MarkerStore();
    Zones.RemoveAll([Store](const FJapanMapZone& Z)
    {
        return Z.Key.StartsWith(MarkerPrefix) && (!Store || !Store->All().ContainsByPredicate([&](const FJapanMarker& M) { return M.Key == Z.Key; }));
    });
    if (Store) for (const auto& M : Store->All())
    {
        auto* Z = Zones.FindByPredicate([&](const FJapanMapZone& Zone) { return Zone.Key == M.Key; });
        if (!Z) Z = &Zones.AddDefaulted_GetRef();
        Z->Key = M.Key; Z->Name = M.Name; Z->Hint = TEXT("Saved skate-line location");
        Z->Location = M.Ground.GetLocation(); Z->Yaw = M.Ground.Rotator().Yaw;
    }
    return Zones;
}

bool UJapanMap::HasMarker() const
{
    const auto* Store = MarkerStore(); return Store && Store->Selected();
}

FTransform UJapanMap::GetMarkerTransform() const
{
    const auto* Store = MarkerStore();
    return Store && Store->Selected() ? Store->Selected()->Ground : FTransform::Identity;
}

TArray<FString> UJapanMap::GetMarkerKeys() const
{
    TArray<FString> Keys;
    if (const auto* Store = MarkerStore()) for (const auto& M : Store->All()) Keys.Add(M.Key);
    return Keys;
}

FString UJapanMap::GetMarkerName() const
{
    const auto* Store = MarkerStore(); return Store && Store->Selected() ? Store->Selected()->Name : FString();
}

FString UJapanMap::GetSelectedMarkerKey() const
{
    const auto* Store = MarkerStore(); return Store && Store->Selected() ? Store->Selected()->Key : FString();
}

bool UJapanMap::MarkerResult(bool Result)
{
    if (!Result) if (const auto* Store = MarkerStore()) ULiveLibrary::Say(Store->Error.IsEmpty() ? TEXT("Choose a saved marker first.") : Store->Error);
    return Result;
}

bool UJapanMap::SelectMarker(const FString& Key)
{
    auto* Store = MarkerStore(); return Store && MarkerResult(Store->Select(Key));
}

bool UJapanMap::RenameMarker(const FString& Name)
{
    auto* Store = MarkerStore();
    if (!Store || !MarkerResult(Store->Rename(Name))) return false;
    ULiveLibrary::Say(TEXT("Marker renamed.")); return true;
}

bool UJapanMap::DeleteMarker()
{
    auto* Store = MarkerStore();
    if (!Store || !MarkerResult(Store->Delete())) return false;
    ULiveLibrary::Say(TEXT("Marker deleted.")); return true;
}

void UJapanMap::CycleMarker(int32 Direction)
{
    const auto Keys = GetMarkerKeys(); if (Keys.IsEmpty()) return;
    const int32 I = Keys.Find(GetSelectedMarkerKey());
    SelectMarker(Keys[(FMath::Max(0,I)+Direction+Keys.Num())%Keys.Num()]);
}

bool UJapanMap::IsEditingMarkerName() const
{
    return MarkerName.IsValid() && MarkerName->HasKeyboardFocus();
}

bool UJapanMap::SetMarker()
{
    const auto* Store = MarkerStore(); return Store && SaveMarker(Store->NextName());
}

bool UJapanMap::SaveMarker(const FString& Name)
{
    if (!Owner || Owner->IsCinematic() || Owner->AreControlsSuspended() || !Owner->GetLandscape() || !Owner->GetLandscape()->bLoaded) return false;
    const bool bGrounded = Owner->GetCharacterMovement()->IsMovingOnGround() || (Owner->GetSkate() && Owner->GetSkate()->IsRiding() && Owner->GetSkate()->GetMode() == ESkateMode::Ground);
    if (!bGrounded) { ULiveLibrary::Say(TEXT("Stand on solid ground to save a marker.")); return false; }
    const FVector Feet = Owner->GetActorLocation() - FVector(0,0,Owner->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SavedMarker),false,Owner);
    if (!Owner->GetWorld()->LineTraceSingleByChannel(Hit,Feet+FVector(0,0,60),Feet-FVector(0,0,120),ECC_Visibility,Params)
        || FMath::Abs(Feet.Z-Hit.ImpactPoint.Z) > 35.f || !Owner->GetCharacterMovement()->IsWalkable(Hit))
    {
        ULiveLibrary::Say(TEXT("Stand on solid ground to save a marker.")); return false;
    }
    if (!MarkerResult(MarkerStore()->Add(Name,FTransform(FRotator(0,Owner->GetActorRotation().Yaw,0),Hit.ImpactPoint)))) return false;
    const int32 Style = AJapanHUD::CurrentControllerStyle();
    const FMapPadLabels L = MapPadLabels(Style);
    ULiveLibrary::Say(GetMarkerName()+(Style ? FString::Printf(TEXT(" saved. Hold %s, then %s returns here."),L.Map,L.Travel) : FString(TEXT(" saved. F9 returns here."))));
    return true;
}

bool UJapanMap::ReturnToMarker()
{
    if (!Owner || Owner->IsCinematic() || Owner->AreControlsSuspended()) return false;
    if (!HasMarker())
    {
        const int32 Style = AJapanHUD::CurrentControllerStyle();
        const FMapPadLabels L = MapPadLabels(Style);
        ULiveLibrary::Say(Style ? FString::Printf(TEXT("Save a marker first: hold %s, then %s."),L.Map,L.Mark) : FString(TEXT("Save a marker first (F5 or the map).")));
        return false;
    }
    const FTransform Marker = GetMarkerTransform();
    const FVector Ground = Marker.GetLocation();
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SavedMarkerReturn),false,Owner);
    const auto* Capsule = Owner->GetCapsuleComponent();
    // Travel resets crouching: test clearance for the standing capsule, even when saving or returning crouched.
    const auto* Standing = Owner->GetClass()->GetDefaultObject<AWandererCharacter>()->GetCapsuleComponent();
    const float Half = FMath::Max(Capsule->GetUnscaledCapsuleHalfHeight(),Standing->GetUnscaledCapsuleHalfHeight())*Capsule->GetShapeScale();
    const float Radius = FMath::Max(Capsule->GetUnscaledCapsuleRadius(),Standing->GetUnscaledCapsuleRadius())*Capsule->GetShapeScale();
    // A local trace keeps a marker below a bridge or roof on its original floor.
    if (!Owner->GetWorld()->LineTraceSingleByChannel(Hit,Ground+FVector(0,0,30),Ground-FVector(0,0,50),ECC_Visibility,Params)
        || FMath::Abs(Ground.Z-Hit.ImpactPoint.Z) > 20.f || !Owner->GetCharacterMovement()->IsWalkable(Hit)
        || Owner->GetWorld()->OverlapBlockingTestByProfile(Hit.ImpactPoint+FVector(0,0,Half+3.f),FQuat::Identity,
            Capsule->GetCollisionProfileName(),FCollisionShape::MakeCapsule(Radius,Half),Params))
    {
        ULiveLibrary::Say(TEXT("This marker's ground is unavailable or obstructed. Try again when it is clear.")); return false;
    }
    if (!Owner->TravelTo(Hit.ImpactPoint,Marker.Rotator().Yaw,*GetMarkerName(),30.f)) return false;
    ULiveLibrary::Say(TEXT("Returned to ")+GetMarkerName()+TEXT(".")); return true;
}

const FJapanMapZone* UJapanMap::FindZone(const FString& Key) const
{
    for (const auto& Z : GetZones()) if (Z.Key == Key) return &Z;
    return nullptr;
}

bool UJapanMap::TeleportToZone(const FString& Key)
{
    if (Key.StartsWith(TEXT("player_")))
    {
        if (!Owner || Owner->IsCinematic() || Owner->AreControlsSuspended()) return false;
        const uint32 Before = Owner->GetActivityEpoch();
        Owner->ServerTravelToPlayer(Key.Mid(7), Before);
        return Owner->HasAuthority() && Owner->GetActivityEpoch() != Before; // The server resolves the live pawn and reports acceptance.
    }
    if (Key.StartsWith(MarkerPrefix)) return SelectMarker(Key) && ReturnToMarker();
    const FJapanMapZone* Z = FindZone(Key);
    if (!Z || !Owner) return false;
    if (Key == TEXT("craterpark") && CraterParkTower::HasLines()) return CraterParkTower::Return(Owner,0);
    if (Key.EndsWith(TEXT("_station")))
        if (auto* Train = ABelmonteTrainService::Find(Owner)) return Train->GoToStation(Key, true);
    return Owner->TravelTo(Z->Location,Z->Yaw,*Z->Name,Z->Above);
}

FVector2D UJapanMap::ToSheet(const FVector& Location) const
{
    auto Project=[](double V,const TArray<FVector2D>& Knots)
    {
        if(Knots.IsEmpty())return V;
        if(V<=Knots[0].X)return Knots[0].Y;
        for(int32 I=1;I<Knots.Num();++I)if(V<=Knots[I].X)
            return FMath::Lerp(Knots[I-1].Y,Knots[I].Y,(V-Knots[I-1].X)/(Knots[I].X-Knots[I-1].X));
        return Knots.Last().Y;
    };
    const double X=Project(Location.X/100.0,ProjectionX),Y=Project(-Location.Y/100.0,ProjectionY);
    return FVector2D((X-Bounds.Min.X)/(Bounds.Max.X-Bounds.Min.X),(Bounds.Max.Y-Y)/(Bounds.Max.Y-Bounds.Min.Y));
}

void UJapanMap::Open()
{
    if (IsOpen() || !bLoaded || !Owner || !GEngine || !GEngine->GameViewport) return;
    CloseMarkerBar();
    AtlasCurrentRegion();
    Widget = MakeJapanAtlasWidget(this);
    GEngine->GameViewport->AddViewportWidgetContent(Widget.ToSharedRef(),19);
    Owner->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
}

void UJapanMap::Close()
{
    CloseMarkerBar();
    if (Widget && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Widget.ToSharedRef());
    Widget.Reset(); MarkerName.Reset(); AtlasSearch.Reset(); StableName.Reset();
    if (FSlateApplication::IsInitialized()) FSlateApplication::Get().SetAllUserFocusToGameViewport();
    if (Owner) Owner->SetMenuOpen(false);
}

void UJapanMap::OpenMarkerBar()
{
    if (IsMarkerBarOpen() || IsOpen() || !Owner || Owner->IsCinematic() || Owner->AreControlsSuspended() || !MarkerStore() || !GEngine || !GEngine->GameViewport) return;
    TSharedRef<SMarkerBar> Bar = SNew(SMarkerBar).Map(this).PadStyle(AJapanHUD::CurrentControllerStyle());
    MarkerBar = Bar;
    GEngine->GameViewport->AddViewportWidgetContent(Bar,18);
    Owner->SetMenuOpen(true);
    // The bar takes focus while View is still held. It leaves key releases unhandled, so that release still reaches the
    // game through the viewport. The View hold opens it a tick late (AWandererCharacter::SetupPlayerInputComponent), so
    // the hold trigger still sees View come up after the flush this focus change causes, and the next tap and hold start clean.
    FSlateApplication::Get().SetKeyboardFocus(Bar,EFocusCause::SetDirectly);
    UE_LOG(LogTemp,Display,TEXT("MARKERS bar opened: %d saved places"),GetMarkerKeys().Num());
}

void UJapanMap::CloseMarkerBar()
{
    if (!MarkerBar) return;
    if (GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(MarkerBar.ToSharedRef());
    MarkerBar.Reset();
    if (Owner) Owner->SetMenuOpen(false);
    if (FSlateApplication::IsInitialized()) FSlateApplication::Get().SetAllUserFocusToGameViewport();
}

bool UJapanMap::ReviewSlateKey(const FString& Key, bool bPressed)
{
    const FKey K(*Key);
    if (!K.IsValid()) return false;
    const FKeyEvent Event(K,FModifierKeysState(),0,false,0,0);
    if (bPressed) FSlateApplication::Get().ProcessKeyDownEvent(Event); else FSlateApplication::Get().ProcessKeyUpEvent(Event);
    return true;
}

bool UJapanMap::ReviewSlateAnalog(const FString& Key, float Value)
{
    const FKey K(*Key);
    if (!IsOpen() || !K.IsGamepadKey() || !K.IsAnalog() || !FMath::IsFinite(Value)) return false;
    const FAnalogInputEvent Event(K,FModifierKeysState(),0,false,0,0,FMath::Clamp(Value,-1.f,1.f));
    FSlateApplication::Get().ProcessAnalogInputEvent(Event);
    return true;
}

FString UJapanMap::ReviewAtlasController() const
{
    return Widget.IsValid() ? JapanAtlasControllerSnapshot(Widget.ToSharedRef()) : TEXT("{}");
}

bool UJapanMap::ReviewMarkerBarKey(const FString& Key)
{
    const FKey K(*Key);
    if (!IsMarkerBarOpen() || !K.IsValid()) return false;
    auto& App = FSlateApplication::Get();
    const FKeyEvent Event(K,FModifierKeysState(),0,false,0,0);
    App.ProcessKeyDownEvent(Event); App.ProcessKeyUpEvent(Event);
    return true;
}

FString UJapanMap::ReviewMarkerNameInput(const FString& Text)
{
    if (!IsOpen() || !MarkerName || Text.Len()>48) return FString();
    MarkerName->SetText(FText::GetEmpty());
    auto& App = FSlateApplication::Get();
    App.SetKeyboardFocus(MarkerName,EFocusCause::SetDirectly);
    for (TCHAR C : Text)
    {
        const FKey Key = C == TEXT(' ') ? EKeys::SpaceBar : FKey(*FString::Chr(FChar::ToUpper(C)));
        const FKeyEvent Event(Key,FModifierKeysState(),0,false,C,C);
        App.ProcessKeyDownEvent(Event);
        App.ProcessKeyCharEvent(FCharacterEvent(C,FModifierKeysState(),0,false));
        App.ProcessKeyUpEvent(Event);
    }
    return MarkerName ? MarkerName->GetText().ToString() : FString();
}

bool UJapanMap::ReviewCommitMarkerName()
{
    if (!IsEditingMarkerName()) return false;
    auto& App = FSlateApplication::Get();
    const FKeyEvent Event(EKeys::Enter,FModifierKeysState(),0,false,13,13);
    App.ProcessKeyDownEvent(Event); App.ProcessKeyUpEvent(Event);
    return true;
}

bool UJapanMap::IsMarkerReviewOnVehicle() const
{
    return Owner && (Owner->OnVehicle() || (Owner->GetSkate() && Owner->GetSkate()->IsRiding()));
}
