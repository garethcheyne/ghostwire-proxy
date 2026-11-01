#!/usr/bin/env bash
# Ghostwire Proxy: install it on a new server, from a clone of the repository.
#
#   git clone https://github.com/garethcheyne/ghostwire-proxy.git && cd ghostwire-proxy
#   ./installGhostwireProxy.sh                   install (asks a few questions first)
#   ./installGhostwireProxy.sh --yes             don't ask: answers from the GW_* variables below, or defaults
#   ./installGhostwireProxy.sh --check           say what an install would do; change nothing
#   ./installGhostwireProxy.sh --settings-only   write .env and stop (to edit it before the first start)
#
# Or in one go, which clones into /opt/ghostwire-proxy (or GW_DIR) and runs this from there:
#   curl -fsSL https://raw.githubusercontent.com/garethcheyne/ghostwire-proxy/main/installGhostwireProxy.sh | sudo bash
#
# Answers can be given up front (and must be, with --yes, where there's no default):
#   GW_URL             where the admin panel is opened (default: http://<this server>:88). An https
#                      address with a domain gets its own proxy host and Let's Encrypt certificate on
#                      the first start, so its DNS has to point here first.
#   GW_ADMIN_EMAIL     the first admin's email, which they sign in with; Let's Encrypt writes to it
#   GW_ADMIN_NAME      the first admin's name (default: Administrator)
#   GW_ADMIN_PASSWORD  at least 12 characters (default: a random one, shown once at the end)
#
# Every Ghostwire app has one of these at its root, with the same options and steps:
#   1 Pre-flight  2 Settings  3 Build  4 Start  5 Health check  6 Admin account  7 Done
# It sets up a new install only; upgradeGhostwireProxy.sh upgrades it from then on. It makes .env
# from .env.example with random secrets, and a run that stops part way carries on when run again.
# It needs ports 80 and 443 (the proxy), 88 (the admin panel) and 8089 (the API). The log of each
# run goes in data/backups/. The "This app" part below is what differs between apps; the "Common"
# part is the same in all.

set -Eeuo pipefail

# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  This app
# ═══════════════════════════════════════════════════════════════════════════════════════════════

app_settings() {
  APP_NAME="Ghostwire Proxy"
  INSTALLER=installGhostwireProxy.sh
  UPGRADER=upgradeGhostwireProxy.sh
  REPO_URL="https://github.com/garethcheyne/ghostwire-proxy.git"
  DEFAULT_DIR=/opt/ghostwire-proxy
  BACKUP_DIR=data/backups
  MIN_FREE_GB=5
  MIN_MEMORY_GB=2
  FIXED_PORTS="80 443 88 8089"
  # docker-compose.yml refuses to load without it, and .env doesn't exist yet during pre-flight.
  PREFLIGHT_ENV="POSTGRES_PASSWORD=preflight"
  HEALTH_URLS="http://localhost:8089/health http://localhost:88/api/health"
}

# The admin account isn't kept in .env, so a run that carries on asks for it again.
app_questions() {
  if [ "$RESUME" = true ]; then
    GW_URL=$(env_value NEXTAUTH_URL)
  else
    ask GW_URL "Address the admin panel will be opened at" "http://$(server_address):88" check_url
    GW_URL=$(as_url "$GW_URL")
  fi
  ask GW_ADMIN_EMAIL "The first admin's email (they sign in with it)" "$(default_admin_email "$GW_URL")" check_email
  ask GW_ADMIN_NAME "The first admin's name" "Administrator" check_required
  ask_password GW_ADMIN_PASSWORD "The first admin's password"
}

app_summary() {
  summary_line "Admin panel" "$GW_URL"
  summary_line "Admin" "$GW_ADMIN_NAME <$GW_ADMIN_EMAIL>"
  summary_line "Ports" "80 and 443 (proxy hosts), 88 (admin panel), 8089 (API)"
  case "$GW_URL" in
    https://*)
      if [[ ! "$(url_host "$GW_URL")" =~ ^[0-9.]+$ ]] && [ "$(url_host "$GW_URL")" != localhost ]; then
        info "On its first start the API gives $(url_host "$GW_URL") a proxy host and a Let's Encrypt"
        info "certificate, so its DNS must point at this server, with ports 80 and 443 open."
      fi
      ;;
    *) warn "Plain http: fine on a private network; use an https address for anything else." ;;
  esac
}

