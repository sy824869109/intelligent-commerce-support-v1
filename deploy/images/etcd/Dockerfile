FROM docker.io/library/golang:1.27.1-alpine3.24@sha256:cf6fca6641884b8433441b2b0652976f975e1d0fdd26d177eaaf8596087f3125 AS build
ARG SOURCE_SHA256=a7ac1ed4192c6e53e4716df3e08bc75e4f929fcb186a9d9e5b0aaf11c96b067a
WORKDIR /src
RUN set -eux; wget -O source.tar.gz \
      https://github.com/etcd-io/etcd/archive/refs/tags/v3.6.14.tar.gz \
    && echo "${SOURCE_SHA256}  source.tar.gz" | sha256sum -c \
    && tar --extract --gzip --strip-components=1 --file source.tar.gz \
    && rm source.tar.gz
ENV GOTOOLCHAIN=local CGO_ENABLED=0 GOFLAGS=-trimpath\ -buildvcs=false\ -p=2 GOMAXPROCS=2
# All modules participating in the three release binaries receive the same fixed versions.
RUN for module in api client/pkg client/v3 pkg server etcdctl etcdutl; do \
      cd "/src/${module}"; \
      go get google.golang.org/grpc@v1.83.1 \
        golang.org/x/crypto@v0.55.0 golang.org/x/net@v0.58.0 golang.org/x/text@v0.41.0; \
      go mod tidy; \
    done \
    && mkdir -p /out \
    && (cd /src/server && go build -o /out/etcd .) \
    && (cd /src/etcdctl && go build -o /out/etcdctl .) \
    && (cd /src/etcdutl && go build -o /out/etcdutl .) \
    && for binary in etcd etcdctl etcdutl; do \
      go version -m "/out/${binary}" > "/tmp/${binary}.buildinfo"; \
      grep -F $'dep\tgoogle.golang.org/grpc\tv1.83.1' "/tmp/${binary}.buildinfo"; \
      grep -F $'dep\tgolang.org/x/crypto\tv0.55.0' "/tmp/${binary}.buildinfo"; \
    done

FROM scratch
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build --chmod=0755 /out/etcd /out/etcdctl /out/etcdutl /usr/local/bin/
USER 1000:1000
VOLUME ["/etcd"]
EXPOSE 2379 2380
ENTRYPOINT ["/usr/local/bin/etcd"]
LABEL org.opencontainers.image.version="3.6.14-ics.1" \
      org.opencontainers.image.source="https://github.com/etcd-io/etcd" \
      org.ics.security.go="1.27.1" \
      org.ics.security.grpc="1.83.1"
