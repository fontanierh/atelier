"""Source/interface checks for the bounded native motion owners; native build remains a separate guarded check."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate'
CPP = (SOURCE / 'Private/SkateMotionData.cpp').read_text()
HEADER = (SOURCE / 'Public/SkateDataLibrary.h').read_text()


def function(name):
    """Extract a function while ignoring C++ string/comment braces."""
    start = CPP.index(name + '(')
    begin = CPP.index('{', start)
    tokens = re.finditer(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|[{}]', CPP[begin:])
    depth = 0
    for token in tokens:
        if token[0] == '{': depth += 1
        elif token[0] == '}':
            depth -= 1
            if not depth: return CPP[start:begin + token.end()]
    raise AssertionError('Missing function end: ' + name)


LOAD = function('LoadMotionImport')
BANK = function('WriteMotionBank')
INDEX = function('WriteMotionIndex')
BANK_ENTRY = function('USkateDataLibrary::ImportMotionBank')
INDEX_ENTRY = function('USkateDataLibrary::ImportMotionIndex')
LEGACY = function('USkateDataLibrary::ImportMotion')


def test_reflected_single_output_abis_and_output_identity_guards():
    assert ('UFUNCTION(BlueprintCallable, Category="Skate Data") static bool ImportMotionBank('
            'const FString& PackageFolder, int32 BankIndex, const FString& ExpectedPackage, FString& Error);') in HEADER
    assert ('UFUNCTION(BlueprintCallable, Category="Skate Data") static bool ImportMotionIndex('
            'const FString& PackageFolder, const FString& ExpectedPackage, FString& Error);') in HEADER
    assert 'BankIndex<0||!MotionOutput(ExpectedPackage,FString::Printf(TEXT("Bank_%03d"),BankIndex))' in BANK_ENTRY
    assert '!=TEXT("Banks")' in BANK_ENTRY
    assert '!MotionOutput(ExpectedPackage,TEXT("MotionData"))' in INDEX_ENTRY
    output = function('MotionOutput')
    assert 'StartsWith(TEXT("/Game/"))' in output and 'IsValidLongPackageName(Package)' in output
    for entry in (BANK_ENTRY, INDEX_ENTRY):
        assert entry.index('Expected package must name exactly') < entry.index('LoadMotionImport(')
        assert 'Motion import requires an editor build' in entry
        assert entry.index('LoadMotionImport(') < entry.index('return WriteMotion')


def test_bank_uses_original_order_conversion_and_one_save_without_sibling_access():
    assert 'constexpr int32 MotionChunkSize=128;' in CPP
    assert 'BankIndex<0||BankIndex>=MotionBankCount(Source)' in BANK
    assert BANK.index('Motion bank index is out of range') < BANK.index('Asset<USkateMotionBank>')
    assert 'const int32 Begin=BankIndex*MotionChunkSize;' in BANK
    assert 'int64(Begin)+MotionChunkSize,int64(Frames.clips.size())' in BANK
    assert 'for(const auto& Pair:Frames.clips)' in BANK
    assert 'if(Index>=End)break;' in BANK
    assert 'if(Index>=Begin)Bank->Clips.Add(ToAsset(*Pair.second));' in BANK
    assert BANK.count('Asset<USkateMotionBank>(ExpectedPackage)') == 1
    assert BANK.count('Save(') == 1 and 'Save(Bank.Get(),Error)' in BANK
    assert 'MotionData' not in BANK and 'LoadObject' not in BANK
    assert 'WriteMotionIndex' not in BANK_ENTRY


def test_index_requires_exact_bank_membership_and_full_typed_comparison_before_sole_save():
    for statement in (
        'Data->SchemaVersion=USkateMotionData::CurrentSchema;Data->bHasTrajectory=Frames.rig.has_trajectory;',
        'Data->Bones=Map(Frames.rig.bones,[](const auto& V){return ToAsset(V);});',
        'Data->ReferencePoses=Map(Frames.rig.poses,[](const auto& V){return ToAsset(V);});',
        'Data->Metadata=Metadata;Data->Banks.Reset();',
        'for(int32 B=0;B<MotionBankCount(Source);++B)',
        'MotionBankPackage(FPackageName::GetLongPackagePath(ExpectedPackage),B)',
        'LoadObject<USkateMotionBank>',
        '!Bank||Bank->GetOutermost()->GetName()!=Package||Bank->Clips.Num()!=Count',
        'Held.Emplace(Bank);Banks.Add(Bank);Data->Banks.Add(TSoftObjectPtr<USkateMotionBank>(Bank));',
        'Banks[Index/MotionChunkSize]->Clips[Index%MotionChunkSize]',
        'Clip.Name!=Text(Pair.second->name)||Clip.Bank!=int32(Pair.second->bank)||Clip.SourceRecord!=int64(Pair.second->record)',
        'DecodeSkateMotion(*Data,Banks,Decoded,SimulationError)',
        'CompareMotion(Source,*Decoded,ComparedFrames,Samples,SimulationError)',
    ):
        assert statement in INDEX
    assert INDEX.index('LoadObject<USkateMotionBank>') < INDEX.index('DecodeSkateMotion(') < INDEX.index('return Save(')
    assert INDEX.count('Save(') == 1 and 'Save(Data.Get(),Error)' in INDEX
    assert INDEX.count('Asset<') == 1 and 'Asset<USkateMotionData>(ExpectedPackage)' in INDEX
    assert 'WriteMotionBank' not in INDEX_ENTRY


def test_original_metadata_validation_and_conversion_are_shared_before_any_author_writes():
    for statement in (
        'skate::LoadGameplayResources(std::filesystem::u8path(String(PackageFolder)),Resources,SimulationError)',
        'for(int32 B=0;B<2;++B)',
        'metadata/bank-%d.skate', 'Bank.Load(Bytes,SimulationError)',
        'auto Typed=ToAsset(Bank);', 'AttributeTargets(Typed,Bank,Frames.rig,SimulationError)',
        'Metadata.Add(MoveTemp(Typed));',
    ):
        assert statement in LOAD
    assert 'Save(' not in LOAD and 'Asset<' not in LOAD
    assert CPP.count('auto Typed=ToAsset(Bank);') == 1
    assert CPP.count('Bank->Clips.Add(ToAsset(*Pair.second));') == 1
    assert LEGACY.index('LoadMotionImport(') < LEGACY.index('WriteMotionBank(') < LEGACY.index('WriteMotionIndex(')


def test_only_legacy_whole_import_can_scan_or_retire_content():
    selected = LOAD + BANK + INDEX + BANK_ENTRY + INDEX_ENTRY
    for operation in ('FindFiles', 'IFileManager', 'Delete(', 'GetAssetRegistry', 'ImportMotion('):
        assert operation not in selected
    assert 'FindFiles(Stale,' in LEGACY and 'IFileManager::Get().Delete(' in LEGACY
    assert 'if(Number>=0 && Number<Chunk)continue;' in LEGACY
    assert LEGACY.index('WriteMotionIndex(') < LEGACY.index('FindFiles(')
