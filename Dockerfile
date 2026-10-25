FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pil python3-reportlab hplip libsane-hpaio sane-utils \
    ca-certificates gnupg dirmngr wget dbus python3-dbus util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data && chown 1000:1000 /data \
    && printf 'hpaio\n' > /etc/sane.d/dll.conf
WORKDIR /app
COPY app/ /app/
RUN python3 /app/ensure_identity.py
USER 1000:1000
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3)" || exit 1
CMD ["python3", "/app/runtime.py"]
