#include "MaterialInputAudit.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpression.h"
#include "MaterialExpressionIO.h"

namespace
{
FMaterialInputAuditResult AuditInput(const FExpressionInput* Input)
{
    FMaterialInputAuditResult Result;
    if (!Input || !IsValid(Input->Expression))
    {
        Result.Error = TEXT("Material input is absent or unconnected");
        return Result;
    }
    if (!Input->Expression->GetOutputs().IsValidIndex(Input->OutputIndex))
    {
        Result.Error = TEXT("Material input selects an invalid source output");
        return Result;
    }
    Result.SourcePath = Input->Expression->GetPathName();
    Result.OutputIndex = Input->OutputIndex;
    Result.Masks = {Input->Mask, Input->MaskR, Input->MaskG, Input->MaskB, Input->MaskA};
    return Result;
}
}

FMaterialInputAuditResult UMaterialInputAudit::ReadInput(UMaterialExpression* Expression, int32 InputIndex)
{
    if (!IsValid(Expression) || InputIndex < 0 || InputIndex >= Expression->CountInputs())
    {
        FMaterialInputAuditResult Result;
        Result.Error = TEXT("Invalid material expression or input index");
        return Result;
    }
    return AuditInput(Expression->GetInput(InputIndex));
}

FMaterialInputAuditResult UMaterialInputAudit::ReadPropertyInput(UMaterial* Material, EMaterialProperty Property)
{
    if (!IsValid(Material) || Property < 0 || Property >= MP_MAX)
    {
        FMaterialInputAuditResult Result;
        Result.Error = TEXT("Invalid material or property");
        return Result;
    }
    return AuditInput(Material->GetExpressionInputForProperty(Property));
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Materials/MaterialExpressionCustom.h"
#include "Materials/MaterialExpressionVertexColor.h"
#include "UObject/Package.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMaterialInputAuditReadOnlyTest, "YorimichiV2.Authoring.MaterialInputAudit",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FMaterialInputAuditReadOnlyTest::RunTest(const FString& Parameters)
{
    UMaterialExpressionVertexColor* Source = NewObject<UMaterialExpressionVertexColor>();
    UMaterialExpressionCustom* Target = NewObject<UMaterialExpressionCustom>();
    Target->Inputs.SetNum(2);
    Target->Inputs[0].Input.Connect(0, Source);
    Target->Inputs[1].Input.Connect(4, Source);
    Target->Inputs[1].Input.SetMask(1, 0, 0, 0, 1);
    const bool WasDirty = Target->GetOutermost()->IsDirty();

    const FMaterialInputAuditResult First = UMaterialInputAudit::ReadInput(Target, 0);
    const FMaterialInputAuditResult Second = UMaterialInputAudit::ReadInput(Target, 1);
    TestTrue(TEXT("both connected inputs are readable"), First.Error.IsEmpty() && Second.Error.IsEmpty());
    TestEqual(TEXT("same source is retained"), Second.SourcePath, Source->GetPathName());
    TestEqual(TEXT("first input selects RGB"), First.OutputIndex, 0);
    TestEqual(TEXT("second input selects alpha"), Second.OutputIndex, 4);
    TestTrue(TEXT("second input retains its component mask"), Second.Masks == TArray<int32>({1, 0, 0, 0, 1}));
    TestEqual(TEXT("reading does not dirty the package"), Target->GetOutermost()->IsDirty(), WasDirty);
    TestEqual(TEXT("reading does not rewire the input"), Target->Inputs[1].Input.OutputIndex, 4);
    TestFalse(TEXT("negative input refuses"), UMaterialInputAudit::ReadInput(Target, -1).Error.IsEmpty());
    TestFalse(TEXT("missing input refuses"), UMaterialInputAudit::ReadInput(Target, 2).Error.IsEmpty());
    Target->Inputs[1].Input.Expression = nullptr;
    TestFalse(TEXT("unconnected input refuses"), UMaterialInputAudit::ReadInput(Target, 1).Error.IsEmpty());

    UMaterial* Material = NewObject<UMaterial>();
    FExpressionInput* Root = Material->GetExpressionInputForProperty(MP_BaseColor);
    TestNotNull(TEXT("base colour has a native input"), Root);
    if (!Root) return false;
    Root->Connect(0, Source);
    Root->SetMask(1, 1, 1, 1, 0);
    const FMaterialInputAuditResult RGB = UMaterialInputAudit::ReadPropertyInput(Material, MP_BaseColor);
    Root->SetMask(1, 1, 0, 0, 0);
    const bool RootWasDirty = Material->GetOutermost()->IsDirty();
    const FMaterialInputAuditResult Red = UMaterialInputAudit::ReadPropertyInput(Material, MP_BaseColor);
    TestTrue(TEXT("both root selections are readable"), RGB.Error.IsEmpty() && Red.Error.IsEmpty());
    TestEqual(TEXT("root source is retained"), Red.SourcePath, Source->GetPathName());
    TestEqual(TEXT("root output is retained"), Red.OutputIndex, 0);
    TestTrue(TEXT("RGB root retains its mask"), RGB.Masks == TArray<int32>({1, 1, 1, 1, 0}));
    TestTrue(TEXT("red root retains its mask"), Red.Masks == TArray<int32>({1, 1, 0, 0, 0}));
    TestEqual(TEXT("root read does not dirty the package"), Material->GetOutermost()->IsDirty(), RootWasDirty);
    TestEqual(TEXT("root read does not rewire the input"), Root->OutputIndex, 0);
    TestEqual(TEXT("root read does not change its mask"), Root->MaskG, 0);
    TestFalse(TEXT("null material refuses"), UMaterialInputAudit::ReadPropertyInput(nullptr, MP_BaseColor).Error.IsEmpty());
    TestFalse(TEXT("invalid property refuses"), UMaterialInputAudit::ReadPropertyInput(Material, MP_MAX).Error.IsEmpty());
    Root->Expression = nullptr;
    TestFalse(TEXT("unconnected root refuses"), UMaterialInputAudit::ReadPropertyInput(Material, MP_BaseColor).Error.IsEmpty());
    return true;
}
#endif
