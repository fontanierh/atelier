#!/usr/bin/env python3
"""Ordered original AirSettings load, retained destination, repeated failure/recovery.

Only the root render guard compiles/runs. --preflight writes source/fixtures and
checks immutable source identity without compiling or running binaries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import check_skeleton_input_runtime_parity as dispatcher
from air_settings_fixtures import loader_fixtures
from check_gesture_parity import PLUGIN,converter
from check_air_state_parity import Reader
from reference_build import build_probe
from session_parity import REFERENCE_REVISION,digest
UNITS=('NativeMath','NameId','Settings','StockSettingsReader','AirMath','AirState','AirStateSettings')
ALIASES={'atelier-host/src/bindings/input.rs':'crates/skate-host/src/physics/air_phase/input.rs'}

def prepare(out,assets):
 out.mkdir(parents=True,exist_ok=True);native=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=out/'native-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in [*sorted(native.glob('*.h')),*[native/(u+'.cpp')for u in UNITS],PLUGIN/'Tests/Native/air_settings_probe.cpp']:shutil.copy2(p,snapshot/p.name)
 # Reuse only the declaration portion of the existing independent binding
 # transport. This binds the complete unmodified input module without calling
 # or providing any implementation of the unrelated runtime functions.
 bindings=(PLUGIN/'Tests/Reference/air_state_probe.rs').read_text();start=bindings.index('mod bindings {');end=bindings.index('    pub fn read(',start);types=bindings[start:end]+'}\n'
 template=PLUGIN/'Tests/Reference/air_settings_probe.rs';reference=out/'air-settings-reference.rs';reference.write_text(template.read_text().replace('// GENERATED_OWNER_TYPES',types))
 source=dispatcher.source(ALIASES['atelier-host/src/bindings/input.rs']);root_original=out/'air-settings-original-input.rs';root_original.write_text(source)
 fixtures=loader_fixtures(assets.resolve());records=[]
 stock=out/'stock.native';stock.write_bytes(converter.encode_settings(assets/'private/stock/skater-collections.json'))
 for index,fixture in enumerate(fixtures):
  folder=out/'fixtures'/f'{index:03d}-{fixture["label"]}';path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(fixture['data'])+'\n');bank=folder/'settings.native';bank.write_bytes(converter.encode_settings(path));records.append(dict(index=index,label=fixture['label'],assets=str(folder),bank=str(bank),success=fixture['success'],first_position=fixture['first_position'],second_position=fixture.get('second_position'),native_sha256=digest(bank),json_sha256=digest(path)))
 provenance=dict(reference_revision=REFERENCE_REVISION,original_input_sha256=hashlib.sha256(source.encode()).hexdigest(),binding_declarations_sha256=hashlib.sha256(types.encode()).hexdigest(),native_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},reference_probe_sha256=digest(reference),probe_templates_sha256={p.name:digest(p)for p in(template,PLUGIN/'Tests/Native/air_settings_probe.cpp')},fixture_generator_sha256=digest(PLUGIN/'Tests/air_settings_fixtures.py'),units=UNITS)
 (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');(out/'fixtures.json').write_text(json.dumps(records,indent=2)+'\n');return snapshot,reference,records,provenance

def decode(raw):
 r=Reader(raw);base=r.words(25);attempts=[]
 for _ in range(3):attempts.append(dict(error=r.status(),words=r.words(25)))
 assert r.at==len(raw);assert attempts[-1]['error']is None and attempts[-1]['words']==base
 assert attempts[0]==attempts[1]
 if attempts[0]['error']is not None:assert attempts[0]['words']==base
 return dict(stock=base,attempts=attempts)

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for key in('assets','output','target-dir'):parser.add_argument('--'+key,type=Path,required=True)
 parser.add_argument('--preflight',action='store_true');args=parser.parse_args();out=args.output.resolve();assets=args.assets.resolve();snapshot,probe,fixtures,provenance=prepare(out,assets)
 if args.preflight:print(json.dumps(dict(fixtures=len(fixtures),invalid=sum(not f['success']for f in fixtures),raw_graph_success=sum(f['success']for f in fixtures),compound_failures=sum(f['second_position']is not None for f in fixtures),units=len(UNITS),provenance_sha256=digest(out/'provenance.json')),indent=2));return
 reference=build_probe(out,'air-settings-reference',probe,args.target_dir,extra_sources=ALIASES);native=out/'air-settings-native'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'air_settings_probe.cpp'),'-o',str(native)],check=True)
 assert digest(out/'reference-source'/next(iter(ALIASES)))==provenance['original_input_sha256']
 results=[];width_errors={};combined=hashlib.sha256()
 for fixture in fixtures:
  folder=Path(fixture['assets']);expected=subprocess.check_output([str(reference),str(assets),str(folder)]);actual=subprocess.check_output([str(native),str(out/'stock.native'),fixture['bank']]);(folder/'reference.bin').write_bytes(expected);(folder/'native.bin').write_bytes(actual)
  assert expected==actual,(fixture['label'],expected.hex(),actual.hex());record=decode(expected);error=record['attempts'][0]['error'];assert (error is None)==fixture['success'],fixture['label']
  if fixture['second_position']is None and fixture['label'].endswith('-width'):width_errors[fixture['first_position']]=error
  if fixture['second_position']is not None:assert error==width_errors[fixture['first_position']],(fixture['label'],error,width_errors)
  combined.update(expected);results.append(dict(label=fixture['label'],error=error,output_sha256=hashlib.sha256(expected).hexdigest(),output_bytes=len(expected)))
 result=dict(passed=True,reference_revision=REFERENCE_REVISION,fixtures=len(fixtures),invalid=sum(not f['success']for f in fixtures),raw_graph_success=sum(f['success']for f in fixtures),compound_failures=sum(f['second_position']is not None for f in fixtures),read_positions=10,output_sha256=combined.hexdigest(),results=results,provenance_sha256=digest(out/'provenance.json'),scope='Entire unchanged original AirSettings::load; exact 16-word graph reader and ordered five mode distances, three state scalars, steering; exact error text, staged destination, repeated load and recovery.',boundaries='Loader leaf only. Unused data-only owner declarations bind the full input.rs module; no physical/frame/selector/launch function executes. Whole Air/Known actual producer proof remains separate.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='results'},indent=2))
if __name__=='__main__':main()
