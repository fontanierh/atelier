"""Submit one reviewed multiview set to Tripo and retain its outputs.

Run with `uv run python` (httpx is a project dependency), with TRIPO_API_KEY or the private
project credential file. A saved task is resumed; uncertain POSTs are never
automatically repeated. Raw API responses stay in ignored api-private folders.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

import httpx

API = "https://openapi.tripo3d.ai/v3"
KEY_FILE = Path.home()/".local/share/atelier/credentials/tripo-api-key"  # optional; TRIPO_API_KEY from .env comes first
VIEWS = ("front", "left", "back", "right")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, indent=2)+"\n")
    if private:
        temporary.chmod(0o600)
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text())


def credential():
    try:   # the repository-root .env (never printed)
        from atelier.env import load
        load()
    except ImportError:
        pass
    key = os.environ.get("TRIPO_API_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not key:
        raise SystemExit("Set TRIPO_API_KEY or the private project Tripo credential file.")
    if key.startswith("tcli_"):
        raise SystemExit("A tcli_ Client ID cannot authenticate. Use the secret tsk_ API key.")
    return key


def call(client, method, route, **kwargs):
    response = client.request(method, API+route, **kwargs)
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(f"Tripo returned HTTP {response.status_code} without JSON") from None
    if response.status_code >= 400 or result.get("code") != 0:
        raise RuntimeError(f"Tripo HTTP {response.status_code}, code {result.get('code')}: {result.get('message', 'request failed')}")
    return result


def private_folder(output):
    output.mkdir(parents=True, exist_ok=True)
    path = output/"api-private"
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)
    ignore = output/".gitignore"
    existing = ignore.read_text() if ignore.exists() else ""
    missing = [rule for rule in ("api-private/", "*.part", "*.blend1", "blender/turntable-frames/")
               if rule not in existing.splitlines()]
    if missing:
        ignore.write_text(existing.rstrip()+"\n"+"\n".join(missing)+"\n")
    return path


def output_urls(value, prefix="output"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from output_urls(child, prefix+"_"+key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from output_urls(child, prefix+"_"+str(index))
    elif isinstance(value, str) and value.startswith("https://"):
        yield prefix, value


def download_outputs(output, task):
    raw = output/"raw"
    raw.mkdir(exist_ok=True)
    previous = read_json(output/"downloads.json") if (output/"downloads.json").exists() else []
    indexed = {item["output_field"]: item for item in previous}
    # Never send API authentication to a CDN/download host.
    with httpx.Client(timeout=httpx.Timeout(180, connect=20), follow_redirects=True) as download_client:
        for field, url in output_urls(task.get("output", {})):
            item = indexed.get(field)
            if item and (output/item["file"]).exists() and digest(output/item["file"]) == item["sha256"]:
                continue
            suffix = Path(urlparse(url).path).suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,6}", suffix):
                suffix = ".bin"
            name = re.sub(r"[^a-zA-Z0-9_-]", "_", field)+suffix
            path = raw/name
            partial = path.with_suffix(path.suffix+".part")
            with download_client.stream("GET", url) as response:
                response.raise_for_status()
                with partial.open("wb") as target:
                    for chunk in response.iter_bytes():
                        target.write(chunk)
            partial.replace(path)
            indexed[field] = {"output_field":field, "file":str(path.relative_to(output)),
                              "sha256":digest(path), "bytes":path.stat().st_size,
                              "downloaded_at":now()}
            write_json(output/"downloads.json", list(indexed.values()))
            print(f"Downloaded {name}: {path.stat().st_size:,} bytes", flush=True)
    return list(indexed.values())


def fetch(client, output, watch):
    job_path = output/"job.json"
    job = read_json(job_path)
    if not job.get("task_id"):
        raise RuntimeError("No recorded task ID. Reconcile any uncertain submission before retrying.")
    private = private_folder(output)
    last = None
    deadline = time.monotonic()+1800
    while True:
        response = call(client, "GET", "/tasks/"+job["task_id"])
        write_json(private/"latest-task.json", response, private=True)
        task = response["data"]
        state = (task.get("status"), task.get("progress"))
        job.update(provider_status=state[0], progress=state[1], last_checked_at=now())
        if "credits_consumed" in task:
            job["credits_consumed"] = task["credits_consumed"]
        write_json(job_path, job)
        if state != last:
            print(f"{job['task_id']}: {state[0]} ({state[1]}%)", flush=True)
            last = state
        if state[0] == "success":
            files = download_outputs(output, task)
            job.update(output_files=len(files))
            if job.get("user_approval", "pending") == "pending":
                job.update(status="downloaded_awaiting_review", user_approval="pending")
            write_json(job_path, job)
            print(f"Task complete; {len(files)} outputs retained. Credits: {job.get('credits_consumed', 'not reported')}", flush=True)
            return
        if state[0] in {"failed", "cancelled"}:
            job.update(status=state[0], error_code=task.get("error_code"), error_message=task.get("error_message"))
            write_json(job_path, job)
            raise RuntimeError(f"Tripo task {state[0]}: {task.get('error_message', task.get('error_code'))}")
        if not watch or time.monotonic() >= deadline:
            return
        time.sleep(10)


def generate(client, references, output, faces):
    job_path = output/"job.json"
    private = private_folder(output)
    if job_path.exists() and read_json(job_path).get("task_id"):
        return fetch(client, output, True)
    if (private/"submission-started.json").exists():
        raise RuntimeError("An earlier POST may have succeeded. Reconcile it before creating another paid task.")
    approval = read_json(references/"approval.json")
    if approval.get("event") != "multiview_set_approved_for_tripo_generation":
        raise RuntimeError("The multiview set has no recorded approval for Tripo generation.")
    images = {view: references/(view+".png") for view in VIEWS}
    for path in images.values():
        if approval["images"].get(path.name) != digest(path):
            raise RuntimeError(f"Approved input changed: {path.name}")
    tokens_path = private/"uploads.json"
    tokens = read_json(tokens_path) if tokens_path.exists() else {}
    for view, path in images.items():
        if view in tokens and tokens[view]["sha256"] == digest(path):
            continue
        with path.open("rb") as image:
            data = call(client, "POST", "/files", files={"file":(path.name,image,"image/png")})["data"]
        tokens[view] = {"file_token":data["file_token"], "sha256":digest(path)}
        write_json(tokens_path, tokens, private=True)
        print("Uploaded "+view, flush=True)
    settings = {"model":"P2-20260801", "quad":True, "face_limit":faces,
                "texture":True, "pbr":True, "texture_quality":"detailed",
                "export_uv":True, "model_seed":9122026, "texture_seed":9122026}
    payload = {"inputs":[{view:tokens[view]["file_token"]} for view in VIEWS], **settings}
    job = {"stage":"initial_tripo_mesh", "revision":output.name,
           "status":"submitting", "submitted_at":now(), "endpoint":API+"/generation/multiview-to-model",
           "settings":settings, "reference_directory":str(references.resolve()),
           "approved_inputs":approval["images"], "view_convention":"anatomical left/right",
           "user_approval":"pending", "auto_rig_submitted":False}
    write_json(job_path, job)
    write_json(private/"submission-started.json", {"started_at":now(), "request":payload}, private=True)
    response = call(client, "POST", "/generation/multiview-to-model", json=payload)
    write_json(private/"submission-response.json", response, private=True)
    job.update(task_id=response["data"]["task_id"], status="submitted")
    write_json(job_path, job)
    print("Submitted P2 task "+job["task_id"], flush=True)
    fetch(client, output, True)


def rig(client, source, output):
    """Rig the exact approved cleanup, retaining the check and raw rig separately."""
    approval = read_json(source.parent/"rig-approval.json")
    if approval.get("event") != "cleanup_approved_for_tripo_rigging" or approval.get("sha256") != digest(source):
        raise RuntimeError("The rigging input has no matching cleanup approval.")
    private = private_folder(output)
    upload_path = private/"upload.json"
    if upload_path.exists():
        upload = read_json(upload_path)
        if upload["sha256"] != digest(source):
            raise RuntimeError("Source differs from the recorded upload; create a new revision.")
    else:
        with source.open("rb") as model:
            data = call(client, "POST", "/files", files={"file":(source.name, model, "model/gltf-binary")})["data"]
        upload = {"file_token":data["file_token"], "sha256":digest(source)}
        write_json(upload_path, upload, private=True)
        print("Uploaded approved cleanup", flush=True)

    def stage(folder, route, settings):
        stage_private = private_folder(folder)
        job_path = folder/"job.json"
        if not job_path.exists():
            write_json(job_path, {"stage":route.rsplit("/",1)[-1], "revision":folder.name,
                "status":"submitting", "submitted_at":now(), "endpoint":API+route,
                "source_file":str(source.resolve()), "source_sha256":digest(source),
                "settings":settings, "user_approval":"pending"})
        job = read_json(job_path)
        if job["source_sha256"] != digest(source) or job["settings"] != settings:
            raise RuntimeError("Recorded stage differs from the requested input or settings.")
        if not job.get("task_id"):
            marker = stage_private/"submission-started.json"
            if marker.exists():
                raise RuntimeError("A prior submission may have succeeded; reconcile before retrying.")
            payload = {"input":upload["file_token"], **settings}
            write_json(marker, {"started_at":now(), "request":payload}, private=True)
            response = call(client, "POST", route, json=payload)
            write_json(stage_private/"submission-response.json", response, private=True)
            job.update(task_id=response["data"]["task_id"], status="submitted")
            write_json(job_path, job)
            print("Submitted "+route+": "+job["task_id"], flush=True)
        fetch(client, folder, True)
        return read_json(stage_private/"latest-task.json")["data"]

    checked = stage(output/"check", "/animations/rig-check", {})
    if checked.get("status") != "success":
        raise RuntimeError("Rig check is not complete; resume this command later.")
    check = checked.get("output", {})
    write_json(output/"rig-check.json", {key:check.get(key) for key in ("riggable", "rig_type")})
    if check.get("riggable") is not True or check.get("rig_type") != "biped":
        raise RuntimeError("Rig check did not confirm a riggable biped. Inspect before proceeding.")
    stage(output, "/animations/rig", {"model":"v1.0-20240301", "rig_type":"biped", "spec":"mixamo", "out_format":"glb"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("balance")
    gen = commands.add_parser("generate")
    gen.add_argument("--references", type=Path, required=True)
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--faces", type=int, default=8000)
    query = commands.add_parser("fetch")
    query.add_argument("--output", type=Path, required=True)
    query.add_argument("--watch", action="store_true")
    auto_rig = commands.add_parser("rig")
    auto_rig.add_argument("--source", type=Path, required=True)
    auto_rig.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = credential()
    try:
        with httpx.Client(headers={"Authorization":"Bearer "+key}, timeout=httpx.Timeout(180, connect=20)) as client:
            if args.command == "balance":
                print(json.dumps(call(client, "GET", "/account/balance")["data"]))
            elif args.command == "generate":
                generate(client, args.references, args.output, args.faces)
            elif args.command == "rig":
                rig(client, args.source, args.output)
            else:
                fetch(client, args.output, args.watch)
    except Exception as error:
        # Do not print request headers, credentials or signed download URLs.
        message = str(error).replace(key, "<redacted>")
        message = re.sub(r"https://\S+", "<URL omitted>", message)
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
