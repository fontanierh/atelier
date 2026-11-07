#include "ImportProvenance.h"
#include "InterchangeAssetImportData.h"

bool UImportProvenance::RenameInterchangeNode(UAssetImportData* Data, const FString& NodeId)
{
    UInterchangeAssetImportData* Interchange = Cast<UInterchangeAssetImportData>(Data);
    if (!Interchange)
    {
        return false;
    }
    Interchange->Modify();
    Interchange->NodeUniqueID = NodeId;
    return true;
}
