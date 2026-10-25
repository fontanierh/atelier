"""The native in-memory verification API shares every production check and report with the file wrapper.

These source/interface checks run without Unreal. Native compilation and fresh-process
verification remain required before claiming native execution evidence.
"""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate'
CPP = (SOURCE / 'Private/SkateMotionData.cpp').read_text()
HEADER = (SOURCE / 'Public/SkateDataLibrary.h').read_text()
MEMORY = CPP.split('bool USkateDataLibrary::VerifyToJson(', 1)[1].split('\nbool USkateDataLibrary::Verify(', 1)[0]
WRAPPER = CPP.split('bool USkateDataLibrary::Verify(', 1)[1]


def test_reflected_api_keeps_both_output_parameters_and_original_file_api():
    assert ('UFUNCTION(BlueprintCallable, Category="Skate Data") static bool VerifyToJson('
            'const FString& PackageFolder, FString& ReportJson, FString& Error);') in HEADER
    assert ('static bool Verify(const FString& PackageFolder, const FString& ReportFile, FString& Error);') in HEADER
    assert MEMORY.startswith('const FString& PackageFolder,FString& ReportJson,FString& Error)')
    assert MEMORY.index('ReportJson.Reset();') < MEMORY.index('#if WITH_EDITOR')
    assert MEMORY.count('ReportJson=') == 1
    assert MEMORY.index('ReportJson=') > MEMORY.index('Unreferenced skate data package would be cooked: ')
    assert 'SaveStringToFile' not in MEMORY and 'ReportFile' not in MEMORY
    assert 'Error=TEXT("Skate data verification requires an editor build");return false;' in MEMORY


def test_file_api_delegates_before_writing_exact_memory_report_and_preserves_failure():
    assert WRAPPER.index('if(!VerifyToJson(PackageFolder,ReportJson,Error))return false;') < WRAPPER.index('SaveStringToFile')
    assert 'FFileHelper::SaveStringToFile(ReportJson,*ReportFile)' in WRAPPER
    assert 'Error=TEXT("Cannot save skate data verification report");' in WRAPPER
    assert 'return false;' in WRAPPER and WRAPPER.rstrip().endswith('return true;\n}')
    # Exhaustive checks live in one shared implementation, never a reduced wrapper path.
    assert 'CompareMotion(' not in WRAPPER and 'Replays(' not in WRAPPER
    assert CPP.count('if(!CompareMotion(*Reference->animation,*Typed,Frames,Samples,E))') == 1


def test_shared_implementation_retains_serialized_reload_replays_and_every_control():
    for statement in (
        'CompleteSkateMotion(Path);CompleteSkateRuntime(RuntimePath);',
        'const FSkateMotionLoad Loaded=RequestSkateMotion(Path).get();',
        'const FSkateRuntimeLoad LoadedRuntime=RequestSkateRuntime(RuntimePath).get();',
        'if(!CompareMotion(*Reference->animation,*Typed,Frames,Samples,E))',
        'if(Bytes!=Pair.second)',
        'if(!skate::LoadGameplayResources(*LoadedRuntime.Payloads,*Typed,Runtime,E)||!Replays(Reference,Runtime,Steps,E))',
        'V=Float(Bits(V)^1u);', 'V=Saved;',
        'if(!Detected)', 'if(!RejectedRig||!RejectedTrack||!RejectedMetadata)',
        'Distance^=1u;', 'if(!RuntimeDetected)', 'if(!RejectedGraph||!RejectedBone||!RejectedSchema)',
        'if(!EncodeSkateRuntime(*RuntimeData,Encoded,E)||Encoded!=*LoadedRuntime.Payloads)',
        'if(!Referenced.Contains(Full)&&Full!=RuntimePackage)',
    ):
        assert statement in MEMORY
    replays = CPP.split('bool Replays(', 1)[1].split('\n#endif', 1)[0]
    assert 'for(bool Goofy:{false,true}) for(int Scenario=0;Scenario<6;++Scenario)' in replays
    assert 'for(int F=0;F<600;++F)' in replays


def test_complete_existing_report_format_is_finite_json_with_all_original_evidence_fields():
    literal = re.search(r'ReportJson=FString::Printf\(TEXT\("((?:\\.|[^"\\])*)"\)', MEMORY)[1]
    template = json.loads('"' + literal + '"')
    substitutions = iter([1, '/Game/SkateMotion/MotionData.MotionData', 3324, 100, 200, 7200,
                          1, '/Game/SkateRuntime/RuntimeData.RuntimeData', 7, 1234,
                          '"/Game/SkateMotion/Banks/Bank_000.Bank_000"'])
    report = re.sub(r'%llu|%d|%s', lambda match: str(next(substitutions)), template)
    data = json.loads(report, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    assert data == {'schema': 1, 'asset': '/Game/SkateMotion/MotionData.MotionData', 'clips': 3324,
                    'frames': 100, 'bone_samples': 200, 'replay_steps': 7200, 'replay_cases': 12,
                    'exact': True, 'negative_control': True, 'invalid_record_controls': 3,
                    'runtime_schema': 1, 'runtime_asset': '/Game/SkateRuntime/RuntimeData.RuntimeData',
                    'runtime_files': 7, 'runtime_bytes': 1234, 'runtime_exact': True,
                    'runtime_negative_control': True, 'runtime_invalid_record_controls': 3,
                    'banks': ['/Game/SkateMotion/Banks/Bank_000.Bank_000']}
