#!/bin/bash

# EQ Advisor Uninstallation Script
# Completely removes eq-advisor and all files

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
echo "  EQ Advisor Uninstallation"
echo "======================================"
echo ""
echo -e "${YELLOW}⚠ This will completely remove eq-advisor${NC}"
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
read -p "Permanently delete eq-advisor? This cannot be undone. (y/N): " final_confirm

if [[ "$final_confirm" != "y" ]] && [[ "$final_confirm" != "Y" ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo ""
echo "Removing eq-advisor..."

# Remove everything in the directory from a subshell (allows deletion of the directory itself)
(
  cd "$PARENT_DIR"
  rm -rf "$INSTALL_NAME" 2>/dev/null
)

echo -e "${GREEN}✓${NC} eq-advisor uninstalled"

echo ""
echo "======================================"
echo -e "${GREEN}  Uninstall Complete${NC}"
echo "======================================"
echo ""

# Move back to parent directory so user isn't left in a non-existent directory
cd "$PARENT_DIR" 2>/dev/null || cd ~
