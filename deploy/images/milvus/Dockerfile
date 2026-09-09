# syntax=docker/dockerfile:1.7

FROM docker.io/milvusdb/milvus-env:ubuntu22.04-20260603-5baf83b@sha256:4d0ea84b1ccbbbbd9fbe99a467412fa8d1a93cb8b37632d8eb5019745d56214d AS build

ARG SOURCE_COMMIT=bfa1bc34f93df2ccd20fa7c060463c6c6812d355
ARG SOURCE_SHA256=47d14ac523d2503d9581facb225499cdc81c9ba9cffc1d923b7877ec5b3737e6
ARG GO_ARCHIVE=go1.27.1.linux-amd64.tar.gz
ARG GO_SHA256=63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
WORKDIR /build

RUN curl --fail --location --retry 3 --output source.tar.gz \
        "https://github.com/milvus-io/milvus/archive/${SOURCE_COMMIT}.tar.gz" \
    && echo "${SOURCE_SHA256}  source.tar.gz" | sha256sum --check --strict \
    && mkdir source \
    && tar --extract --gzip --file source.tar.gz --strip-components=1 --directory source \
    && rm source.tar.gz \
    && curl --fail --location --retry 3 --output go.tar.gz \
        "https://go.dev/dl/${GO_ARCHIVE}" \
    && echo "${GO_SHA256}  go.tar.gz" | sha256sum --check --strict \
    && mkdir /opt/go1.27.1 \
    && tar --extract --gzip --file go.tar.gz --strip-components=1 --directory /opt/go1.27.1 \
    && rm go.tar.gz

ENV GOROOT=/opt/go1.27.1
ENV PATH=/opt/go1.27.1/bin:/go/bin:/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV GOTOOLCHAIN=local
ENV GOFLAGS=-mod=readonly\ -trimpath\ -buildvcs=false\ -p=2
ENV GOMAXPROCS=2
ENV CARGO_BUILD_JOBS=2
ENV jobs=2
ENV CMAKE_BUILD_PARALLEL_LEVEL=2
ENV CONAN_CPU_COUNT=2
ENV MAKEFLAGS=-j2
ENV CCACHE_DIR=/ccache

COPY go.mod.lock go.sum.lock modules.sha256 /locks/
RUN cd /locks \
    && sha256sum --check --strict modules.sha256 \
    && cp go.mod.lock /build/source/go.mod \
    && cp go.sum.lock /build/source/go.sum

WORKDIR /build/source
RUN --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    go mod download \
    && go mod verify

RUN --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    --mount=type=cache,id=ics-milvus-conan-v2,target=/root/.conan,sharing=locked \
    --mount=type=cache,target=/root/.cargo,sharing=locked \
    --mount=type=cache,target=/ccache,sharing=locked \
    conan remove --locks \
    && make \
      BUILD_TAGS=v2.6.23-ics.2 \
      BUILD_TIME=2026-09-09T00:00:00Z \
      GIT_COMMIT=bfa1bc34f93df2ccd20fa7c060463c6c6812d355 \
      GO_VERSION=go1.27.1 \
      MILVUS_VERSION=2.6.23-ics.2 \
      build-cpp \
    && make \
      BUILD_TAGS=v2.6.23-ics.2 \
      BUILD_TIME=2026-09-09T00:00:00Z \
      GIT_COMMIT=bfa1bc34f93df2ccd20fa7c060463c6c6812d355 \
      GO_VERSION=go1.27.1 \
      MILVUS_VERSION=2.6.23-ics.2 \
      build-go

RUN test -x /build/source/bin/milvus \
    && test -s /build/source/internal/core/output/lib/libmilvus-planparser.so \
    && go version -m /build/source/bin/milvus > /tmp/milvus.buildinfo \
    && go version -m /build/source/internal/core/output/lib/libmilvus-planparser.so > /tmp/planparser.buildinfo \
    && grep -F $'dep\tgoogle.golang.org/grpc\tv1.83.2' /tmp/milvus.buildinfo \
    && grep -F $'dep\tgithub.com/bytedance/sonic\tv1.15.2' /tmp/milvus.buildinfo \
    && grep -F $'dep\tgolang.org/x/crypto\tv0.55.0' /tmp/milvus.buildinfo \
    && grep -F $'=>\tgo.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc\tv0.60.0' /tmp/milvus.buildinfo \
    && grep -F $'dep\tgoogle.golang.org/grpc\tv1.83.2' /tmp/planparser.buildinfo \
    && grep -F $'dep\tgithub.com/bytedance/sonic\tv1.15.2' /tmp/planparser.buildinfo \
    && grep -F $'=>\tgo.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc\tv0.60.0' /tmp/planparser.buildinfo

FROM docker.io/milvusdb/milvus:v2.6.23@sha256:60e96d5abe7ea9199dd8a4d0d0506f9b57a7056cf57683327b8c7ae7f489ed17

COPY --from=build --chown=root:root --chmod=774 /build/source/bin/milvus /milvus/bin/milvus
COPY --from=build --chown=root:root --chmod=774 /build/source/internal/core/output/lib/libmilvus-planparser.so /milvus/lib/libmilvus-planparser.so

LABEL org.opencontainers.image.source="https://github.com/sy824869109/intelligent-commerce-support-v1" \
      org.opencontainers.image.version="2.6.23-ics.2" \
      org.opencontainers.image.revision="bfa1bc34f93df2ccd20fa7c060463c6c6812d355" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.ics.security.go="1.27.1" \
      org.ics.security.grpc="1.83.2" \
      org.ics.compat.sonic="1.15.2" \
      org.ics.compat.otelgrpc="0.60.0"