app_env() {
  local origin
  env_secret POSTGRES_PASSWORD 40
  env_secret BETTER_AUTH_SECRET 48
  env_secret JWT_SECRET 64
  env_secret ENCRYPTION_KEY 48
  env_secret NEXTAUTH_SECRET 48
  env_hex INTERNAL_AUTH_TOKEN 32
  env_set NEXTAUTH_URL "$GW_URL"
  # Only for one https address: it makes the session cookie Secure (see .env.example).
  case "$GW_URL" in https://*) env_set BETTER_AUTH_URL "$GW_URL" ;; esac
  origin=$(url_origin "$GW_URL")
  if [ "$origin" = http://localhost:88 ]; then env_set CORS_ORIGINS "$origin"; else env_set CORS_ORIGINS "$origin,http://localhost:88"; fi
  env_set LETSENCRYPT_EMAIL "$GW_ADMIN_EMAIL"
  env_set VAPID_EMAIL "mailto:$GW_ADMIN_EMAIL"
}

app_ready() { APP_URL=$(env_value NEXTAUTH_URL); }

# The API first (it runs the migrations), then the rest, as the upgrade does.
app_start() {
  docker compose up -d ghostwire-proxy-api
  if wait_for_url http://localhost:8089/health 600; then
    ok "The API is up (the database is migrated)."
  else
    warn "The API isn't answering after 10 minutes; starting the rest anyway."
  fi
  docker compose up -d --remove-orphans
}

json_string() {
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}
  printf '"%s"' "$s"
}

