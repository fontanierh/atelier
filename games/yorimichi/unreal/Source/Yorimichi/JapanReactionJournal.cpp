#include "JapanReactionJournal.h"

namespace JapanReactionCodec
{
// Fixed vocabulary: peer content identity binds this ordering. Never decode a
// peer-controlled FString length or create a new FName from network text.
const FName Actions[] = {NAME_None, TEXT("HitF"), TEXT("HitB"), TEXT("HitL"), TEXT("HitR"),
    TEXT("HitMF"), TEXT("HitMB"), TEXT("HitML"), TEXT("HitMR"),
    TEXT("KnockF"), TEXT("KnockB"), TEXT("KnockL"), TEXT("KnockR"),
    TEXT("GuardHit"), TEXT("GuardBreak"), TEXT("SwordGuardHit"), TEXT("SwordGuardBreak")};
}

bool FJapanScheduledReaction::Serialize(FArchive& Ar)
{
    const bool Loading = Ar.IsLoading();
    uint8 ActionIndex = 255;
    if (Loading) *this = FJapanScheduledReaction();
    else
    {
        if (!IsValid()) { Ar.SetError(); return false; }
        for (int32 I = 0; I < UE_ARRAY_COUNT(JapanReactionCodec::Actions); ++I)
            if (JapanReactionCodec::Actions[I] == Value.Action) { ActionIndex = uint8(I); break; }
        if (ActionIndex == 255) { Ar.SetError(); return false; }
    }
    FJapanScheduledReaction Decoded;
    auto& Item = Loading ? Decoded : *this;
    Ar << Item.Epoch << Item.Sequence << Item.Resolved.Generation << Item.Resolved.Time;
    uint32 Count = Item.Value.Bytes.Num();
    Ar.SerializeIntPacked(Count);
    if (Ar.IsError() || !Item.Epoch || !Item.Sequence || !Item.Resolved.IsValid() ||
        !Count || Count > FJapanReactionValue::MaximumBytes)
    { Ar.SetError(); return false; }
    if (Loading) Item.Value.Bytes.SetNumUninitialized(Count);
    Ar.Serialize(Item.Value.Bytes.GetData(), Count);
    if (Ar.IsError()) return false;
    Ar << ActionIndex;
    if (ActionIndex >= UE_ARRAY_COUNT(JapanReactionCodec::Actions)) { Ar.SetError(); return false; }
    if (Loading) Item.Value.Action = JapanReactionCodec::Actions[ActionIndex];
    if (Ar.IsError() || !Item.IsValid()) { Ar.SetError(); return false; }
    if (Loading) *this = MoveTemp(Decoded);
    return true;
}
