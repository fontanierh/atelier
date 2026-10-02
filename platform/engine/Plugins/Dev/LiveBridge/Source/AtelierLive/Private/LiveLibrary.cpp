#include "LiveLibrary.h"
#include "Misc/App.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"
#include "Camera/PlayerCameraManager.h"
#include "Kismet/GameplayStatics.h"
#include "InputKeyEventArgs.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "PhysicsEngine/BodySetup.h"
#include "ImageUtils.h"
#include "UnrealClient.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "MeshDescription.h"
#include "StaticMeshAttributes.h"
#include "StaticMeshOperations.h"
#include "GLTFAsset.h"
#include "GLTFReader.h"
#include "GLTFMeshFactory.h"
#include "HttpServerModule.h"
#include "IHttpRouter.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#if WITH_EDITOR
#include "IPythonScriptPlugin.h"
#endif

// ------------------------------------------------------------------ props
ALiveProp::ALiveProp()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
    Mesh->SetupAttachment(GetRootComponent());
    Mesh->SetMobility(EComponentMobility::Movable);
}

namespace
{
    struct FLiveModel { TObjectPtr<UStaticMesh> Mesh; FBox Bounds = FBox(ForceInit); FDateTime Stamp; FString Error; };
    TMap<FString, FLiveModel> Models;
    TMap<FString, TWeakObjectPtr<ALiveProp>> Props;
    FString Message; double MessageUntil = 0., MessageFrom = 0.;
    bool bStarted = false;
    TSharedPtr<IHttpRouter> Router;
    TArray<FHttpRouteHandle> Routes;

    TFunction<bool(APawn*, const FVector&, float)> Teleport;
    FString Resolve(const FString& Path) { return ULiveLibrary::Resolve(Path); }
    const UAtelierLiveSettings& Settings() { return *GetDefault<UAtelierLiveSettings>(); }

    UMaterialInterface* Painted()
    {
        static TWeakObjectPtr<UMaterialInterface> Cached;
        if (!Cached.IsValid()) Cached = Cast<UMaterialInterface>(Settings().PropMaterial.TryLoad());
        return Cached.Get();
    }

