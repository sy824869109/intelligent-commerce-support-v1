FROM grafana/loki:3.7.7@sha256:d70e4659623f3e109af669cae76fe2a5dd5be54e2298fe8aed380d982fbc2500
COPY --chmod=755 loki /usr/bin/loki
COPY build.json /ics-build.json
LABEL org.ics.purpose="environment-toolkit" org.ics.upstream.version="3.7.7" org.ics.security.grpc="1.83.2"
