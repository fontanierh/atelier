#include "JapanFootstepSet.h"

const FJapanFootstepBank* UJapanFootstepSet::Find(FName Surface) const
{
    const FJapanFootstepBank* Bank=Surfaces.Find(Surface);
    if(Bank && Bank->Steps.Num()) return Bank;
    Bank=Surfaces.Find(DefaultSurface);
    return Bank && Bank->Steps.Num() ? Bank : nullptr;
}