    /** Parse a GLB with the engine's glTF reader and build a static mesh in memory: every mesh node in the scene with its
     *  world transform, one material slot per glTF material, base-colour texture and factor on the painterly master. */
    FLiveModel& LoadModel(const FString& GlbPath)
    {
        const FString Full = Resolve(GlbPath);
        const FDateTime Stamp = IFileManager::Get().GetTimeStamp(*Full);
        FLiveModel& Model = Models.FindOrAdd(Full);
        if (Model.Mesh && Model.Stamp == Stamp) return Model;
        if (Model.Mesh) Model.Mesh->RemoveFromRoot();
        Model = FLiveModel(); Model.Stamp = Stamp;
        if (!FPaths::FileExists(Full)) { Model.Error = TEXT("file not found: ") + Full; return Model; }
        GLTF::FAsset Asset; GLTF::FFileReader Reader;
        Reader.ReadFile(Full, true, false, Asset);
        if (Asset.ValidationCheck() != GLTF::FAsset::Valid) { Model.Error = TEXT("invalid glTF: ") + Full; return Model; }
        // World transforms of the nodes (glTF metres -> centimetres on the translation).
        TArray<FTransform> Global; Global.SetNum(Asset.Nodes.Num());
        TFunction<void(int32, const FTransform&)> Walk = [&](int32 Index, const FTransform& Parent)
        {
            FTransform Local = Asset.Nodes[Index].Transform; Local.SetTranslation(Local.GetTranslation() * 100.f);
            Global[Index] = Local * Parent;
            for (int32 Child : Asset.Nodes[Index].Children) Walk(Child, Global[Index]);
        };
        TArray<int32> Roots; Asset.GetRootNodes(Roots);
        for (int32 Root : Roots) Walk(Root, FTransform::Identity);
        FMeshDescription Merged; FStaticMeshAttributes(Merged).Register();
        int32 Parts = 0;
        for (int32 Index = 0; Index < Asset.Nodes.Num(); ++Index)
        {
            const GLTF::FNode& Node = Asset.Nodes[Index];
            if (!Asset.Meshes.IsValidIndex(Node.MeshIndex)) continue;
            FMeshDescription Part; GLTF::FMeshFactory Factory; Factory.SetUniformScale(100.f);
            Factory.FillMeshDescription(Asset.Meshes[Node.MeshIndex], Global[Index], &Part);
            FStaticMeshOperations::FAppendSettings Append;
            FStaticMeshOperations::AppendMeshDescription(Part, Merged, Append);
            ++Parts;
        }
        if (!Parts) { Model.Error = TEXT("no meshes in ") + Full; return Model; }
        FStaticMeshOperations::ComputeTriangleTangentsAndNormals(Merged);
        FStaticMeshOperations::ComputeTangentsAndNormals(Merged, EComputeNTBsFlags::Tangents | EComputeNTBsFlags::WeightedNTBs);
        UStaticMesh* Mesh = NewObject<UStaticMesh>(GetTransientPackage(), MakeUniqueObjectName(GetTransientPackage(), UStaticMesh::StaticClass(), *FPaths::GetBaseFilename(Full)));
        Mesh->AddToRoot();
        // One slot per glTF material, named as the mesh factory names its polygon groups (the material index).
        TMap<int32, UTexture2D*> Textures;
        for (int32 MaterialIndex = 0; MaterialIndex < FMath::Max(1, Asset.Materials.Num()); ++MaterialIndex)
        {
            UMaterialInstanceDynamic* MID = Painted() ? UMaterialInstanceDynamic::Create(Painted(), Mesh) : nullptr;
            if (MID && Asset.Materials.IsValidIndex(MaterialIndex))
            {
                const GLTF::FMaterial& M = Asset.Materials[MaterialIndex];
                MID->SetVectorParameterValue(TEXT("Tint"), FLinearColor(M.BaseColorFactor.X, M.BaseColorFactor.Y, M.BaseColorFactor.Z, 1.f));
                if (Asset.Textures.IsValidIndex(M.BaseColor.TextureIndex))
                {
                    const GLTF::FImage& Image = Asset.Textures[M.BaseColor.TextureIndex].Source;
                    UTexture2D*& Texture = Textures.FindOrAdd(M.BaseColor.TextureIndex);
                    if (!Texture && Image.Data && Image.DataByteLength)
                        Texture = FImageUtils::ImportBufferAsTexture2D(TArrayView64<const uint8>(Image.Data, Image.DataByteLength));
                    if (Texture) MID->SetTextureParameterValue(TEXT("Tex"), Texture);
                }
            }
            const FName Slot(*FString::FromInt(MaterialIndex));
            FStaticMaterial SlotMaterial(MID ? static_cast<UMaterialInterface*>(MID) : Painted(), Slot);
#if WITH_EDITORONLY_DATA
            SlotMaterial.ImportedMaterialSlotName = Slot;
#endif
            Mesh->GetStaticMaterials().Add(MoveTemp(SlotMaterial));
        }
        UStaticMesh::FBuildMeshDescriptionsParams Params;
        Params.bFastBuild = true; Params.bBuildSimpleCollision = true; Params.bAllowCpuAccess = true; Params.bCommitMeshDescription = false;
        Mesh->BuildFromMeshDescriptions({ &Merged }, Params);
        Model.Mesh = Mesh; Model.Bounds = Mesh->GetBoundingBox();
        UE_LOG(LogTemp, Display, TEXT("LIVE model %s: %d parts, %d materials, bounds %s"), *Full, Parts, Mesh->GetStaticMaterials().Num(), *Model.Bounds.ToString());
        return Model;
    }

    FString JsonString(const TSharedRef<FJsonObject>& Object)
    {
        FString Out; TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out); FJsonSerializer::Serialize(Object, Writer); return Out;
    }
    TArray<TSharedPtr<FJsonValue>> Vec(const FVector& V) { return { MakeShared<FJsonValueNumber>(V.X), MakeShared<FJsonValueNumber>(V.Y), MakeShared<FJsonValueNumber>(V.Z) }; }
}

