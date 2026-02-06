#!/bin/bash

# DAC-EQ Uninstallation Script
# Completely removes dac-eq and all files

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get installation directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$INSTALL_DIR")"
INSTALL_NAME="$(basename "$INSTALL_DIR")"

echo "======================================"
echo "  DAC-EQ Uninstallation"
echo "======================================"
echo ""
echo -e "${YELLOW}⚠ This will completely remove dac-eq${NC}"
echo ""
echo "Including:"
echo "  - All source code"
echo "  - Virtual environment (venv/)"
echo "  - MCP configuration (.mcp.json)"
echo "  - EQ profiles (eq/ folder)"
echo ""

read -p "Before continuing: Have you backed up your EQ profiles? (y/N): " backup_confirm

if [[ "$backup_confirm" != "y" ]] && [[ "$backup_confirm" != "Y" ]]; then
    echo ""
    echo "To backup your profiles, run:"
    echo "  cp -r eq/ ~/my-backup-location/"
    echo ""
    echo "Then run this script again."
    exit 0
fi

echo ""
read -p "Permanently delete dac-eq? This cannot be undone. (y/N): " final_confirm

if [[ "$final_confirm" != "y" ]] && [[ "$final_confirm" != "Y" ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo ""
echo "Removing dac-eq..."

# Change to parent directory first (so we can delete the directory we're in)
cd "$PARENT_DIR" || exit 1

# Remove the entire installation directory
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}✓${NC} dac-eq completely removed"
else
    echo "Installation directory not found"
fi

echo ""
echo "======================================"
echo -e "${GREEN}  Uninstall Complete${NC}"
echo "======================================"
echo ""
echo "dac-eq has been completely removed from:"
echo "  $INSTALL_DIR"
echo ""
