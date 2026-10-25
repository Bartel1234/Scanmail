#!/usr/bin/env bash
# Build/test first, then switch. On failure restore the previous container.
set -euo pipefail
cd -- "$(dirname -- "$0")"
umask 077
data_dir=${SCANMAIL_DATA_DIR:-/mnt/user/appdata/scanmail}
archive_dir=${SCANMAIL_ARCHIVE_DIR:-/mnt/user/appdata/scanmail-images}
port=${SCANMAIL_PORT:-8788}
[[ "$port" =~ ^[0-9]+$ ]] && ((port >= 1 && port <= 65535)) || { echo 'Ugyldig port.'; exit 1; }
[[ -f "$data_dir/runtime.env" ]] || { echo 'runtime.env mangler. Installer ScanMail først.'; exit 1; }
exec 9> "$data_dir/update.lock"
flock -n 9 || { echo 'En anden opdatering kører allerede.'; exit 1; }
parent=$(docker inspect --type container --format '{{.Image}}' scanmail)
restart_policy=$(docker inspect --type container --format '{{.HostConfig.RestartPolicy.Name}}' scanmail)
[[ -n "$restart_policy" ]] || restart_policy=unless-stopped
stamp="$(date +%Y%m%d-%H%M%S)-$$"
parent_tag="scanmail:driver-parent-$stamp"
candidate="scanmail:0.3.1-$stamp"
backup="scanmail-backup-$stamp"
smoke="scanmail-smoke-$stamp"
old_stopped=0
renamed=0
success=0
candidate_id=''
rollback() {
  code=$?
  trap - EXIT INT TERM
  docker rm -f "$smoke" >/dev/null 2>&1 || true
  if [[ "$success" == 0 && "$old_stopped" == 1 ]]; then
    echo 'Opdatering fejlede. Gendanner den tidligere container ...'
    if [[ "$renamed" == 1 ]]; then
      running_image=$(docker inspect --type container --format '{{.Image}}' scanmail 2>/dev/null || true)
      if [[ -n "$running_image" && "$running_image" == "$candidate_id" ]]; then
        docker rm -f scanmail >/dev/null || true
      fi
      if docker rename "$backup" scanmail; then
        docker update --restart="$restart_policy" scanmail >/dev/null || true
      else
        echo "Automatisk gendannelse blev afvist. Den gamle container hedder $backup."
        exit 1
      fi
    fi
    docker start scanmail >/dev/null || { echo 'Den gamle container kunne ikke startes. Kontrollér Docker.'; exit 1; }
    echo 'Den tidligere container er startet igen.'
  fi
  exit "$code"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker tag "$parent" "$parent_tag"
echo 'Bygger opdateringen med dit eksisterende HP-plugin ...'
docker build --pull=false --build-arg "SCANMAIL_PARENT_IMAGE=$parent_tag" \
  -f Dockerfile.update -t "$candidate" .
candidate_id=$(docker image inspect --format '{{.Id}}' "$candidate")
# Exercise identity, private D-Bus, driver state, OCR, PDF and Python startup offline.
docker run --rm --init --network none --user 1000:1000 \
  --cap-drop ALL --security-opt no-new-privileges:true --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m,mode=1777 \
  --entrypoint python3 "$candidate" -c '
import configparser, os, pwd, subprocess, tempfile
from runtime import start_bus
pwd.getpwuid(os.getuid())
start_bus()
subprocess.run(["dbus-send", "--system", "--type=method_call", "--print-reply",
 "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
 check=True, stdout=subprocess.DEVNULL)
config = configparser.ConfigParser()
config.read("/etc/hp/hplip.conf")
state = configparser.ConfigParser()
state.read("/var/lib/hp/hplip.state")
assert config.get("hplip", "version") == state.get("plugin", "version"), "HP-pluginversion matcher ikke HPLIP"
languages = subprocess.check_output(["tesseract", "--list-langs"], text=True).splitlines()
assert "dan" in languages and "eng" in languages, "OCR-sprog mangler"
os.environ["DATA_DIR"] = tempfile.mkdtemp()
import server
from PIL import Image, ImageDraw, ImageFont
folder = server.WORK / ("a" * 32)
folder.mkdir()
image = Image.new("RGB", (1200, 500), "white")
# Pillow default bitmap font is sufficient for pipeline smoke testing.
ImageDraw.Draw(image).text((50, 100), "SCANMAIL TEST", fill="black")
image.save(folder / "1.jpg")
job = dict(id="a"*32, pages=1, dpi=150, ocr=True, quality="small", status="processing")
pdf = server.make_pdf(job)
assert pdf.startswith(b"%PDF-") and job["pdf_ready"]
print("Bruger, privat D-Bus, pluginversion og OCR/PDF fungerer.")
'
# Run the actual app on an internal port, isolated from LAN, printer and SMTP.
# It receives an ephemeral data volume and a dummy hash; no account files are mounted.
docker run -d --init --name "$smoke" --network none --user 1000:1000 \
  --cap-drop ALL --security-opt no-new-privileges:true --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m,mode=1777 \
  -e DATA_DIR=/tmp/scanmail-data -e "SCANMAIL_PASSWORD_HASH=11111111111111111111111111111111:$(printf '%064d' 0)" \
  --entrypoint python3 "$candidate" /app/runtime.py >/dev/null
healthy=0
for attempt in {1..15}; do
  if docker exec "$smoke" python3 -c 'import json,urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=2))["version"] == "0.3.1"' >/dev/null 2>&1; then
    healthy=1; break
  fi
  sleep 1
done
[[ "$healthy" == 1 ]] || { echo 'Den nye app bestod ikke opstartstesten.'; docker logs --tail 30 "$smoke"; exit 1; }
docker rm -f "$smoke" >/dev/null
mkdir -p "$archive_dir"
chmod 700 "$archive_dir"
docker image save "$candidate" | gzip > "$archive_dir/scanmail-0.3.1-$stamp.tar.gz.tmp"
mv "$archive_dir/scanmail-0.3.1-$stamp.tar.gz.tmp" "$archive_dir/scanmail-0.3.1-$stamp.tar.gz"
echo 'Testene bestod. Skifter container. Midlertidige scans forsvinder; indstillinger bevares.'
old_stopped=1
docker stop scanmail >/dev/null
docker rename scanmail "$backup"
renamed=1
docker update --restart=no "$backup" >/dev/null
docker run -d --init --name scanmail --restart unless-stopped --entrypoint python3 \
  --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges:true \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m,mode=1777 \
  --memory 1536m --cpus 2 --pids-limit 128 --log-opt max-size=5m --log-opt max-file=2 \
  -p "$port:8080" -v "$data_dir:/data" --env-file "$data_dir/runtime.env" \
  --label 'net.unraid.docker.managed=dockerman' \
  --label 'net.unraid.docker.webui=http://[IP]:[PORT:8080]/' \
  "$candidate" /app/runtime.py >/dev/null
healthy=0
for attempt in {1..15}; do
  if docker exec scanmail python3 -c 'import json,urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=2))["version"] == "0.3.1"' >/dev/null 2>&1; then
    healthy=1; break
  fi
  sleep 1
done
[[ "$healthy" == 1 ]] || { echo 'Den nye container svarer ikke korrekt.'; docker logs --tail 30 scanmail; exit 1; }
success=1
printf '\nScanMail 0.3.1 er klar på http://DIN-UNRAID-IP:%s\nBackup: %s (autostart slået fra)\n' "$port" "$backup"
printf 'Test en fysisk scanning og PDF-download før mail.\n'
