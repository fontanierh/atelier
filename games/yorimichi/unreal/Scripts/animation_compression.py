"""Preserve accessory motion on the existing metre-based character skeletons.

FBX keeps a 100x root scale. Generic local-unit tolerances can discard
centimetres of visible motion. Use 0.0001 for these rigs (0.01 cm in game).
Run this script alone to update existing character/item clips without reimport.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import unreal as U

_settings=None

def apply_to(sequence):
    global _settings
    if _settings is None:
        folder='/Game/Japan/Animation'
        path=folder+'/CharacterCompression'
        library=U.EditorAssetLibrary
        library.make_directory(folder)
        _settings=library.load_asset(path) if library.does_asset_exist(path) else U.AssetToolsHelpers.get_asset_tools().create_asset(
            'CharacterCompression',folder,U.AnimBoneCompressionSettings,U.AnimBoneCompressionSettingsFactory())
        codecs=list(_settings.get_editor_property('codecs'))
        codec_class=U.load_class(None,'/Script/Engine.AnimCompress_PerTrackCompression')
        codec=next((c for c in codecs if c.get_class()==codec_class),None)
        if codec is None: codec=U.new_object(codec_class,outer=_settings,name='CharacterTracks')
        # The codec has no generated Python wrapper; use its reflected C++ names.
        for key in ('MaxPosDiffBitwise','MaxAngleDiffBitwise','MaxScaleDiffBitwise',
                    'MaxPosDiff','MaxAngleDiff','MaxScaleDiff','MaxEffectorDiff',
                    'MinEffectorDiff','EffectorDiffSocket'):
            codec.set_editor_property(key,.0001)
        codec.set_editor_property('MaxZeroingThreshold',.000001)
        codec.set_editor_property('bResampleAnimation',False)
        codec.set_editor_property('bRetarget',False)
        _settings.set_editor_property('codecs',[codec])
        _settings.set_editor_property('error_threshold',.0001)
        library.save_loaded_asset(_settings)
    sequence.set_editor_property('bone_compression_settings',_settings)

if __name__=='__main__':
    paths=[]
    for folder in ('/Game/CapeBoy','/Game/Wanderer'):
        for path in U.EditorAssetLibrary.list_assets(folder,recursive=True,include_folder=False):
            asset=U.load_asset(path)
            if isinstance(asset,U.AnimSequence):
                apply_to(asset); U.EditorAssetLibrary.save_loaded_asset(asset); paths.append(path)
    out=yori.OUT/'compression_update.json'
    out.write_text(json.dumps({'local_error_threshold':.0001,'clips':paths},indent=2)+'\n')
    U.log('CHARACTER COMPRESSION UPDATED: '+str(len(paths))+' clips')
