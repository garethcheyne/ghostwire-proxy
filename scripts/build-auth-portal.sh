#!/bin/bash
# Build auth portal themes and copy to proxy directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Building auth portal themes..."

# Build default theme
echo "Building default theme..."
cd "$PROJECT_ROOT/frontend-authwall/default"
npm ci
npm run build

# Copy to proxy directory
echo "Copying to proxy/auth-portal/default..."
rm -rf "$PROJECT_ROOT/proxy/auth-portal/default"
cp -r "$PROJECT_ROOT/frontend-authwall/default/dist" "$PROJECT_ROOT/proxy/auth-portal/default"

# Build any additional themes (if they exist)
for theme_dir in "$PROJECT_ROOT/frontend-authwall"/*/; do
    theme_name=$(basename "$theme_dir")
    if [ "$theme_name" != "default" ] && [ "$theme_name" != "_template" ] && [ -f "$theme_dir/package.json" ]; then
        echo "Building theme: $theme_name..."
        cd "$theme_dir"
        npm ci
        npm run build
        rm -rf "$PROJECT_ROOT/proxy/auth-portal/$theme_name"
        cp -r "$theme_dir/dist" "$PROJECT_ROOT/proxy/auth-portal/$theme_name"
    fi
done

echo "Auth portal build complete!"
