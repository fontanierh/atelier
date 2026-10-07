#include "JapanNetwork.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanEndpointTest, "Yorimichi.Network.JoinEndpoint",
    EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanEndpointTest::RunTest(const FString&)
{
    struct FCase { const TCHAR* Input; const TCHAR* Expected; };
    for (const FCase& Case : { FCase{TEXT(" 100.64.12.3 "), TEXT("100.64.12.3:7777")},
            FCase{TEXT("shared-device.example.ts.net:8888"), TEXT("shared-device.example.ts.net:8888")},
            FCase{TEXT("localhost:1"), TEXT("localhost:1")}, FCase{TEXT("host:65535"), TEXT("host:65535")} })
    {
        FString Endpoint, Error;
        TestTrue(Case.Input, JapanNetwork::ParseEndpoint(Case.Input, Endpoint, Error));
        TestEqual(TEXT("Normalized host and port"), Endpoint, FString(Case.Expected));
        TestTrue(TEXT("No error for valid input"), Error.IsEmpty());
    }
    for (const TCHAR* Input : { TEXT(""), TEXT("host?listen"), TEXT("host/path"), TEXT("https://host"),
            TEXT("host:7777?game=Something"), TEXT("host:7.7"), TEXT("host:-1"), TEXT("host:+1"),
            TEXT("host:0"), TEXT("host:65536"), TEXT("host:"), TEXT("host:77:77"),
            TEXT("host..name"), TEXT("-host"), TEXT("host-"), TEXT("host name"), TEXT("[::1]")} )
    {
        FString Endpoint, Error;
        TestFalse(Input, JapanNetwork::ParseEndpoint(Input, Endpoint, Error));
        TestFalse(TEXT("Rejected input explains the failure"), Error.IsEmpty());
    }
    return true;
}
#endif