// ------------------------------------------------------------------ verbs
FString ULiveLibrary::LiveRoot() { return FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("../../..")); }
FString ULiveLibrary::Resolve(const FString& Path) { return FPaths::IsRelative(Path) ? FPaths::ConvertRelativePathToFull(LiveRoot() / Path) : Path; }

UWorld* ULiveLibrary::GameWorld()
{
    if (!GEngine) return nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if ((Context.WorldType == EWorldType::Game || Context.WorldType == EWorldType::PIE) && Context.World()) return Context.World();
    return nullptr;
}

APawn* ULiveLibrary::Player() { UWorld* W = GameWorld(); return W ? UGameplayStatics::GetPlayerPawn(W, 0) : nullptr; }
FTransform ULiveLibrary::PlayerTransform() { APawn* P = Player(); return P ? P->GetActorTransform() : FTransform::Identity; }

FTransform ULiveLibrary::CameraTransform()
{
    UWorld* W = GameWorld(); APlayerController* PC = W ? UGameplayStatics::GetPlayerController(W, 0) : nullptr;
    return PC && PC->PlayerCameraManager ? FTransform(PC->PlayerCameraManager->GetCameraRotation(), PC->PlayerCameraManager->GetCameraLocation()) : FTransform::Identity;
}

FVector ULiveLibrary::AimPoint(float MaxDistance)
{
    UWorld* W = GameWorld(); if (!W) return FVector::ZeroVector;
    const FTransform C = CameraTransform(); const FVector From = C.GetLocation(), To = From + C.GetRotation().GetForwardVector() * MaxDistance;
    FCollisionQueryParams Q(SCENE_QUERY_STAT(LiveAim), true, Player());
    FHitResult Hit;
    return W->LineTraceSingleByChannel(Hit, From, To, ECC_Visibility, Q) ? Hit.ImpactPoint : GroundAt(To);
}

FVector ULiveLibrary::GroundAt(FVector Location)
{
    UWorld* W = GameWorld(); if (!W) return Location;
    FCollisionQueryParams Q(SCENE_QUERY_STAT(LiveGround), true, Player());
    for (TActorIterator<ALiveProp> It(W); It; ++It) Q.AddIgnoredActor(*It);
    FHitResult Hit;
    if (W->LineTraceSingleByChannel(Hit, Location + FVector(0, 0, 2000), Location - FVector(0, 0, 6000), ECC_Visibility, Q)) return Hit.ImpactPoint;
    return Location;
}

ALiveProp* ULiveLibrary::SpawnModel(const FString& Id, const FString& GlbPath, FVector Location, float Yaw, float Scale, const FString& Collision, const FString& Overlay)
{
    UWorld* W = GameWorld(); if (!W) return nullptr;
    FLiveModel& Model = LoadModel(GlbPath);
    if (!Model.Mesh) { UE_LOG(LogTemp, Error, TEXT("LIVE spawn %s failed: %s"), *Id, *Model.Error); return nullptr; }
    RemoveProp(Id);
    FActorSpawnParameters Spawn; Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    ALiveProp* Prop = W->SpawnActor<ALiveProp>(Location, FRotator(0, Yaw, 0), Spawn);
    if (!Prop) return nullptr;
    Prop->Id = Id; Prop->Source = GlbPath; Prop->Overlay = Overlay; Prop->Collision = Collision;
    Prop->Mesh->SetStaticMesh(Model.Mesh);
    // The actor's origin is where the model's base touches the ground: centre of the footprint, lowest point.
    const FVector Base(Model.Bounds.GetCenter().X, Model.Bounds.GetCenter().Y, Model.Bounds.Min.Z);
    Prop->Mesh->SetRelativeScale3D(FVector(Scale));
    Prop->Mesh->SetRelativeLocation(-Base * Scale);
    if (Collision == TEXT("none")) Prop->Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    else
    {
        if (Collision == TEXT("complex") && Model.Mesh->GetBodySetup())
        { Model.Mesh->GetBodySetup()->CollisionTraceFlag = CTF_UseComplexAsSimple; Model.Mesh->GetBodySetup()->CreatePhysicsMeshes(); }
        Prop->Mesh->SetCollisionProfileName(TEXT("BlockAll"));
    }
    Props.Add(Id, Prop);
    UE_LOG(LogTemp, Display, TEXT("LIVE spawn %s (%s) at %s yaw %.0f scale %.2f"), *Id, *GlbPath, *Location.ToString(), Yaw, Scale);
    return Prop;
}

