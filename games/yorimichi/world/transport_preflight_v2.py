"""Run the original transport source checks before any private native owner starts."""
import json


def ferry(service_file, cut_file, out, report):
    from regions.ferry.service import validate_service
    validate_service(json.loads(service_file.read_text()), out / 'ferry')
    failures = json.loads(cut_file.read_text())['failures']
    if failures:
        raise ValueError('Ferry Harbor cut failed: ' + str(failures))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('{"passed":true}\n')


def gondola(service_file, out, report):
    from gondola.service import validate_service
    validate_service(json.loads(service_file.read_text()), out)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('{"passed":true}\n')
