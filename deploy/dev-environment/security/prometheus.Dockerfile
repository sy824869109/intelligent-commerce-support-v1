# Preserve the official LTS filesystem/configuration; replace only patched server and promtool.
FROM prom/prometheus:v3.13.3@sha256:6976aa8a60fec930796ce5772b8d12da7a318a5daa8d40d69c5c7819a05eeed7
COPY --chmod=755 prometheus /bin/prometheus
COPY --chmod=755 promtool /bin/promtool
COPY build.json /usr/share/ics-build/prometheus.json
LABEL org.ics.purpose="environment-toolkit" org.ics.upstream.version="3.13.3" org.ics.security.grpc="1.83.2"
