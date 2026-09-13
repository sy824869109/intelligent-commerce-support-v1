# Official stable patch plus the audited Alpine libuuid security fix.
FROM nginx:1.30.4-alpine@sha256:dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c
USER root
RUN apk add --no-cache libuuid=2.42.3-r1
LABEL org.ics.purpose="environment-toolkit" org.ics.security.libuuid="2.42.3-r1"