ALiveProp* ULiveLibrary::FindProp(const FString& Id) { const TWeakObjectPtr<ALiveProp>* P = Props.Find(Id); return P ? P->Get() : nullptr; }

bool ULiveLibrary::RemoveProp(const FString& Id)
{
    TWeakObjectPtr<ALiveProp> P; if (!Props.RemoveAndCopyValue(Id, P) || !P.IsValid()) return false;
    P->Destroy(); return true;
}

TArray<FString> ULiveLibrary::PropIds() { TArray<FString> Out; for (auto& It : Props) if (It.Value.IsValid()) Out.Add(It.Key); return Out; }

FVector ULiveLibrary::ModelSize(const FString& GlbPath) { FLiveModel& M = LoadModel(GlbPath); return M.Mesh ? M.Bounds.GetSize() : FVector::ZeroVector; }

bool ULiveLibrary::TeleportPlayer(FVector Location, float Yaw)
{
    APawn* P = Player(); if (!P) return false;
    const FVector Ground = GroundAt(Location);
    if (Teleport) return Teleport(P, Ground, Yaw);
    return P->TeleportTo(Ground + FVector(0, 0, P->GetSimpleCollisionHalfHeight()), FRotator(0, Yaw, 0));
}

void ULiveLibrary::FixedStep(float Fps)
{
    if (Fps > 0.f) { FApp::SetFixedDeltaTime(1.0 / Fps); FApp::SetUseFixedTimeStep(true); }
    else FApp::SetUseFixedTimeStep(false);
}

bool ULiveLibrary::InputKey(const FString& Key, const FString& Event, float Value)
{
    APlayerController* PC = UGameplayStatics::GetPlayerController(GameWorld(), 0); if (!PC) return false;
    const FKey K(*Key); if (!K.IsValid()) return false;
    const EInputEvent E = Event == TEXT("press") ? IE_Pressed : Event == TEXT("release") ? IE_Released : IE_Axis;
    return PC->InputKey(FInputKeyEventArgs::CreateSimulated(K, E, E == IE_Released ? 0.f : Value, 1));
}

void ULiveLibrary::Say(const FString& Text, float Seconds) { Message = Text; MessageFrom = FPlatformTime::Seconds(); MessageUntil = MessageFrom + Seconds; UE_LOG(LogTemp, Display, TEXT("LIVE say: %s"), *Text); }

bool ULiveLibrary::CurrentMessage(FString& Text, float& Alpha)
{
    const double Now = FPlatformTime::Seconds(); if (Now > MessageUntil || Message.IsEmpty()) return false;
    Text = Message; Alpha = FMath::Clamp(float(FMath::Min(Now - MessageFrom, MessageUntil - Now) / .35), 0.f, 1.f); return true;
}

void ULiveLibrary::Screenshot(const FString& Path) { FScreenshotRequest::RequestScreenshot(Resolve(Path), true, false); }

bool ULiveLibrary::SaveOverlay(const FString& Name)
{
    TArray<TSharedPtr<FJsonValue>> List;
    for (auto& It : Props)
    {
        ALiveProp* P = It.Value.Get(); if (!P || P->Overlay != Name) continue;
        TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
        O->SetStringField(TEXT("id"), P->Id); O->SetStringField(TEXT("glb"), P->Source); O->SetStringField(TEXT("collision"), P->Collision);
        O->SetArrayField(TEXT("location"), Vec(P->GetActorLocation())); O->SetNumberField(TEXT("yaw"), P->GetActorRotation().Yaw);
        O->SetNumberField(TEXT("scale"), P->Mesh->GetRelativeScale3D().X);
        List.Add(MakeShared<FJsonValueObject>(O));
    }
    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>(); Root->SetStringField(TEXT("overlay"), Name); Root->SetArrayField(TEXT("props"), List);
    const FString Path = LiveRoot() / Settings().OverlayFolder / Name + TEXT(".json");
    return FFileHelper::SaveStringToFile(JsonString(Root) + TEXT("\n"), *Path);
}

