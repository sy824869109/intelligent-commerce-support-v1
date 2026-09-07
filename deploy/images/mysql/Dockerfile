# Rebuild only the privilege-drop helper with the fixed Go toolchain.
FROM docker.io/library/golang:1.27.1-alpine3.24@sha256:cf6fca6641884b8433441b2b0652976f975e1d0fdd26d177eaaf8596087f3125 AS gosu-build
ARG GOSU_SHA256=cd9719b775dbfedae53923c9b0dc792b66d42c51e0b36652ed6f747fbadc0164
WORKDIR /src
RUN set -eux; wget -O source.tar.gz \
      https://github.com/tianon/gosu/archive/refs/tags/1.19.tar.gz \
    && echo "${GOSU_SHA256}  source.tar.gz" | sha256sum -c \
    && tar --extract --gzip --strip-components=1 --file source.tar.gz \
    && CGO_ENABLED=0 GOTOOLCHAIN=local go build -mod=readonly -trimpath -buildvcs=false \
      -ldflags='-s -w' -o /out/gosu . \
    && go version -m /out/gosu | grep -F $'build\tCGO_ENABLED=0'

FROM docker.io/library/mysql:8.4.11-oraclelinux9@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb

USER root
RUN microdnf update -y \
    && microdnf clean all \
    && rm -rf /var/cache/dnf /usr/bin/mysqlsh /usr/share/mysqlsh /usr/lib/mysqlsh \
    && grep -q 'exec gosu mysql' /usr/local/bin/docker-entrypoint.sh
COPY --from=gosu-build --chown=root:root --chmod=0755 /out/gosu /usr/local/bin/gosu
RUN gosu --version \
    && mysqld --version

LABEL org.opencontainers.image.version="8.4.11-ics.1" \
      org.opencontainers.image.source="https://github.com/docker-library/mysql" \
      org.ics.security.gosu="1.19-go1.27.1"
