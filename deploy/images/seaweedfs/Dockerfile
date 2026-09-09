# New-platform security derivative only; upstream SeaweedFS and KF are immutable.
# Pin both official image indexes. Build with --platform=linux/amd64 for M01.
FROM docker.io/library/golang:1.27.1-alpine3.24@sha256:cf6fca6641884b8433441b2b0652976f975e1d0fdd26d177eaaf8596087f3125 AS builder

ENV CGO_ENABLED=0 \
    GOTOOLCHAIN=local \
    GOPROXY=https://proxy.golang.org \
    GOSUMDB=sum.golang.org \
    GOMAXPROCS=2
WORKDIR /src

# Exact upstream commit and independently verified archive checksum, not a branch.
ADD --checksum=sha256:d577baa0509178554b35350be261e8a6bebf440c51f0cfb1532a075cf843f1dd https://codeload.github.com/seaweedfs/seaweedfs/tar.gz/79b87202136cebdaaa7db4d94eaa5915ad381276 /tmp/upstream.tar.gz
RUN tar -xzf /tmp/upstream.tar.gz --strip-components=1 -C /src \
    && rm /tmp/upstream.tar.gz

# Full module locks reproduce the adjacent reviewable dependencies.patch.
# Official minimal Go Alpine has no patch executable; do not fetch an unpinned
# build utility just to apply a text patch. All business source stays untouched.
COPY go.mod.lock /src/go.mod
COPY go.sum.lock /src/go.sum
COPY modules.sha256 /tmp/modules.sha256
RUN sha256sum -c /tmp/modules.sha256

RUN --mount=type=cache,id=ics-m01-seaweed-gomod,target=/go/pkg/mod \
    go mod download \
    && go mod verify \
    && sha256sum -c /tmp/modules.sha256

# Upstream "normal" variant has no extra build tags. Do not enable rclone,
# Enterprise, RocksDB, Rust volume/worker or plugin binaries in this image.
RUN --mount=type=cache,id=ics-m01-seaweed-gomod,target=/go/pkg/mod \
    --mount=type=cache,id=ics-m01-seaweed-gocache,target=/root/.cache/go-build \
    go build -p 2 -mod=readonly -trimpath -buildvcs=false -tags="" \
      -ldflags="-s -w -X github.com/seaweedfs/seaweedfs/weed/util/version.COMMIT=79b87202136cebdaaa7db4d94eaa5915ad381276-m01-security.2" \
      -o /out/weed ./weed \
    && go version -m /out/weed > /out/weed.buildinfo.txt \
    && /out/weed version \
    && sha256sum -c /tmp/modules.sha256

FROM docker.io/library/alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS runtime
LABEL org.opencontainers.image.title="SeaweedFS M01 security derivative" \
      org.opencontainers.image.version="4.45-m01-security.2" \
      org.opencontainers.image.revision="79b87202136cebdaaa7db4d94eaa5915ad381276" \
      org.opencontainers.image.source="https://github.com/seaweedfs/seaweedfs" \
      org.opencontainers.image.licenses="Apache-2.0" \
      io.intelligent-commerce.security-derivative="thrift-0.24.0,image-0.45.0,crypto-0.56.0"

# No apk add/upgrade: no floating OS dependencies and no curl/libcurl, FUSE,
# compiler, package downloads, Rust worker or upstream auto-starting entrypoint.
RUN apk del --no-network --purge apk-tools ssl_client libapk libssl3 libcrypto3 \
    && addgroup -g 1000 seaweed \
    && adduser -D -H -u 1000 -G seaweed seaweed \
    && mkdir -p /data/filerldb2 /etc/seaweedfs /usr/share/licenses/seaweedfs \
    && chown -R 1000:1000 /data
COPY --from=builder /out/weed /usr/bin/weed
COPY --from=builder /out/weed.buildinfo.txt /usr/share/licenses/seaweedfs/weed.buildinfo.txt
COPY --from=builder /src/LICENSE /usr/share/licenses/seaweedfs/LICENSE
COPY --from=builder /src/docker/filer.toml /etc/seaweedfs/filer.toml
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY README.md source.lock.json /usr/share/licenses/seaweedfs/

USER 1000:1000
WORKDIR /data
EXPOSE 8333
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=12 \
    CMD ["/bin/busybox", "wget", "-q", "-T", "2", "-O", "/dev/null", "http://127.0.0.1:8333/healthz"]
ENTRYPOINT ["/usr/bin/weed"]
# Fail safe: a bare docker run does not start an anonymous object store.
# The reviewed Compose wrapper validates secrets then invokes `weed server`.
CMD ["version"]
