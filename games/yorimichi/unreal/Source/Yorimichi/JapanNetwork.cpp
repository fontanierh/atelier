#include "JapanNetwork.h"
#include "Components/CapsuleComponent.h"
#include "AtelierData.h"
#include "BotwRider.h"
#include "CairoCharacter.h"
#include "JapanWorld.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Engine/NetDriver.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"
#include "Misc/OutputDeviceRedirector.h"
#include <cstdlib>
#include <cstdio>

#ifndef YORIMICHI_NETWORK_BUILD_ID
#define YORIMICHI_NETWORK_BUILD_ID "unprepared"
#endif

namespace JapanNetwork
{
namespace
{
#if PLATFORM_MAC
bool bFailedExit = false;
void PreserveFailedExitStatus()
{
    // Runs after the ordinary engine shutdown. No UObject, delegate or log is
    // accessed here. UE keeps module code loaded at shutdown; packaged code is monolithic.
    if (bFailedExit) { std::fflush(nullptr); std::_Exit(1); }
}
#endif
}

void RequestFailureExit()
{
#if PLATFORM_MAC
    // Mac inherits the generic RequestExitWithStatus, which discards ReturnCode.
    // Register only on failure so an ordinary Solo/listen shutdown still returns zero.
    if (!bFailedExit)
    {
        bFailedExit = true;
        if (std::atexit(PreserveFailedExitStatus) != 0)
        {
            UE_LOG(LogTemp, Error, TEXT("Could not register the network failure exit status"));
            if (GLog) GLog->Flush();
            std::_Exit(1);
        }
    }
    FPlatformMisc::RequestExit(false);
#else
    FPlatformMisc::RequestExitWithStatus(false, 1);
#endif
}

const TCHAR* Map() { return TEXT("/Game/Japan/Maps/Slice"); }
bool IsOnline(const UWorld* World) { return World && World->GetNetMode() != NM_Standalone; }

bool Allows(UWorld* World, EActivity Activity)
{
    if (!IsOnline(World)) return true;
    switch (Activity)
    {
    case EActivity::Horse:
    case EActivity::Race:
    case EActivity::WorldEdit:
        return false;
    }
    return false;
}

bool IsTailnetIPv4(const FString& Address)
{
    TArray<FString> Octets; Address.ParseIntoArray(Octets, TEXT("."), false);
    if (Octets.Num() != 4) return false;
    int32 Parts[4];
    for (int32 I = 0; I < 4; ++I)
    {
        if (Octets[I].IsEmpty() || Octets[I].Len() > 3) return false;
        for (TCHAR C : Octets[I]) if (C < '0' || C > '9') return false;
        Parts[I] = FCString::Atoi(*Octets[I]);
        if (Parts[I] > 255) return false;
    }
    return Parts[0] == 100 && Parts[1] >= 64 && Parts[1] <= 127;
}

FString LocalEndpoint(UWorld* World)
{
    // The active driver reports the address actually bound, including its real port.
    if (World && World->GetNetMode() != NM_Client)
        if (UNetDriver* Driver = World->GetNetDriver()) return Driver->LowLevelGetNetworkNumber();
    FString Address, Error;
    return PrivateHostAddress(Address, Error) ? FString::Printf(TEXT("%s:%d"), *Address, World ? World->URL.Port : 7777) : FString();
}

bool ParseEndpoint(const FString& Input, FString& Endpoint, FString& Error)
{
    Endpoint = Input.TrimStartAndEnd();
    Error.Reset();
    if (Endpoint.IsEmpty() || Endpoint.Len() > 253)
    { Error = TEXT("Enter the host's device name or IP address, optionally followed by :7777."); return false; }
    // Tailscale's IPv4 and full shared-device DNS names work without special URL interpretation.
    FString Host = Endpoint, Port;
    if (Endpoint.Split(TEXT(":"), &Host, &Port))
    {
        bool bDigits = !Port.IsEmpty();
        for (TCHAR C : Port) bDigits &= C >= '0' && C <= '9';
        if (!bDigits || Port.Len() > 5)
        { Error = TEXT("The game port must be a number from 1 to 65535."); return false; }
        const int32 Value = FCString::Atoi(*Port);
        if (Value < 1 || Value > 65535)
        { Error = TEXT("The game port must be a number from 1 to 65535."); return false; }
    }
    if (Host.IsEmpty() || !FChar::IsAlnum(Host[0]) || !FChar::IsAlnum(Host[Host.Len()-1]))
    { Error = TEXT("Use an IPv4 address or the full device DNS name."); return false; }
    for (TCHAR C : Host)
        if (!((C >= 'a' && C <= 'z') || (C >= 'A' && C <= 'Z') || (C >= '0' && C <= '9') || C == '.' || C == '-'))
        { Error = TEXT("Use only the host name or IPv4 address; do not include a URL or travel options."); return false; }
    TArray<FString> Labels;
    Host.ParseIntoArray(Labels, TEXT("."), false);
    for (const FString& Label : Labels)
        if (Label.IsEmpty() || Label.Len() > 63 || Label.StartsWith(TEXT("-")) || Label.EndsWith(TEXT("-")))
        { Error = TEXT("The host name contains an invalid label."); return false; }
    if (Port.IsEmpty()) Endpoint += TEXT(":7777");
    return true;
}

static FString HashFile(const FString& Path)
{
    TUniquePtr<FArchive> File(IFileManager::Get().CreateFileReader(*Path));
    if (!File) return FString();
    FSHA1 Hash;
    uint8 Buffer[64 * 1024];
    while (!File->AtEnd() && !File->IsError())
    {
        const int64 Count = FMath::Min<int64>(sizeof(Buffer), File->TotalSize() - File->Tell());
        if (Count <= 0) break;
        File->Serialize(Buffer, Count);
        Hash.Update(Buffer, uint32(Count));
    }
    if (File->IsError()) return FString();
    Hash.Final();
    uint8 Digest[FSHA1::DigestSize]; Hash.GetHash(Digest);
    return BytesToHex(Digest, UE_ARRAY_COUNT(Digest)).ToLower();
}

bool Identity(FString& Signature, FString& Error)
{
    static bool bChecked = false;
    static FString CachedSignature, CachedError;
    if (!bChecked)
    {
        bChecked = true;
        FString Text;
        TSharedPtr<FJsonObject> Manifest;
        FString Root = AtelierDataPath(TEXT(""));
        FPaths::NormalizeDirectoryName(Root);
        Root += TEXT("/");
        const FString Path = Root / TEXT("Network/session.json");
        if (!FFileHelper::LoadFileToString(Text, *Path) ||
            !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Manifest) || !Manifest)
            CachedError = TEXT("This build has no multiplayer content manifest. Install a complete matching multiplayer build.");
        else
        {
            double Version = 0;
            FString Build, ContentSignature, Assets;
            const TArray<TSharedPtr<FJsonValue>>* Files = nullptr;
            if (!Manifest->TryGetNumberField(TEXT("protocol"), Version) || Version != Protocol ||
                !Manifest->TryGetStringField(TEXT("code"), Build) || Build != UTF8_TO_TCHAR(YORIMICHI_NETWORK_BUILD_ID) ||
                !Manifest->TryGetStringField(TEXT("assets"), Assets) || Assets.Len() != 40 ||
                !Manifest->TryGetStringField(TEXT("signature"), ContentSignature) || ContentSignature.Len() != 40 ||
                !Manifest->TryGetArrayField(TEXT("files"), Files) || Files->IsEmpty() || Files->Num() > 20000)
                CachedError = TEXT("The multiplayer code and content manifest do not match. Install the complete build again.");
            else
            {
                TSet<FString> Expected;
                TArray<FString> Records;
                for (const TSharedPtr<FJsonValue>& Entry : *Files)
                {
                    const TSharedPtr<FJsonObject>* Item = nullptr;
                    FString Relative, Digest;
                    if (!Entry->TryGetObject(Item) || !Item || !(*Item)->TryGetStringField(TEXT("path"), Relative) ||
                        !(*Item)->TryGetStringField(TEXT("sha1"), Digest) || Relative.IsEmpty() || !FPaths::IsRelative(Relative) ||
                        Relative.Contains(TEXT("..")) || Relative.Contains(TEXT("\n")) || Relative.Contains(TEXT("\r")) || Relative.Contains(TEXT("\\")) || Expected.Contains(Relative) ||
                        Digest.Len() != 40 || HashFile(Root / Relative) != Digest)
                    { CachedError = TEXT("Gameplay data is missing or changed. Both players need the same complete build."); break; }
                    Expected.Add(Relative);
                    // FString cannot contain the canonical embedded NUL: append it to the hash below.
                    Records.Add(Relative + TEXT("\n") + Digest);
                }
                TArray<FString> Actual;
                IFileManager::Get().FindFilesRecursive(Actual, *Root, TEXT("*"), true, false);
                for (FString File : Actual)
                {
                    FPaths::MakePathRelativeTo(File, *Root);
                    const FString Name = FPaths::GetCleanFilename(File);
                    if (File.StartsWith(TEXT("Network/")) || Name.Equals(TEXT(".DS_Store"), ESearchCase::IgnoreCase) ||
                        Name.Equals(TEXT("Thumbs.db"), ESearchCase::IgnoreCase)) continue;
                    if (!Expected.Contains(File))
                    { CachedError = TEXT("Unexpected gameplay data is installed. Install a clean matching multiplayer build."); break; }
                }
                if (CachedError.IsEmpty())
                {
                    Records.Sort([](const FString& A, const FString& B) { return A.Compare(B, ESearchCase::CaseSensitive) < 0; });
                    FSHA1 DataHash;
                    for (const FString& Record : Records)
                    {
                        FString Relative, Digest;
                        Record.Split(TEXT("\n"), &Relative, &Digest);
                        FTCHARToUTF8 Name(*Relative), Value(*(Digest + TEXT("\n")));
                        DataHash.Update(reinterpret_cast<const uint8*>(Name.Get()), Name.Length());
                        const uint8 Zero = 0; DataHash.Update(&Zero, 1);
                        DataHash.Update(reinterpret_cast<const uint8*>(Value.Get()), Value.Length());
                    }
                    DataHash.Final(); uint8 DataDigest[20]; DataHash.GetHash(DataDigest);
                    const FString Payload = FString::Printf(TEXT("%d\n%s\n%s\n%s\n"), Protocol, *Build, *Assets,
                        *BytesToHex(DataDigest, 20).ToLower());
                    FTCHARToUTF8 Utf8(*Payload); uint8 Digest[20];
                    FSHA1::HashBuffer(Utf8.Get(), Utf8.Length(), Digest);
                    if (BytesToHex(Digest, 20).ToLower() != ContentSignature)
                        CachedError = TEXT("The multiplayer content manifest is inconsistent. Install the complete build again.");
                }
                if (CachedError.IsEmpty()) CachedSignature = FString::Printf(TEXT("%d:%s:%s"), Protocol, *Build, *ContentSignature);
            }
        }
        UE_LOG(LogTemp, Display, TEXT("NETWORK identity %s"), CachedError.IsEmpty() ? *CachedSignature : *CachedError);
    }
    Signature = CachedSignature;
    Error = CachedError;
    return Error.IsEmpty() && !Signature.IsEmpty();
}

AJapanWorld* FindWorld(UWorld* World)
{
    if (!World) return nullptr;
    TActorIterator<AJapanWorld> It(World);
    return It ? *It : nullptr;
}
AJapanWorld* EnsureWorld(UWorld* World)
{
    if (AJapanWorld* Existing = FindWorld(World)) return Existing;
    return World ? World->SpawnActor<AJapanWorld>() : nullptr;
}
bool IsPlayableRider(const FString& Name)
{
    return (Name == ACairoCharacter::BotwName() && ACairoCharacter::HasBotw()) || ABotwRider::Available().Contains(Name);
}
FString DefaultRider()
{
    const FString Requested = ABotwRider::Requested();
    return IsPlayableRider(Requested) ? Requested : ACairoCharacter::BotwName();
}
}

void JapanNetwork::ConfigurePlayerCollision(UCapsuleComponent* Capsule)
{
    if (Capsule) Capsule->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
}
