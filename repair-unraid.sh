#!/usr/bin/env bash
# Recreate the failed runtime with an explicit Python entrypoint; preserve driver image and data.
set -euo pipefail
data_dir=/mnt/user/appdata/scanmail
[[ -f "$data_dir/runtime.env" ]] || { echo 'runtime.env mangler. Stopper uden ændringer.'; exit 1; }
image_ready=$(docker inspect --type container --format '{{.Image}}' scanmail)
docker image inspect "$image_ready" >/dev/null
backup="scanmail-before-repair-$(date +%Y%m%d-%H%M%S)"
docker stop scanmail >/dev/null
docker rename scanmail "$backup"
printf 'Tidligere container bevaret som %s. Genbruger samme image og appdata.\n' "$backup"
docker run -d --name scanmail --restart unless-stopped --entrypoint python3 \
  --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges:true \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m,mode=1777 \
  --memory 1536m --cpus 2 --pids-limit 128 --log-opt max-size=5m --log-opt max-file=2 \
  -p 8788:8080 -v "$data_dir:/data" --env-file "$data_dir/runtime.env" \
  --label 'net.unraid.docker.managed=dockerman' \
  --label 'net.unraid.docker.webui=http://[IP]:[PORT:8080]/' \
  "$image_ready" /app/server.py
printf '\nKontrollerer lokal HTTP i op til cirka 20 sekunder ...\n'
if curl --fail --silent --show-error --max-time 2 --retry 8 --retry-delay 1 --retry-connrefused http://127.0.0.1:8788/healthz; then
  printf '\nÅbn http://DIN-UNRAID-IP:8788\n'
else
  printf '\nAppen svarer ikke endnu. Seneste log:\n'
  docker logs --tail 40 scanmail
  exit 1
fi