int32 ULiveLibrary::LoadOverlay(const FString& Name)
{
    FString Text; TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text, *(LiveRoot() / Settings().OverlayFolder / Name + TEXT(".json"))) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root) return -1;
    int32 Count = 0;
    for (const TSharedPtr<FJsonValue>& V : Root->GetArrayField(TEXT("props")))
    {
        const TSharedPtr<FJsonObject> O = V->AsObject(); const TArray<TSharedPtr<FJsonValue>>& L = O->GetArrayField(TEXT("location"));
        if (SpawnModel(O->GetStringField(TEXT("id")), O->GetStringField(TEXT("glb")), FVector(L[0]->AsNumber(), L[1]->AsNumber(), L[2]->AsNumber()),
            O->GetNumberField(TEXT("yaw")), O->GetNumberField(TEXT("scale")), O->GetStringField(TEXT("collision")), Name)) ++Count;
    }
    UE_LOG(LogTemp, Display, TEXT("LIVE overlay %s: %d props"), *Name, Count);
    return Count;
}

// ------------------------------------------------------------------ bridge
namespace
{
    TUniquePtr<FHttpServerResponse> Json(const TSharedRef<FJsonObject>& O) { return FHttpServerResponse::Create(JsonString(O), TEXT("application/json")); }

    bool HandlePython(const FHttpServerRequest& Request, const FHttpResultCallback& Done)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
#if WITH_EDITOR
        IPythonScriptPlugin* Python = IPythonScriptPlugin::Get();
        if (Python && Python->IsPythonAvailable())
        {
            FPythonCommandEx Command;
            // The body is not null-terminated: convert it with its explicit length.
            FUTF8ToTCHAR Convert(reinterpret_cast<const ANSICHAR*>(Request.Body.GetData()), Request.Body.Num());
            Command.Command = FString(Convert.Length(), Convert.Get());
            Command.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;
            Command.FileExecutionScope = EPythonFileExecutionScope::Public;
            const bool bOk = Python->ExecPythonCommandEx(Command);
            Out->SetBoolField(TEXT("ok"), bOk); Out->SetStringField(TEXT("result"), Command.CommandResult);
            FString Log; for (const FPythonLogOutputEntry& E : Command.LogOutput) Log += E.Output + TEXT("\n");
            Out->SetStringField(TEXT("output"), Log);
        }
        else { Out->SetBoolField(TEXT("ok"), false); Out->SetStringField(TEXT("result"), TEXT("Python is not available in this build")); }
#else
        Out->SetBoolField(TEXT("ok"), false); Out->SetStringField(TEXT("result"), TEXT("Python needs an uncooked (editor) build"));
#endif
        Done(Json(Out)); return true;
    }

    bool HandleState(const FHttpServerRequest&, const FHttpResultCallback& Done)
    {
        TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
        const FTransform P = ULiveLibrary::PlayerTransform(), C = ULiveLibrary::CameraTransform();
        Out->SetArrayField(TEXT("player"), Vec(P.GetLocation())); Out->SetNumberField(TEXT("player_yaw"), P.Rotator().Yaw);
        Out->SetArrayField(TEXT("camera"), Vec(C.GetLocation())); Out->SetArrayField(TEXT("camera_rotation"), Vec(FVector(C.Rotator().Pitch, C.Rotator().Yaw, C.Rotator().Roll)));
        Out->SetArrayField(TEXT("aim"), Vec(ULiveLibrary::AimPoint()));
        TArray<TSharedPtr<FJsonValue>> Ids; for (const FString& Id : ULiveLibrary::PropIds()) Ids.Add(MakeShared<FJsonValueString>(Id));
        Out->SetArrayField(TEXT("props"), Ids);
        Out->SetNumberField(TEXT("fps"), 1. / FMath::Max(1e-4, FApp::GetDeltaTime()));
        Done(Json(Out)); return true;
    }
}

