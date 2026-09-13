"""Build exactly the configured telemetry components with pinned upstream OCB."""

import hashlib
import json
import os
import subprocess  # nosec B404
import urllib.request

import yaml

from prepare_environment_source import ROOT, BASE, GO

BUILDER_URL = (
    "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/"
    "download/cmd/builder/v0.160.0/ocb_0.160.0_windows_amd64.exe"
)
BUILDER_SHA256 = "2a40f86342f25bf0ac27bcbbc6da4054b0acd1541fd7d69a02f6c6aabac535f1"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    folder = BASE / "collector-0.160.0"
    folder.mkdir(parents=True, exist_ok=True)
    executable = folder / "ocb.exe"
    if not executable.exists():
        partial = executable.with_suffix(".download")
        # Fixed official HTTPS release URL; downloaded bytes must match the pinned SHA.
        with (
            urllib.request.urlopen(BUILDER_URL, timeout=90) as response,  # nosec B310
            partial.open("wb") as output,
        ):
            while block := response.read(1024 * 1024):
                output.write(block)
        if sha256(partial) != BUILDER_SHA256:
            raise ValueError("Upstream OCB checksum mismatch")
        partial.rename(executable)
    if sha256(executable) != BUILDER_SHA256:
        raise ValueError("OCB identity changed")
    config = ROOT / "deploy/dev-environment/security/collector-builder.yaml"
    manifest = yaml.safe_load(config.read_text(encoding="utf-8"))
    output = folder / "distribution"
    manifest["dist"].update(output_path=str(output), go=str(GO))
    generated = folder / "builder.yaml"
    generated.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    environment = dict(os.environ)
    environment.update(
        GOENV="off",
        GOWORK="off",
        GOTOOLCHAIN="local",
        CGO_ENABLED="0",
        GOOS="linux",
        GOARCH="amd64",
        GOMAXPROCS="2",
        GOPATH=str(ROOT / "_local_artifacts/go-path"),
        GOMODCACHE=str(ROOT / "_local_artifacts/go-mod-cache"),
        GOCACHE=str(ROOT / "_local_artifacts/go-build-cache"),
        GOFLAGS="-mod=mod -trimpath -buildvcs=false -p=2",
    )
    subprocess.run(  # nosec B603
        [str(executable), "--config", str(generated)],
        cwd=folder,
        env=environment,
        check=True,
        timeout=1800,
    )
    binary = output / "ics-otelcol"
    report = {
        "builder_url": BUILDER_URL,
        "builder_sha256": BUILDER_SHA256,
        "manifest_sha256": sha256(config),
        "binary_sha256": sha256(binary),
        "go": "1.27.1",
        "source": str(output.relative_to(ROOT)),
        "image_scan": "NOT_RUN",
        "compatibility": "NOT_RUN",
    }
    (folder / "build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Collector compiled; scan and real pipeline validation still required", flush=True)


if __name__ == "__main__":
    main()
