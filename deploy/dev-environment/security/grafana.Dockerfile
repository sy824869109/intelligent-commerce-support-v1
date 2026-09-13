# Maintain the official UI, plugins and startup scripts. Backend patch uses upstream
# supported pure-Go SQLite; actual SQLite migrations and datasources must be tested.
FROM grafana/grafana:12.4.10@sha256:c132a683b2430fff9115a29b2a79c8ab97540cdcc90846e3c81878c778ca3596
USER root
RUN apk add --no-cache libcrypto3=3.5.8-r0 libssl3=3.5.8-r0
COPY --chmod=755 grafana /usr/share/grafana/bin/grafana
COPY build.json /usr/share/grafana/ics-build.json
LABEL org.ics.purpose="environment-toolkit" org.ics.upstream.version="12.4.10" org.ics.security.grpc="1.83.2"
USER 472
