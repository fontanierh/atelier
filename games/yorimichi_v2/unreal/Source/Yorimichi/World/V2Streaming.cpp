#include "World/V2Streaming.h"
#include "Engine/World.h"
#include "WorldPartition/WorldPartition.h"

namespace
{
// Visit every numeric property named LoadingRange in Container (of Struct) and in the structs, arrays and Root's own
// subobjects it holds, to a small depth: the spatial hash keeps them in Grids[], the runtime hash set in its
// RuntimePartitions[]' partition objects. Visit gets the property path, the property and its value address.
void VisitRanges(const UObject* Root, const UStruct* Struct, void* Container, const FString& Path, int32 Depth,
                 TFunctionRef<void(const FString&, FNumericProperty*, void*)> Visit)
{
    if (Depth > 4) return;
    for (TFieldIterator<FProperty> It(Struct); It; ++It)
    {
        FProperty* Property = *It;
        void* Value = Property->ContainerPtrToValuePtr<void>(Container);
        const FString Here = Path + TEXT(".") + Property->GetName();
        if (FNumericProperty* Number = CastField<FNumericProperty>(Property))
        {
            if (Property->GetFName() == TEXT("LoadingRange")) Visit(Here, Number, Value);
        }
        else if (FStructProperty* Inner = CastField<FStructProperty>(Property))
        {
            VisitRanges(Root, Inner->Struct, Value, Here, Depth + 1, Visit);
        }
        else if (FObjectProperty* Object = CastField<FObjectProperty>(Property))
        {
            UObject* Held = Object->GetObjectPropertyValue(Value);
            if (Held && Held->IsIn(Root)) VisitRanges(Root, Held->GetClass(), Held, Here, Depth + 1, Visit);
        }
        else if (FArrayProperty* Array = CastField<FArrayProperty>(Property))
        {
            FScriptArrayHelper Items(Array, Value);
            for (int32 I = 0; I < Items.Num(); ++I)
            {
                const FString Item = FString::Printf(TEXT("%s[%d]"), *Here, I);
                if (FStructProperty* Element = CastField<FStructProperty>(Array->Inner))
                    VisitRanges(Root, Element->Struct, Items.GetRawPtr(I), Item, Depth + 1, Visit);
                else if (FObjectProperty* Ref = CastField<FObjectProperty>(Array->Inner))
                    if (UObject* Held = Ref->GetObjectPropertyValue(Items.GetRawPtr(I)); Held && Held->IsIn(Root))
                        VisitRanges(Root, Held->GetClass(), Held, Item, Depth + 1, Visit);
            }
        }
    }
}

UObject* RuntimeHash(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    UWorldPartition* Partition = World ? World->GetWorldPartition() : nullptr;
    FObjectProperty* Property = FindFProperty<FObjectProperty>(UWorldPartition::StaticClass(), TEXT("RuntimeHash"));
    return Partition && Property ? Property->GetObjectPropertyValue_InContainer(Partition) : nullptr;
}

// The HLOD layers keep their own ranges (0 = always loaded).
bool IsHlod(const FString& Path) { return Path.Contains(TEXT("HLOD")); }

double Read(FNumericProperty* Number, void* Value)
{
    return Number->IsFloatingPoint() ? Number->GetFloatingPointPropertyValue(Value) : double(Number->GetSignedIntPropertyValue(Value));
}
}

float UV2Streaming::IslandRangeCm()
{
    return 300000.f;
}

float UV2Streaming::MinLoadingRange(const UObject* WorldContext)
{
    UObject* Hash = RuntimeHash(WorldContext);
    if (!Hash) return 0.f;
    double Smallest = -1.;
    VisitRanges(Hash, Hash->GetClass(), Hash, FString(), 0, [&](const FString& Path, FNumericProperty* Number, void* Value)
    {
        if (!IsHlod(Path)) Smallest = Smallest < 0. ? Read(Number, Value) : FMath::Min(Smallest, Read(Number, Value));
    });
    return Smallest < 0. ? 0.f : float(Smallest);
}

FString UV2Streaming::DescribeLoadingRanges(const UObject* WorldContext)
{
    UObject* Hash = RuntimeHash(WorldContext);
    if (!Hash) return FString();
    FString Lines = Hash->GetClass()->GetName() + TEXT("\n");
    VisitRanges(Hash, Hash->GetClass(), Hash, Hash->GetClass()->GetName(), 0,
                [&](const FString& Path, FNumericProperty* Number, void* Value)
                {
                    Lines += FString::Printf(TEXT("%s=%.0f\n"), *Path, Read(Number, Value));
                });
    return Lines;
}

int32 UV2Streaming::SetLoadingRanges(const UObject* WorldContext, float RangeCm)
{
    UObject* Hash = RuntimeHash(WorldContext);
    if (!Hash || RangeCm <= 0.f) return 0;
    Hash->Modify();
    int32 Changed = 0;
    VisitRanges(Hash, Hash->GetClass(), Hash, FString(), 0, [&](const FString& Path, FNumericProperty* Number, void* Value)
    {
        if (IsHlod(Path)) return;
        if (Number->IsFloatingPoint()) Number->SetFloatingPointPropertyValue(Value, RangeCm);
        else Number->SetIntPropertyValue(Value, int64(RangeCm));
        ++Changed;
    });
    if (Changed) Hash->MarkPackageDirty();
    return Changed;
}
