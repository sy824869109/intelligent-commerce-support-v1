# New-platform derivative: same Redis release, only refresh fixed Alpine packages.
FROM docker.io/library/redis:8.8.2-alpine3.23@sha256:96cb544fa0af5aa898d160cffb7dae70c3df117190fc123831c64712cda425ff

USER root
RUN apk add --no-cache --upgrade \
      libcrypto3=3.5.8-r0 libssl3=3.5.8-r0 setpriv=2.41.6-r1 \
    && test "$(apk info -e libssl3)" = libssl3 \
    && test -x /bin/setpriv \
    && redis-server --version

LABEL org.opencontainers.image.version="8.8.2-ics.1" \
      org.opencontainers.image.source="https://github.com/redis/redis" \
      org.ics.security.derivative="alpine-security-refresh-20260907"
