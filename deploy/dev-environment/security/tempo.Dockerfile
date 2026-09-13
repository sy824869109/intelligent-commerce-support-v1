FROM grafana/tempo:3.0.3@sha256:0296560ac66f8a3600d7fb3014a52c189d4d9c3549ad6ff441bf2409855d68d5
COPY --chmod=755 tempo /tempo
COPY build.json /ics-build.json
LABEL org.ics.purpose="environment-toolkit" org.ics.upstream.version="3.0.3" org.ics.security.grpc="1.83.2"
