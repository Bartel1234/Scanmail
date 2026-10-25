#!/usr/bin/env bash
# Repair HPLIP identity and private D-Bus while preserving licensed driver and settings.
cd -- "$(dirname -- "$0")"
set -euo pipefail
data_dir=/mnt/user/appdata/scanmail
[[ -f "$data_dir/runtime.env" ]] || { echo 'runtime.env mangler. Stopper uden ændringer.'; exit 1; }
parent_image=$(docker inspect --type container --format '{{.Image}}' scanmail)
docker image inspect "$parent_image" >/dev/null
parent_tag="scanmail:0.2.0-driver-parent-$(date +%Y%m%d-%H%M%S)"
docker tag "$parent_image" "$parent_tag"
image_ready=scanmail:0.2.0-runtime-fixed
docker build --pull=false --build-arg "SCANMAIL_PARENT_IMAGE=$parent_tag" \
  -f Dockerfile.repair -t "$image_ready" .
# Check identity and an actual D-Bus method call with the same read-only runtime.
# No connection to the scanner, SMTP, or host D-Bus is made here.
docker run --rm --init --network none --user 1000:1000 \
  --cap-drop ALL --security-opt no-new-privileges:true --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 \
  --entrypoint python3 "$image_ready" -c '
from runtime import start_bus
import subprocess
start_bus()
subprocess.run(["dbus-send", "--system", "--type=method_call", "--print-reply",
                "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus.ListNames"], check=True, stdout=subprocess.DEVNULL)
print("Brugerpost og privat D-Bus fungerer.")
'
archive_dir=/mnt/user/appdata/scanmail-images
mkdir -p "$archive_dir"
chmod 700 "$archive_dir"
umask 077
docker image save "$image_ready" | gzip > "$archive_dir/scanmail-0.2.0-runtime-fixed.tar.gz.tmp"
mv "$archive_dir/scanmail-0.2.0-runtime-fixed.tar.gz.tmp" "$archive_dir/scanmail-0.2.0-runtime-fixed.tar.gz"
backup="scanmail-before-repair-$(date +%Y%m%d-%H%M%S)"
docker stop scanmail >/dev/null
docker rename scanmail "$backup"
printf 'Tidligere container bevaret som %s. Genbruger HP-plugin og appdata med rettet runtime.\n' "$backup"
docker run -d --init --name scanmail --restart unless-stopped --entrypoint python3 \
  --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges:true \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m,mode=1777 \
  --memory 1536m --cpus 2 --pids-limit 128 --log-opt max-size=5m --log-opt max-file=2 \
  -p 8788:8080 -v "$data_dir:/data" --env-file "$data_dir/runtime.env" \
  --label 'net.unraid.docker.managed=dockerman' \
  --label 'net.unraid.docker.webui=http://[IP]:[PORT:8080]/' \
  "$image_ready" /app/runtime.py
printf '\nKontrollerer lokal HTTP i op til cirka 20 sekunder ...\n'
if curl --fail --silent --show-error --max-time 2 --retry 8 --retry-delay 1 --retry-connrefused http://127.0.0.1:8788/healthz; then
  printf '\nÅbn http://DIN-UNRAID-IP:8788\n'
else
  printf '\nAppen svarer ikke endnu. Seneste log:\n'
  docker logs --tail 40 scanmail
  exit 1
fi
