#!/bin/bash
set -euo pipefail

# ─────────────────────────────────────────────
# Ghostwire Proxy - Purge Old Backups
#
# Removes backup files older than a specified number of days.
# Keeps the most recent N backups regardless of age as a safety net.
#
# Usage:
#   ./scripts/purge-backups.sh              # purge backups older than 30 days (keep last 3)
#   ./scripts/purge-backups.sh --days 14    # purge backups older than 14 days
#   ./scripts/purge-backups.sh --keep 5     # always keep at least 5 backups
#   ./scripts/purge-backups.sh --dry-run    # show what would be deleted
# ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/data/backups"

# Defaults
MAX_AGE_DAYS=30
MIN_KEEP=3
DRY_RUN=false
RUN=false

show_help() {
    echo "Ghostwire Proxy - Purge Old Backups"
    echo ""
    echo "Removes old pre-upgrade and scheduled backup files from data/backups/."
    echo "Always keeps the most recent N backups as a safety net, regardless of age."
    echo ""
    echo "Usage:"
    echo "  $0 --run                  Purge backups older than 30 days (keep last 3)"
    echo "  $0 --run --days 14        Purge backups older than 14 days"
    echo "  $0 --run --keep 5         Always keep at least 5 most recent backups"
    echo "  $0 --dry-run              Preview what would be deleted (safe, no changes)"
    echo ""
    echo "Options:"
    echo "  --run           Actually delete files (required unless --dry-run)"
    echo "  --days N        Delete backups older than N days (default: 30)"
    echo "  --keep N        Always keep at least N most recent backups (default: 3)"
    echo "  --dry-run       Show what would be deleted without removing anything"
    echo "  --help, -h      Show this help message"
    echo ""
    echo "Examples:"
    echo "  # See what would be cleaned up (safe):"
    echo "  ./scripts/purge-backups.sh --dry-run"
    echo ""
    echo "  # Delete pre-upgrade backups older than 2 weeks, keep last 5:"
    echo "  ./scripts/purge-backups.sh --run --days 14 --keep 5"
    echo ""
    echo "  # Aggressive cleanup — keep only the 2 newest backups:"
    echo "  ./scripts/purge-backups.sh --run --days 7 --keep 2"
    echo ""
    echo "Note: This script runs automatically after a successful upgrade"
    echo "      (with --days 30 --keep 5)."
}

# No arguments → show help
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --days|-d)   MAX_AGE_DAYS="$2"; shift ;;
        --keep|-k)   MIN_KEEP="$2"; shift ;;
        --dry-run)   DRY_RUN=true; RUN=true ;;
        --run)       RUN=true ;;
        --help|-h)   show_help; exit 0 ;;
        *) echo "Unknown option: $1"; echo "Run with --help for usage."; exit 1 ;;
    esac
    shift
done

if [ "$RUN" = false ]; then
    show_help
    exit 0
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[purge]${NC} $*"; }
ok()   { echo -e "${GREEN}[  ok ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ warn]${NC} $*"; }

if [ ! -d "$BACKUP_DIR" ]; then
    warn "Backup directory does not exist: $BACKUP_DIR"
    exit 0
fi

log "Scanning backups in: $BACKUP_DIR"
log "Policy: delete files older than ${MAX_AGE_DAYS} days, always keep newest ${MIN_KEEP}"
[ "$DRY_RUN" = true ] && log "(DRY RUN — no files will be deleted)"
echo ""

# Find all backup files (sql dumps and tar.gz archives), sorted newest first
BACKUP_FILES=()
while IFS= read -r -d '' file; do
    BACKUP_FILES+=("$file")
done < <(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name "*.sql" -o -name "*.sql.gz" -o -name "*.tar.gz" -o -name "*.dump" \) -printf '%T@ %p\0' | sort -rzn | cut -z -d' ' -f2-)

TOTAL=${#BACKUP_FILES[@]}
log "Found $TOTAL backup file(s)"

if [ "$TOTAL" -le "$MIN_KEEP" ]; then
    ok "Only $TOTAL backup(s) found — nothing to purge (minimum keep: $MIN_KEEP)"
    exit 0
fi

DELETED=0
FREED=0

for i in "${!BACKUP_FILES[@]}"; do
    file="${BACKUP_FILES[$i]}"
    position=$((i + 1))

    # Always keep the newest MIN_KEEP files
    if [ "$position" -le "$MIN_KEEP" ]; then
        continue
    fi

    # Check age
    file_age_days=$(( ($(date +%s) - $(stat -c %Y "$file")) / 86400 ))

    if [ "$file_age_days" -ge "$MAX_AGE_DAYS" ]; then
        file_size=$(du -h "$file" | cut -f1)
        file_size_bytes=$(stat -c %s "$file")
        basename=$(basename "$file")

        if [ "$DRY_RUN" = true ]; then
            echo -e "  ${YELLOW}[would delete]${NC} $basename (${file_size}, ${file_age_days} days old)"
        else
            rm -f "$file"
            echo -e "  ${RED}[deleted]${NC} $basename (${file_size}, ${file_age_days} days old)"
        fi

        DELETED=$((DELETED + 1))
        FREED=$((FREED + file_size_bytes))
    fi
done

echo ""
if [ "$DELETED" -eq 0 ]; then
    ok "No backups eligible for purge"
else
    FREED_HUMAN=$(numfmt --to=iec "$FREED" 2>/dev/null || echo "${FREED} bytes")
    if [ "$DRY_RUN" = true ]; then
        log "Would delete $DELETED file(s), freeing ~$FREED_HUMAN"
    else
        ok "Purged $DELETED file(s), freed $FREED_HUMAN"
    fi
fi
