#include "MaterialInputAudit.h"
#include "Materials/MaterialExpression.h"
#include "MaterialExpressionIO.h"

FMaterialInputAuditResult UMaterialInputAudit::ReadInput(UMaterialExpression* Expression, int32 InputIndex)
{
    FMaterialInputAuditResult Result;
    if (!IsValid(Expression) || InputIndex < 0 || InputIndex >= Expression->CountInputs())
    {
        Result.Error = TEXT("Invalid material expression or input index");
        return Result;
    }
    const FExpressionInput* Input = Expression->GetInput(InputIndex);
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
    return true;
}
#endif
