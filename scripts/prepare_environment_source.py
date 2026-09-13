"""Build reviewed telemetry sources in project artifacts; no original-project changes."""

from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import subprocess  # nosec B404
import tarfile
import urllib.request
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "_local_artifacts/environment/security-build"
GO = ROOT / "_local_artifacts/toolchains/go1.27.1-windows-amd64/go/bin/go.exe"
PROFILES = {
    "prometheus": (
        "prometheus/prometheus",
        "b273ae3adeb64ad630d65ef7f16440df95658410",
        ["prometheus", "promtool"],
    ),
    "tempo": ("grafana/tempo", "1900ed7bb5cad1a3edc285783d7d4ac4278337dc", ["tempo"]),
    "loki": ("grafana/loki", "7a40404f32b3e6464c9cfc6cc7dd75a40f3931da", ["loki"]),
    "grafana": ("grafana/grafana", "81407c71e96e8351b4600164c1b4d30c8baf41d6", ["grafana"]),
}
VERSIONS = {"prometheus": "3.13.3", "tempo": "3.0.3", "loki": "3.7.7", "grafana": "12.4.10"}


def extract_source(archive, source):
    """Extract regular source files only, including Windows long paths, without links."""
    skipped = []
    seen = set()
    with tarfile.open(archive) as bundle:
        for member in bundle:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or not name.parts
                or name.parts[0] != source.name
                or any(p in {"..", "."} or ":" in p or "\\" in p for p in name.parts)
                or member.name in seen
            ):
                raise ValueError("Unsafe or duplicate source member")
            seen.add(member.name)
            target = source.parent.joinpath(*name.parts).resolve()
            if not target.is_relative_to(source.resolve()):
                raise ValueError("Source target escaped build directory")
            if member.issym() or member.islnk():
                # Go does not embed symlinks. Record omissions; missing required
                # source will fail the actual build, never substitute link targets.
                skipped.append(member.name)
                continue
            if not (member.isfile() or member.isdir()):
                raise ValueError("Special source member rejected")
            disk = Path("\\\\?\\" + str(target)) if os.name == "nt" else target
            if member.isdir():
                disk.mkdir(parents=True, exist_ok=True)
            else:
                disk.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as content, disk.open("wb") as output:
                    shutil.copyfileobj(content, output)
    return skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=list(PROFILES))
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    repo, revision, binaries = PROFILES[args.service]
    BASE.mkdir(parents=True, exist_ok=True)
    archive = BASE / (args.service + "-" + revision + ".tar.gz")
    if not archive.exists():
        url = "https://codeload.github.com/" + repo + "/tar.gz/" + revision
        partial = archive.with_suffix(".download")
        with urllib.request.urlopen(url, timeout=90) as response, partial.open("wb") as output:  # nosec B310
            while block := response.read(1024 * 1024):
                output.write(block)
        partial.rename(archive)
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    source = BASE / (args.service + "-" + revision)
    marker = source / ".ics-extracted-sha256"
    if not marker.exists():
        skipped = extract_source(archive, source)
        (source / ".ics-omitted-links.json").write_text(json.dumps(skipped), encoding="utf-8")
        marker.write_text(checksum + "\n", encoding="ascii")
    elif marker.read_text(encoding="ascii").strip() != checksum:
        raise ValueError("Extracted source identity changed")
    print("Source ready: " + str(source), flush=True)
    if args.prepare_only:
        return
    environment = dict(os.environ)
    environment.update(
        GOENV="off",
        GOWORK="off",
        GOTOOLCHAIN="local",
        CGO_ENABLED="0",
        GOOS="linux",
        GOARCH="amd64",
        GOPATH=str(ROOT / "_local_artifacts/go-path"),
        GOMODCACHE=str(ROOT / "_local_artifacts/go-mod-cache"),
        GOCACHE=str(ROOT / "_local_artifacts/go-build-cache"),
        GOFLAGS="-mod=mod -trimpath -buildvcs=false -p=2",
        GOMAXPROCS="2",
    )

    def run(arguments):
        subprocess.run([str(GO), *arguments], cwd=source, env=environment, check=True, timeout=1800)  # nosec B603

    upgrades = ["google.golang.org/grpc@v1.83.2", "golang.org/x/crypto@v0.55.0"]
    if args.service in {"tempo", "grafana"}:
        upgrades.append("github.com/apache/thrift@v0.24.0")
    if args.service == "grafana":
        environment["GOWORK"] = str(source / "go.work")
        environment["GOFLAGS"] = "-trimpath -buildvcs=false -p=2"
    run(["get", *upgrades])
    outputs = BASE / (args.service + "-" + revision[:12] + "-output")
    outputs.mkdir(exist_ok=True)
    for name in binaries:
        target = "./pkg/cmd/grafana" if args.service == "grafana" else "./cmd/" + name
        tags = ["-tags=oss"] if args.service == "grafana" else []
        version = VERSIONS[args.service] + "-ics.1"
        flags = {
            "prometheus": f"-X github.com/prometheus/common/version.Version={version} -X github.com/prometheus/common/version.Revision={revision}",
            "tempo": f"-X main.Version={version} -X main.Revision={revision}",
            "loki": f"-X github.com/grafana/loki/v3/pkg/util/build.Version={version} -X github.com/grafana/loki/v3/pkg/util/build.Revision={revision}",
            "grafana": f"-X main.version={version} -X main.commit={revision} -X main.buildBranch=ics-security",
        }[args.service]
        run(["build", *tags, "-ldflags=" + flags, "-o", str(outputs / name), target])
    record = {
        "repository": repo,
        "revision": revision,
        "source_sha256": checksum,
        "go": "1.27.1",
        "dependency_patches": upgrades,
        "binaries": {
            name: hashlib.sha256((outputs / name).read_bytes()).hexdigest() for name in binaries
        },
    }
    (outputs / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(args.service + " patched binaries built; image scan and compatibility still required")


if __name__ == "__main__":
    main()