/** The bridge runs agent code, so it only ever listens on loopback: the game's DefaultEngine.ini must bind its port
 *  there ([HTTPServer.Listeners] +ListenerOverrides=(Port=N,BindAddress=localhost), or a loopback DefaultBindAddress). */
static bool LoopbackOnly(int32 Port)
{
    auto IsLoopback = [](const FString& Address) { return Address == TEXT("localhost") || Address == TEXT("127.0.0.1") || Address == TEXT("::1"); };
    TArray<FString> Overrides;
    GConfig->GetArray(TEXT("HTTPServer.Listeners"), TEXT("ListenerOverrides"), Overrides, GEngineIni);
    for (const FString& Entry : Overrides)
    {
        FString Address; int32 EntryPort = 0;
        if (FParse::Value(*Entry, TEXT("Port="), EntryPort) && EntryPort == Port && FParse::Value(*Entry, TEXT("BindAddress="), Address))
            return IsLoopback(Address.TrimChar(TEXT(')')));
    }
    FString Default;
    return GConfig->GetString(TEXT("HTTPServer.Listeners"), TEXT("DefaultBindAddress"), Default, GEngineIni) && IsLoopback(Default);
}

void AtelierLive::SetTeleport(TFunction<bool(APawn*, const FVector&, float)> InTeleport) { Teleport = MoveTemp(InTeleport); }

void AtelierLive::Start(UWorld* World)
{
    if (bStarted || !World || FParse::Param(FCommandLine::Get(), TEXT("nolive"))) return;
    bStarted = true;
    int32 Port = Settings().Port; FParse::Value(FCommandLine::Get(), TEXT("liveport="), Port);
    if (!LoopbackOnly(Port))
    {
        UE_LOG(LogTemp, Error, TEXT("LIVE bridge not started: port %d is not bound to loopback. Add +ListenerOverrides=(Port=%d,BindAddress=localhost) under [HTTPServer.Listeners] in the game's DefaultEngine.ini."), Port, Port);
        return;
    }
    FHttpServerModule& Http = FHttpServerModule::Get();
    Router = Http.GetHttpRouter(Port, false);
    if (Router)
    {
        Routes.Add(Router->BindRoute(FHttpPath(TEXT("/python")), EHttpServerRequestVerbs::VERB_POST, FHttpRequestHandler::CreateStatic(&HandlePython)));
        Routes.Add(Router->BindRoute(FHttpPath(TEXT("/state")), EHttpServerRequestVerbs::VERB_GET, FHttpRequestHandler::CreateStatic(&HandleState)));
        Http.StartAllListeners();
        UE_LOG(LogTemp, Display, TEXT("LIVE bridge listening on localhost:%d (POST /python, GET /state)"), Port);
    }
    else UE_LOG(LogTemp, Warning, TEXT("LIVE bridge: port %d unavailable (another game running?)"), Port);
#if WITH_EDITOR
    // The game's in-game helper module (PythonFolder/PythonModule), imported as `live` in the shared namespace.
    if (IPythonScriptPlugin* Python = IPythonScriptPlugin::Get(); Python && Python->IsPythonAvailable() && !Settings().PythonModule.IsEmpty())
    {
        FPythonCommandEx Boot; Boot.FileExecutionScope = EPythonFileExecutionScope::Public;
        Boot.Command = FString::Printf(TEXT("import sys\np=r'%s'\nif p not in sys.path: sys.path.insert(0, p)\nimport %s as live\n"), *(ULiveLibrary::LiveRoot() / Settings().PythonFolder), *Settings().PythonModule);
        Python->ExecPythonCommandEx(Boot);
        if (!Boot.CommandResult.IsEmpty() && Boot.CommandResult != TEXT("None")) UE_LOG(LogTemp, Warning, TEXT("LIVE python boot: %s"), *Boot.CommandResult);
    }
#endif
    // Everything accepted so far comes back on every start.
    TArray<FString> Files; IFileManager::Get().FindFiles(Files, *(ULiveLibrary::LiveRoot() / Settings().OverlayFolder / TEXT("*.json")), true, false);
    for (const FString& File : Files) ULiveLibrary::LoadOverlay(FPaths::GetBaseFilename(File));
}
