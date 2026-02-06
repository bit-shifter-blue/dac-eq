#!/bin/bash

# DAC-EQ Uninstallation Script
# Removes virtual environment and MCP configuration

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get installation directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================"
echo "  DAC-EQ Uninstallation"
echo "======================================"
echo ""
echo "This will remove:"
echo "  - Virtual environment (venv/)"
echo "  - MCP configuration (.mcp.json)"
echo "  - EQ profiles in eq/ folder"
echo ""
echo -e "${YELLOW}⚠ Important: Your EQ profiles will be deleted!${NC}"
echo ""
echo "If you want to keep your EQ profiles, cancel this script and manually"
echo "copy the eq/ folder to a backup location before uninstalling:"
echo "  cp -r eq/ ~/my-backup-location/"
echo ""

read -p "Do you want to continue with uninstall? (y/N): " confirm

if [[ "$confirm" != "y" ]] && [[ "$confirm" != "Y" ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo ""
echo "Uninstalling..."

# Remove virtual environment
if [ -d "$INSTALL_DIR/venv" ]; then
    rm -rf "$INSTALL_DIR/venv"
    echo -e "${GREEN}✓${NC} Removed virtual environment"
else
    echo "Virtual environment not found (already removed)"
fi

# Remove .mcp.json
if [ -f "$INSTALL_DIR/.mcp.json" ]; then
    rm -f "$INSTALL_DIR/.mcp.json"
    echo -e "${GREEN}✓${NC} Removed MCP configuration"
else
    echo "MCP configuration not found (already removed)"
fi

# Remove EQ profiles
if [ -d "$INSTALL_DIR/eq" ]; then
    rm -rf "$INSTALL_DIR/eq"
    echo -e "${GREEN}✓${NC} Removed EQ profiles"
else
    echo "EQ profiles not found (already removed)"
fi

echo ""
echo "======================================"
echo -e "${GREEN}  Uninstall Complete${NC}"
echo "======================================"
echo ""
echo "To fully remove dac-eq, delete this directory:"
echo "  rm -rf $INSTALL_DIR"
echo ""
echo "To reinstall, run:"
echo "  ./install.sh"
echo ""
