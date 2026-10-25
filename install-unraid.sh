#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
data_dir=/mnt/user/appdata/scanmail
image_base=scanmail:0.3.0-base
image_ready=scanmail:0.3.0-hp
setup_container="scanmail-driver-setup-$$"
printf '\nScanMail 0.3.0 · HP M176n · 172.16.60.252\n\n'
command -v docker >/dev/null || { echo 'Docker er ikke tilgængelig. Kør dette fra Unraid-terminalen.'; exit 1; }
if docker container inspect scanmail >/dev/null 2>&1; then
  echo 'Containeren scanmail findes allerede. Stop her for at beskytte installationen.'
  echo 'Se README.md for genstart og opdatering.'
  exit 1
fi
plugin_source="${SCANMAIL_PLUGIN_SOURCE:-hp}"
case "$plugin_source" in
  hp|openprinting) ;;
  *) echo 'SCANMAIL_PLUGIN_SOURCE skal være hp eller openprinting.'; exit 1 ;;
esac
docker build -t "$image_base" .
printf '\nInstaller nu HP-pluginet. Læs og besvar HP-guidens spørgsmål.\n'
if [[ "$plugin_source" == openprinting ]]; then
  printf 'Henter versionsmatchende plugin og signatur fra OpenPrinting via HTTPS.\n'
  printf 'HP-guiden åbnes med lokal fil. Accepter kun licensen, hvis du er enig.\n'
else
  printf 'Vælg download, og accepter kun licensen, hvis du er enig.\n'
fi
printf 'Stop ved signaturfejl. Svar nej, hvis guiden tilbyder installation uden kontrol.\n\n'
trap 'docker rm -f "$setup_container" >/dev/null 2>&1 || true' EXIT
docker run --name "$setup_container" --user 0:0 --env "SCANMAIL_PLUGIN_SOURCE=$plugin_source" --entrypoint sh -it "$image_base" -c '
  set -eu
  export HOME=/root
  if [ "$SCANMAIL_PLUGIN_SOURCE" = openprinting ]; then
    cd /usr/share/hplip
    hp_version=$(python3 -c "from base.g import prop; print(prop.installed_version)")
    plugin_dir=$(mktemp -d /tmp/scanmail-plugin.XXXXXX)
    plugin_name="hplip-${hp_version}-plugin.run"
    for suffix in "" .asc; do
      wget --https-only --timeout=30 --tries=2 \
        -O "$plugin_dir/$plugin_name$suffix" \
        "https://www.openprinting.org/download/printdriver/auxfiles/HP/plugins/$plugin_name$suffix"
      test -s "$plugin_dir/$plugin_name$suffix"
    done
    hp-plugin -i -p "$plugin_dir/$plugin_name"
    rm -rf "$plugin_dir"
  else
    hp-plugin -i
  fi
  test -f /var/lib/hp/hplip.state
  find /usr/share/hplip/scan/plugins -name "bb_marvell*.so" -type f | grep -q .
'
# hp-plugin must complete successfully. Never accept a failed signature check.

# The stopped filesystem can be committed without the user's data or credentials.
docker commit --change 'USER 1000:1000' --change 'ENTRYPOINT ["python3"]' --change 'ENV HOME=/tmp' \
  --change 'CMD ["/app/runtime.py"]' "$setup_container" "$image_ready" >/dev/null
docker run --rm --entrypoint sh "$image_ready" -c \
  'find /usr/share/hplip/scan/plugins -name "bb_marvell*.so" -type f | grep -q .'
docker rm -f "$setup_container" >/dev/null
trap - EXIT
archive_dir=/mnt/user/appdata/scanmail-images
mkdir -p "$archive_dir"
chmod 700 "$archive_dir"
# Unraid can recreate docker.img. Keep the licensed local image on persistent storage.
umask 077
docker image save "$image_ready" | gzip > "$archive_dir/scanmail-0.3.0-hp.tar.gz.tmp"
mv "$archive_dir/scanmail-0.3.0-hp.tar.gz.tmp" "$archive_dir/scanmail-0.3.0-hp.tar.gz"
mkdir -p "$data_dir"
chmod 700 "$data_dir"
chown 1000:1000 "$data_dir"
if [[ ! -f "$data_dir/runtime.env" ]]; then
  while true; do
    read -r -s -p 'Vælg adgangskode til websiden (mindst 12 tegn): ' scanmail_password
    printf '\n'
    if [[ ${#scanmail_password} -lt 12 ]]; then echo 'Brug mindst 12 tegn.'; continue; fi
    read -r -s -p 'Gentag adgangskoden: ' scanmail_repeat
    printf '\n'
    [[ "$scanmail_password" == "$scanmail_repeat" ]] && break
    echo 'Adgangskoderne er forskellige. Prøv igen.'
  done
  password_hash=$(printf '%s' "$scanmail_password" | docker run --rm -i --entrypoint python3 "$image_ready" -c \
    'import hashlib,secrets,sys; salt=secrets.token_bytes(16); password=sys.stdin.buffer.read(); print(salt.hex()+":"+hashlib.pbkdf2_hmac("sha256",password,salt,260000).hex())')
  unset scanmail_password scanmail_repeat
  umask 077
  printf 'SCANMAIL_PASSWORD_HASH=%s\nSCANNER_IP=172.16.60.252\n' "$password_hash" > "$data_dir/runtime.env"
  unset password_hash
  chmod 600 "$data_dir/runtime.env"
  chown 1000:1000 "$data_dir/runtime.env"
fi
docker run -d --init --name scanmail --restart unless-stopped --entrypoint python3 \
  --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges:true \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m,mode=1777 \
  --memory 1536m --cpus 2 --pids-limit 128 --log-opt max-size=5m --log-opt max-file=2 \
  -p 8788:8080 -v "$data_dir:/data" --env-file "$data_dir/runtime.env" \
  --label 'net.unraid.docker.managed=dockerman' \
  --label 'net.unraid.docker.webui=http://[IP]:[PORT:8080]/' \
  "$image_ready" /app/runtime.py >/dev/null
printf '\nScanMail er startet. Åbn http://DIN-UNRAID-IP:8788\n'
printf 'Log ind, åbn Indstillinger, og tryk Test scanner.\n'
printf 'Scan først et fysisk dokument og download PDF. Opsæt derefter Gmail lokalt.\n'
