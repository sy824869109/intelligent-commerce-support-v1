# Keep the reviewed upstream runtime filesystem, replace the Collector with the
# OCB distribution containing every component required by observability/otel.yaml.
FROM otel/opentelemetry-collector-contrib:0.160.0@sha256:799dc6cf12c96192af37b5bdba804da8c10b3bc563b43cb90c3f3c58d9572ad6
COPY --chmod=755 distribution/ics-otelcol /otelcol-contrib
COPY build.json /ics-build.json
LABEL org.ics.purpose="environment-toolkit" org.ics.distribution="otlp-metrics-logs-traces" org.ics.upstream.version="0.160.0"