# The API's first-run setup (POST /api/setup/initialize), which only works while there are no users:
# the same one the sign-in page uses, done here so the panel is never open without an account.
app_admin() {
  local state
  state=$(curl -fsS -m 10 http://localhost:8089/api/setup/check) || fail "The API's setup check didn't answer."
  if [[ ! "$state" =~ \"setup_required\":\ ?true ]]; then
    warn "An account already exists, so no new one was made."
    ADMIN_LOGIN="your existing account"
    PASSWORD_SOURCE="" GENERATED_PASSWORD=""
    return 0
  fi
  printf '{"email":%s,"name":%s,"password":%s}' "$(json_string "$GW_ADMIN_EMAIL")" \
    "$(json_string "$GW_ADMIN_NAME")" "$(json_string "$GW_ADMIN_PASSWORD")" \
    | curl -fsS -m 30 -o /dev/null -H 'Content-Type: application/json' --data-binary @- \
      http://localhost:8089/api/setup/initialize \
    || fail "The API didn't take the admin account (docker compose logs ghostwire-proxy-api shows why)."
  ok "Made the admin account: $GW_ADMIN_EMAIL."
  ADMIN_LOGIN=$GW_ADMIN_EMAIL
}

app_done() {
  summary_line "Next" "point your sites' DNS here and add them as proxy hosts; keep 8089 (the API) private"
}

# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  Common: the same in every Ghostwire app's installGhostwire<App>.sh. Change it in all of them together.
#  A hook the app section above doesn't define uses the default here.
# ═══════════════════════════════════════════════════════════════════════════════════════════════

if [ -t 1 ]; then
  B=$'\033[1m' G=$'\033[32m' Y=$'\033[33m' R=$'\033[31m' N=$'\033[0m'
else
  B="" G="" Y="" R="" N=""
fi

# ── Output ──────────────────────────────────────────────────────────────────────────────────────
step() { printf '\n%s[%s/%s] %s%s\n' "$B" "$1" "$STEPS" "$2" "$N"; }
info() { printf '  %s\n' "$*"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; }
fail() { printf '\n  %s✗ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }
summary_line() { printf '  %-12s %s\n' "$1" "$2"; }

# ── Questions ───────────────────────────────────────────────────────────────────────────────────
# Questions are read from the terminal, not stdin, so the script can be piped from curl.

# confirm "question": --yes answers yes; with no terminal to ask on, the run stops.
confirm() {
  local answer=""
  [ "$YES" = true ] && return 0
  [ -n "$TTY" ] || fail "No terminal to ask on. Run with --yes (answers from the GW_* variables)."
  read -r -p "  $1 [Y/n] " answer < "$TTY" || answer=""
  [[ ! "$answer" =~ ^[Nn] ]]
}

# ask VAR "question" [default] [check]: VAR keeps a value it already has (a GW_* variable).
# Otherwise --yes (and --check) take the default, and the terminal is asked. check is a function
# that prints what's wrong with an answer, or nothing.
ask() {
  local var=$1 question=$2 default=${3:-} check=${4:-} answer problem preset=false
  [ -n "${!var:-}" ] && preset=true
  while :; do
    if [ "$preset" = true ]; then
      answer=${!var}
    elif [ "$YES" = true ] || [ "$CHECK" = true ]; then
      answer=$default
    else
      [ -n "$TTY" ] || fail "No terminal to ask on. Set $var, or run with --yes for the defaults."
      if [ -n "$default" ]; then
        read -r -p "  $question [$default]: " answer < "$TTY" || answer=""
      else
        read -r -p "  $question: " answer < "$TTY" || answer=""
      fi
      answer=${answer:-$default}
    fi
    problem=""
    [ -z "$check" ] || problem=$("$check" "$answer")
    if [ -z "$problem" ]; then
      printf -v "$var" '%s' "$answer"
      return 0
    fi
    if [ "$CHECK" = true ] && [ "$preset" = false ]; then
      warn "$var: $problem (it would be asked)"
      printf -v "$var" '%s' "$answer"
      return 0
    fi
    [ "$preset" = false ] && [ "$YES" = false ] || fail "$var: $problem"
    warn "$problem"
  done
}

# ask_password VAR "question": typed twice and never shown; Enter (or --yes) makes a random one,
# which is shown once at the very end.
ask_password() {
  local var=$1 question=$2 first second problem
  if [ -n "${!var:-}" ]; then
    problem=$(check_password "${!var}")
    [ -z "$problem" ] || fail "$var: $problem"
    PASSWORD_SOURCE=given
    return 0
  fi
  if [ "$YES" = true ] || [ "$CHECK" = true ]; then
    GENERATED_PASSWORD=$(random_secret 24)
    printf -v "$var" '%s' "$GENERATED_PASSWORD"
    PASSWORD_SOURCE=random
    return 0
  fi
  [ -n "$TTY" ] || fail "No terminal to ask on. Set $var, or run with --yes for a random one."
  while :; do
    read -r -s -p "  $question (Enter for a random one): " first < "$TTY" || first=""
    echo
    if [ -z "$first" ]; then
      GENERATED_PASSWORD=$(random_secret 24)
      printf -v "$var" '%s' "$GENERATED_PASSWORD"
      PASSWORD_SOURCE=random
      return 0
    fi
    problem=$(check_password "$first")
    if [ -n "$problem" ]; then warn "$problem"; continue; fi
    read -r -s -p "  Type it again: " second < "$TTY" || second=""
    echo
    if [ "$first" = "$second" ]; then
      printf -v "$var" '%s' "$first"
      PASSWORD_SOURCE=typed
      return 0
    fi
    warn "They didn't match; try again."
  done
}

# ── Checks for answers (print the problem, or nothing) ──────────────────────────────────────────
check_required() { [ -n "$1" ] || echo "This can't be empty."; }
check_url() {
  local url
  url=$(as_url "$1")
  [[ "$url" =~ ^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$ ]] \
    || echo "Give an address like https://app.example.com (or app.example.com)."
}
check_email() {
  [[ "$1" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$ ]] || echo "Give an email address like you@example.com."
}
check_password() {
  if [ ${#1} -lt 12 ]; then echo "The password needs at least 12 characters."
  elif [ ${#1} -gt 128 ]; then echo "The password can have at most 128 characters."
  elif [[ "$1" == *"'"* ]] || [[ "$1" =~ [[:cntrl:]] ]]; then echo "The password can't hold a ' or control characters."
  fi
}
check_port() {
  if ! [[ "$1" =~ ^[0-9]{1,5}$ ]] || [ "$1" -lt 1 ] || [ "$1" -gt 65535 ]; then echo "Give a port number (1-65535)."
  elif [ "$RESUME" = false ] && port_in_use "$1"; then echo "Port $1 is already in use on this server."
  fi
}
check_yes_no() { [[ "$1" =~ ^([Yy](es)?|[Nn]o?)$ ]] || echo "Answer yes or no."; }

# as_url "app.example.com" → https://app.example.com (no trailing slash).
as_url() {
  local url=${1%/}
  case "$url" in http://* | https://* | "") ;; *) url="https://$url" ;; esac
  printf '%s' "$url"
}
url_host() { local host=${1#*://}; host=${host%%/*}; printf '%s' "${host%%:*}"; }
url_origin() { local rest=${1#*://}; printf '%s://%s' "${1%%://*}" "${rest%%/*}"; }
is_yes() { [[ "$1" =~ ^([Yy](es)?|true|1)$ ]]; }

# An address this server can be reached at, for defaults (the first of its own addresses).
server_address() {
  local address
  address=$(hostname -I 2> /dev/null | awk '{ print $1 }') || true
  printf '%s' "${address:-localhost}"
}

# admin@<domain> when the address has a domain, else nothing (so it is asked).
default_admin_email() {
  local host
  host=$(url_host "$1")
  [[ "$host" == *.* ]] && ! [[ "$host" =~ ^[0-9.]+$ ]] && printf 'admin@%s' "$host"
  return 0
}

# ── Settings ────────────────────────────────────────────────────────────────────────────────────
# env_value KEY [default]: one value from .env, without running the file (values may hold $ or #).
env_value() {
  local value=""
  if [ -f "$PROJECT_DIR/.env" ]; then
    value=$(grep -E "^[[:space:]]*(export[[:space:]]+)?$1=" "$PROJECT_DIR/.env" | tail -n1 | cut -d= -f2- \
      | sed -e 's/[[:space:]]*$//' -e "s/^'\(.*\)'\$/\1/" -e 's/^"\(.*\)"$/\1/') || true
  fi
  printf '%s' "${value:-${2:-}}"
}

# random_secret LENGTH: letters and digits only, so it is safe in .env, a URL and SQL as it is.
random_secret() {
  local secret
  secret=$(openssl rand -base64 $(($1 * 2)) 2> /dev/null | tr -dc 'A-Za-z0-9' | head -c "$1") || true
  [ ${#secret} -eq "$1" ] || secret=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1") || true
  [ ${#secret} -eq "$1" ] || fail "Couldn't make a random secret (no openssl or /dev/urandom)."
  printf '%s' "$secret"
}

# random_hex BYTES: 2 × BYTES hex digits.
random_hex() {
  local hex
  hex=$(openssl rand -hex "$1" 2> /dev/null) || true
  [ ${#hex} -eq $(($1 * 2)) ] || hex=$(LC_ALL=C tr -dc '0-9a-f' < /dev/urandom | head -c $(($1 * 2))) || true
  [ ${#hex} -eq $(($1 * 2)) ] || fail "Couldn't make a random secret (no openssl or /dev/urandom)."
  printf '%s' "$hex"
}

sha256_of() {
  if command -v sha256sum > /dev/null; then printf '%s' "$1" | sha256sum | cut -c1-64
  else printf '%s' "$1" | shasum -a 256 | cut -c1-64; fi
}

# What the app section puts in .env: env_set KEY VALUE, env_secret KEY LENGTH, env_hex KEY BYTES,
# env_drop KEY (comments out a line .env.example has that this install doesn't use).
ENV_KEYS=() ENV_VALUES=() ENV_SECRETS="" ENV_DROPS=" "
env_set() {
  local i
  for i in "${!ENV_KEYS[@]}"; do
    if [ "${ENV_KEYS[$i]}" = "$1" ]; then ENV_VALUES[i]=$2; return 0; fi
  done
  ENV_KEYS+=("$1")
  ENV_VALUES+=("$2")
}
env_secret() { env_set "$1" "$(random_secret "$2")"; ENV_SECRETS="$ENV_SECRETS $1"; }
env_hex() { env_set "$1" "$(random_hex "$2")"; ENV_SECRETS="$ENV_SECRETS $1"; }
env_drop() { ENV_DROPS="$ENV_DROPS$1 "; }

# A value as .env holds it: as it is when that's safe, otherwise in single quotes, which docker
# compose reads literally ($ and # included). A value can't hold a single quote.
env_quote() {
  if [[ "$1" =~ ^[A-Za-z0-9_.,:/@+=-]*$ ]]; then printf '%s' "$1"; else printf "'%s'" "$1"; fi
}

# render_env FILE: .env.example with the values set above; keys it doesn't have go at the end.
# Placeholders .env.example ships with (change-this, your-..., xxxx, example.com) must not survive.
ENV_MARKER_UNFINISHED="(install not finished)"
render_env() {
  local out=$1 line key rest value i done_keys=" " live_keys left="" placeholders=""
  [ -f "$PROJECT_DIR/.env.example" ] || fail ".env.example is missing from $PROJECT_DIR."
  live_keys=" $(grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=' "$PROJECT_DIR/.env.example" \
    | sed -E 's/^[[:space:]]*(export[[:space:]]+)?//; s/=$//' | tr '\n' ' ' || true)"
  {
    printf '# Written by %s on %s %s\n' "$INSTALLER" "$(date '+%Y-%m-%d %H:%M')" "$ENV_MARKER_UNFINISHED"
    printf '# Secrets were made at random. Keep this file private (only its owner can read it) and back it\n'
    printf '# up with the data: the database password has to match the database for as long as it exists.\n\n'
    while IFS= read -r line || [ -n "$line" ]; do
      line=${line%$'\r'}
      key="" rest=""
      if [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
        key=${BASH_REMATCH[2]} rest=${BASH_REMATCH[3]}
        if [[ "$ENV_DROPS" == *" $key "* ]]; then
          printf '# %s\n' "$line"
          continue
        fi
        for i in "${!ENV_KEYS[@]}"; do
          if [ "${ENV_KEYS[$i]}" = "$key" ]; then
            printf '%s=%s\n' "$key" "$(env_quote "${ENV_VALUES[$i]}")"
            done_keys="$done_keys$key "
            continue 2
          fi
        done
        value=${rest%%[[:space:]]#*}
        if [[ "$value" =~ change-this|change_me|changeme|your-|yourdomain|xxxx|generate-a|example\.com ]]; then
          placeholders="$placeholders $key"
        fi
      elif [[ "$line" =~ ^#[[:space:]]?([A-Za-z_][A-Za-z0-9_]*)= ]]; then
        key=${BASH_REMATCH[1]}
        if [[ "$live_keys" != *" $key "* ]] && [[ "$done_keys" != *" $key "* ]]; then
          for i in "${!ENV_KEYS[@]}"; do
            if [ "${ENV_KEYS[$i]}" = "$key" ]; then
              printf '%s=%s\n' "$key" "$(env_quote "${ENV_VALUES[$i]}")"
              done_keys="$done_keys$key "
              continue 2
            fi
          done
        fi
      fi
      printf '%s\n' "$line"
    done < "$PROJECT_DIR/.env.example"
    for i in "${!ENV_KEYS[@]}"; do
      [[ "$done_keys" == *" ${ENV_KEYS[$i]} "* ]] && continue
      [ -n "$left" ] || { left=yes; printf '\n# Set by %s (not in .env.example)\n' "$INSTALLER"; }
      printf '%s=%s\n' "${ENV_KEYS[$i]}" "$(env_quote "${ENV_VALUES[$i]}")"
    done
  } > "$out"
  [ -z "$placeholders" ] || { rm -f "$out"; fail "These would keep a placeholder from .env.example:$placeholders (a bug in $INSTALLER)."; }
}

# Writes .env (mode 600 from the moment it exists), or with --check says what it would hold.
write_env() {
  local tmp
  tmp=$(umask 077 && mktemp "$PROJECT_DIR/.env.XXXXXX") || fail "Can't write in $PROJECT_DIR."
  render_env "$tmp"
  if [ "$CHECK" = true ]; then
    rm -f "$tmp"
    ok "It would write .env from .env.example (readable only by its owner)."
    info "  Random secrets:$ENV_SECRETS"
    info "  From the answers:$(for key in "${ENV_KEYS[@]}"; do [[ " $ENV_SECRETS " == *" $key "* ]] || printf ' %s' "$key"; done)"
    return 0
  fi
  chmod 600 "$tmp"
  mv -f "$tmp" "$PROJECT_DIR/.env"
  ok "Wrote .env (readable only by its owner; random secrets:$ENV_SECRETS)."
}

# The .env this script wrote, from a run that didn't finish (so the same secrets are used again).
unfinished_env() {
  [ -f "$PROJECT_DIR/.env" ] && head -n1 "$PROJECT_DIR/.env" | grep -qF "# Written by $INSTALLER" \
    && head -n1 "$PROJECT_DIR/.env" | grep -qF "$ENV_MARKER_UNFINISHED"
}

# The first line of .env says the install finished; a later run then leaves it alone.
mark_env_installed() {
  local tmp
  [ -f "$PROJECT_DIR/.env" ] || return 0
  tmp=$(mktemp)
  awk -v marker=" $ENV_MARKER_UNFINISHED" -v done_at="; installed $(date '+%Y-%m-%d %H:%M')" \
    'NR == 1 { i = index($0, marker); if (i) $0 = substr($0, 1, i - 1) done_at } { print }' \
    "$PROJECT_DIR/.env" > "$tmp"
  cat "$tmp" > "$PROJECT_DIR/.env"
  rm -f "$tmp"
}

# ── Server ──────────────────────────────────────────────────────────────────────────────────────
# Whether something on this server already listens on a TCP port (or a container publishes it).
port_in_use() {
  if command -v ss > /dev/null && ss -Htln 2> /dev/null | awk '{ print $4 }' | grep -qE "[:.]$1\$"; then return 0; fi
  if docker ps -a --format '{{.Ports}}' 2> /dev/null | grep -qE "[:.]$1->"; then return 0; fi
  (exec 3<> "/dev/tcp/127.0.0.1/$1") 2> /dev/null && return 0
  return 1
}

# The first free port from $1 upwards.
free_port() {
  local port=$1
  while port_in_use "$port"; do port=$((port + 1)); done
  printf '%s' "$port"
}

check_ports() {
  local port busy=""
  [ -n "$1" ] || return 0
  for port in $1; do port_in_use "$port" && busy="$busy $port"; done
  [ -z "$busy" ] || fail "$APP_NAME needs these ports, which are already in use on this server:$busy"
  # shellcheck disable=SC2086
  ok "Ports$(printf ' %s' $1) are free."
}

check_disk() {
  local free_kb
  free_kb=$(df -Pk "${PROJECT_DIR:-/}" 2> /dev/null | awk 'NR == 2 { print $4 }')
  if [ -n "$free_kb" ] && [ "$free_kb" -lt $((MIN_FREE_GB * 1024 * 1024)) ]; then
    fail "Only $((free_kb / 1024 / 1024)) GB free; $APP_NAME needs about ${MIN_FREE_GB} GB (docker system prune can free some)."
  fi
  ok "Disk space is fine (${MIN_FREE_GB} GB needed)."
}

check_memory() {
  local total_kb
  total_kb=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo 2> /dev/null) || true
  [ -n "$total_kb" ] || return 0
  if [ "$total_kb" -lt $((MIN_MEMORY_GB * 1000 * 1000)) ]; then
    warn "This server has $((total_kb / 1024 / 1024)) GB of memory; $APP_NAME wants at least ${MIN_MEMORY_GB} GB."
  else
    ok "Memory is fine (${MIN_MEMORY_GB} GB wanted)."
  fi
}

# ── Docker ──────────────────────────────────────────────────────────────────────────────────────
# docker compose config, with stand-ins for anything it insists on before .env exists.
compose_config() {
  # shellcheck disable=SC2086
  env $PREFLIGHT_ENV docker compose config 2> /dev/null
}

docker_requirements() {
  local tool
  for tool in git curl openssl; do
    command -v "$tool" > /dev/null || fail "$tool isn't installed."
  done
  command -v docker > /dev/null || fail "Docker isn't installed (https://docs.docker.com/engine/install/)."
  docker compose version > /dev/null 2>&1 || fail "Docker Compose v2 isn't available (docker compose)."
  docker info > /dev/null 2>&1 || fail "Can't talk to Docker (is it running? does this user need sudo, or the docker group?)."
  git -C "$PROJECT_DIR" rev-parse --git-dir > /dev/null 2>&1 \
    || fail "$PROJECT_DIR isn't a git checkout: clone the repository and run $INSTALLER from it."
  compose_config > /dev/null || fail "docker-compose.yml doesn't parse: run docker compose config to see why."
  ok "Docker $(docker version --format '{{.Server.Version}}' 2> /dev/null), Compose $(docker compose version --short 2> /dev/null), git, curl and openssl are here."
}

# Refuses a server that already runs the app: its containers, a container with one of its names,
# or its data volumes. An unfinished run of this script carries on instead.
docker_existing() {
  local config project found="" name ids dir
  if unfinished_env; then
    RESUME=true
    ok "An earlier run of $INSTALLER didn't finish; this one carries on with the .env it wrote."
    return 0
  fi
  [ -f "$PROJECT_DIR/.env" ] && fail "$APP_NAME is already set up here (.env exists). Upgrade it with $UPGRADE_CMD instead."
  config=$(compose_config) || true
  project=$(awk '/^name:/ { print $2; exit }' <<< "$config")
  # shellcheck disable=SC2086
  ids=$(env $PREFLIGHT_ENV docker compose ps -a -q 2> /dev/null) || true
  if [ -n "$ids" ]; then
    # Compose labels each container with the folder it was started from.
    dir=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "${ids%%[[:space:]]*}" 2> /dev/null) || true
    if [ -n "$dir" ] && [ "$dir" != "$PROJECT_DIR" ]; then
      fail "$APP_NAME is already installed on this server, in $dir (compose project $project). Upgrade it there with ./$UPGRADER."
    fi
    fail "The $project containers already exist. Upgrade with $UPGRADE_CMD, or remove them first (docker compose down)."
  fi
  # shellcheck disable=SC2013 # names hold no spaces
  for name in $(awk '/^    container_name:/ { print $2 }' <<< "$config"); do
    docker container inspect "$name" > /dev/null 2>&1 && found="$found $name"
  done
  [ -z "$found" ] || fail "Containers with $APP_NAME's names already exist:$found. Is it installed somewhere else on this server?"
  # shellcheck disable=SC2013
  for name in $(awk '/^volumes:/ { v = 1; next } /^[^ ]/ { v = 0 } v && /^    name:/ { print $2 }' <<< "$config"); do
    docker volume inspect "$name" > /dev/null 2>&1 && found="$found $name"
  done
  [ -z "$found" ] || fail "Data from an earlier install is still here (volumes:$found). Upgrade it with $UPGRADE_CMD, or delete the volumes to start again (docker volume rm, which deletes that data)."
  ok "Nothing of $APP_NAME is installed on this server yet."
}

build_images() {
  local out
  out=$(mktemp)
  BUILD_VERSION=$(tr -d '[:space:]' < "$PROJECT_DIR/VERSION" 2> /dev/null || true)
  BUILD_VERSION=${BUILD_VERSION:-$(git -C "$PROJECT_DIR" rev-parse --short HEAD)}
  export BUILD_VERSION
  info "Building $BUILD_VERSION (several minutes the first time)..."
  if docker compose build > "$out" 2>&1; then
    [ -n "${LOG:-}" ] && cat "$out" >> "$LOG.build"
    rm -f "$out"
    ok "Built."
  else
    tail -n 40 "$out" | sed 's/^/    /'
    [ -n "${LOG:-}" ] && cat "$out" >> "$LOG.build"
    rm -f "$out"
    fail "The build failed, so nothing was started. Fix it and run $INSTALLER again: it keeps the .env."
  fi
}

# Waits until every container is running (and healthy, where it has a healthcheck).
wait_for_containers() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT)) pending id name state health code
  info "Waiting for the containers (up to ${HEALTH_TIMEOUT}s)..."
  while :; do
    pending=""
    for id in $(docker compose ps -a -q 2> /dev/null); do
      read -r name state health code < <(docker inspect -f \
        '{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} {{.State.ExitCode}}' \
        "$id" 2> /dev/null) || continue
      name=${name#/}
      case "$state/$health" in
        running/healthy | running/none) ;;
        exited/*) [ "$code" = 0 ] || pending="$pending $name(exited $code)" ;;
        running/*) pending="$pending $name($health)" ;;
        *) pending="$pending $name($state)" ;;
      esac
    done
    if [ -z "$pending" ]; then
      ok "Every container is up and healthy."
      return 0
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      warn "Not healthy after ${HEALTH_TIMEOUT}s:$pending"
      UNHEALTHY=$pending
      return 1
    fi
    sleep 5
  done
}

# wait_for_url URL [seconds]
wait_for_url() {
  local deadline=$((SECONDS + ${2:-60}))
  until curl -fsS -o /dev/null -m 10 "$1" 2> /dev/null; do
    [ "$SECONDS" -ge "$deadline" ] && return 1
    sleep 3
  done
}

check_urls() {
  local url failed=""
  for url in $HEALTH_URLS; do
    if wait_for_url "$url" 60; then ok "Answering: $url"; else failed="$failed $url"; fi
  done
  [ -z "$failed" ] || { warn "Not answering:$failed"; return 1; }
}

compose_logs() {
  local name
  if [ -n "${UNHEALTHY:-}" ]; then
    for name in $UNHEALTHY; do
      name=${name%%(*}
      info "Last lines from $name:"
      docker logs --tail 25 "$name" 2>&1 | sed 's/^/    /' || true
    done
  else
    docker compose logs --tail 25 2>&1 | sed 's/^/    /' || true
  fi
}

# Clones the repository and runs this script from it, for `curl ... | sudo bash`.
bootstrap_clone() {
  local dir=${GW_DIR:-$DEFAULT_DIR}
  [ -n "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/docker-compose.yml" ] && return 0
  [ -n "$REPO_URL" ] || fail "Run $INSTALLER from a clone of the repository."
  command -v git > /dev/null || fail "git isn't installed."
  if [ -d "$dir/.git" ]; then
    [ -f "$dir/$INSTALLER" ] || fail "$dir already holds an older install: upgrade it with $dir/scripts/upgrade.sh."
    info "$dir already holds a clone; running its installer."
  elif [ -e "$dir" ] && [ -n "$(ls -A "$dir" 2> /dev/null)" ]; then
    fail "$dir already exists and isn't a clone of $REPO_URL (set GW_DIR to install somewhere else)."
  else
    info "Downloading $REPO_URL into $dir..."
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$dir" || fail "Couldn't clone $REPO_URL into $dir."
  fi
  [ -f "$dir/$INSTALLER" ] || fail "$dir has no $INSTALLER."
  exec bash "$dir/$INSTALLER" "$@"
}

# ── Default hooks ───────────────────────────────────────────────────────────────────────────────
declare -F app_option        > /dev/null || app_option()        { OPTION_ARGS=0; }
declare -F app_bootstrap     > /dev/null || app_bootstrap()     { bootstrap_clone "$@"; }
declare -F app_requirements  > /dev/null || app_requirements()  { docker_requirements; }
declare -F app_existing      > /dev/null || app_existing()      { docker_existing; }
declare -F app_preflight     > /dev/null || app_preflight()     { :; }
declare -F app_questions     > /dev/null || app_questions()     { :; }
declare -F app_summary       > /dev/null || app_summary()       { :; }
declare -F app_env           > /dev/null || app_env()           { :; }
declare -F app_write         > /dev/null || app_write()         { write_env; }
declare -F app_ready         > /dev/null || app_ready()         { :; }
declare -F app_build         > /dev/null || app_build()         { build_images; }
declare -F app_start         > /dev/null || app_start()         { docker compose up -d --remove-orphans; }
declare -F app_health        > /dev/null || app_health()        { wait_for_containers && check_urls; }
declare -F app_logs          > /dev/null || app_logs()          { compose_logs; }
declare -F app_admin         > /dev/null || app_admin()         { info "Open $APP_URL and create the first account there."; }
declare -F app_finish        > /dev/null || app_finish()        { mark_env_installed; }
declare -F app_done          > /dev/null || app_done()          { :; }
declare -F app_cleanup       > /dev/null || app_cleanup()       { :; }

# ── Run ─────────────────────────────────────────────────────────────────────────────────────────
usage() {
  if [ -f "${BASH_SOURCE[0]:-}" ]; then
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
  else
    echo "Run $INSTALLER --help from a clone of the repository for the details."
  fi
}

on_error() { printf '\n  %s✗ Stopped at line %s: %s%s\n' "$R" "$1" "$2" "$N" >&2; }

on_exit() {
  local code=$?
  app_cleanup || true
  if [ "$code" -ne 0 ] && [ "$CHECK" = false ] && [ "${WROTE_SETTINGS:-false}" = true ]; then
    echo ""
    info "Fix what's above, then run $INSTALLER again: it carries on with the same settings."
  fi
  [ -n "${LOG:-}" ] && [ "$code" -ne 0 ] && info "Log: $LOG"
  return 0
}

# Shows the random admin password once, on the terminal only (never in the log).
show_password() {
  [ -n "$GENERATED_PASSWORD" ] || return 0
  if [ -n "${LOG:-}" ]; then
    exec 1>&3 2>&4
    wait "$LOG_PID" 2> /dev/null || sleep 1
  fi
  printf '\n  ┌──────────────────────────────────────────────────────────────\n'
  printf '  │ The admin password (random; shown only now, not in the log):\n'
  printf '  │   %s%s%s\n' "$B" "$GENERATED_PASSWORD" "$N"
  printf '  └──────────────────────────────────────────────────────────────\n\n'
}

main() {
  YES=false CHECK=false SETTINGS_ONLY=false
  APP_NAME="" INSTALLER="" UPGRADER="" UPGRADE_CMD="" REPO_URL="" BRANCH=main DEFAULT_DIR=""
  BACKUP_DIR=backups MIN_FREE_GB=3 MIN_MEMORY_GB=1 HEALTH_TIMEOUT=300 HEALTH_URLS="" APP_URL=""
  FIXED_PORTS="" PREFLIGHT_ENV="" SETTINGS_FILE=""
  RESUME=false GENERATED_PASSWORD="" PASSWORD_SOURCE="" ADMIN_LOGIN="" PASSWORD_NOTE="" WROTE_SETTINGS=false
  LOG="" LOG_PID=""
  app_settings

  local args=("$@")
  while [ $# -gt 0 ]; do
    case "$1" in
      -y | --yes) YES=true ;;
      --check) CHECK=true ;;
      --settings-only) SETTINGS_ONLY=true ;;
      -h | --help) usage; exit 0 ;;
      *)
        OPTION_ARGS=0
        app_option "$@"
        [ "$OPTION_ARGS" -gt 0 ] || fail "Unknown option $1 (see --help)."
        shift $((OPTION_ARGS - 1))
        ;;
    esac
    shift
  done

  PROJECT_DIR=""
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
  app_bootstrap "${args[@]}"
  [ -z "$PROJECT_DIR" ] || cd "$PROJECT_DIR" || fail "Can't open $PROJECT_DIR."
  UPGRADE_CMD=${UPGRADE_CMD:-cd $PROJECT_DIR && ./$UPGRADER}
  SETTINGS_FILE=${SETTINGS_FILE:-$PROJECT_DIR/.env}
  TTY=""
  if (exec < /dev/tty) 2> /dev/null; then TTY=/dev/tty; fi

  case "$BACKUP_DIR" in /*) ;; *) BACKUP_DIR="$PROJECT_DIR/$BACKUP_DIR" ;; esac
  STAMP=$(date +%Y%m%d-%H%M%S)
  exec 3>&1 4>&2
  if [ "$CHECK" = false ] && mkdir -p "$BACKUP_DIR" 2> /dev/null && [ -w "$BACKUP_DIR" ]; then
    LOG="$BACKUP_DIR/install-$STAMP.log"
    exec > >(tee -a "$LOG") 2>&1
    LOG_PID=$!
  fi
  trap on_exit EXIT
  trap 'on_error $LINENO "$BASH_COMMAND"' ERR

  printf '%s%s install%s  %s, %s\n' "$B" "$APP_NAME" "$N" "$(hostname)" "$(date '+%Y-%m-%d %H:%M')"

  STEPS=7
  step 1 "Pre-flight"
  app_requirements
  check_disk
  check_memory
  app_existing
  [ "$RESUME" = true ] || check_ports "$FIXED_PORTS"
  app_preflight

  step 2 "Settings"
  if [ "$RESUME" = true ]; then
    app_questions
    ok "Settings: the .env from the earlier run."
  else
    [ "$YES" = true ] || [ "$CHECK" = true ] || info "Press Enter to take the answer in [brackets]."
    app_questions
    echo ""
    app_summary
    echo ""
    if [ "$CHECK" = false ]; then
      confirm "Install $APP_NAME with these settings?" || fail "Stopped. Nothing has changed."
    fi
    app_env
    app_write
  fi
  if [ "$CHECK" = true ]; then
    ok "That's what an install would do (--check changes nothing)."
    return 0
  fi
  WROTE_SETTINGS=true
  app_ready
  if [ "$SETTINGS_ONLY" = true ]; then
    ok "Stopped after the settings (--settings-only). Change them if you like, then run $INSTALLER again."
    return 0
  fi

  step 3 "Build"
  app_build

  step 4 "Start"
  app_start

  step 5 "Health check"
  if ! app_health; then
    app_logs
    fail "$APP_NAME isn't healthy (see above)."
  fi

  step 6 "Admin account"
  app_admin

  step 7 "Done"
  app_finish
  ok "$APP_NAME is installed."
  echo ""
  [ -n "$APP_URL" ] && summary_line "Open" "$APP_URL"
  [ -n "$ADMIN_LOGIN" ] && summary_line "Sign in" "$ADMIN_LOGIN"
  case "$PASSWORD_SOURCE" in
    random) summary_line "Password" "random, shown below once${PASSWORD_NOTE:+ (also $PASSWORD_NOTE)}" ;;
    typed | given) summary_line "Password" "the one you gave${PASSWORD_NOTE:+ (also $PASSWORD_NOTE)}" ;;
    *) [ -z "$PASSWORD_NOTE" ] || summary_line "Password" "$PASSWORD_NOTE" ;;
  esac
  app_done
  summary_line "Settings" "$SETTINGS_FILE (holds the secrets: keep it private)"
  [ -n "$LOG" ] && summary_line "Log" "$LOG"
  summary_line "Upgrade" "$UPGRADE_CMD"
  show_password
}

main "$@"
