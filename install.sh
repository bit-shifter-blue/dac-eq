#!/bin/bash

# DAC-EQ Installation Script
# Automated setup for CLI tool and MCP servers

set -e  # Exit on any error

echo "======================================"
echo "  EQ Advisor Installation"
echo "======================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get installation directory (absolute path)
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installing to: $INSTALL_DIR"
echo ""

# ========================================
# 1. Check Prerequisites
# ========================================

echo "Checking prerequisites..."

# Check macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}Error: eq-advisor requires macOS for USB HID device access.${NC}"
    echo "This tool uses hidapi which only supports macOS."
    exit 1
fi

# Check Python version
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [[ "$PYTHON_MAJOR" -ge 3 ]] && [[ "$PYTHON_MINOR" -ge 11 ]]; then
        PYTHON_CMD="python3"
    else
        echo -e "${RED}Error: Python 3.11 or higher required (found: $PYTHON_VERSION)${NC}"
        echo ""
        echo "To install Python 3.11:"
        echo "  brew install python@3.11"
        echo ""
        echo "Then run this script again."
        exit 1
    fi
else
    echo -e "${RED}Error: Python 3 not found${NC}"
    echo ""
    echo "To install Python 3.11:"
    echo "  brew install python@3.11"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo -e "${GREEN}✓${NC} macOS detected"
echo -e "${GREEN}✓${NC} Python $($PYTHON_CMD --version 2>&1) found"

# Check Claude Code (optional)
if ! command -v claude &> /dev/null; then
    echo -e "${YELLOW}Warning: Claude Code CLI not found.${NC}"
    echo "This package includes MCP servers for Claude Code."
    echo ""
    echo "To install Claude Code: npm install -g @anthropic-ai/claude-code"
    echo ""
    echo "(Continuing installation anyway...)"
    echo ""
else
    echo -e "${GREEN}✓${NC} Claude Code CLI found"
fi

echo ""

# ========================================
# 2. Create Virtual Environment
# ========================================

echo "Creating unified virtual environment..."

# Remove old venv if exists
if [ -d "$INSTALL_DIR/venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf "$INSTALL_DIR/venv"
fi

# Create new venv
$PYTHON_CMD -m venv "$INSTALL_DIR/venv"

# Activate venv
source "$INSTALL_DIR/venv/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null

echo -e "${GREEN}✓${NC} Virtual environment created"
echo ""

# ========================================
# 3. Install Dependencies
# ========================================

echo "Installing dependencies (this may take a few minutes)..."
echo "Installing: streamlit, anthropic, hidapi, mcp, autoeq, httpx"
echo ""

# Install all dependencies from unified requirements file
pip install -r "$INSTALL_DIR/requirements.txt"

echo ""
echo -e "${GREEN}✓${NC} Dependencies installed"
echo ""

# ========================================
# 4. Generate .mcp.json
# ========================================

echo "Generating MCP server configuration..."

# Create .mcp.json with absolute paths
# Note: We use absolute paths because Claude Code's MCP protocol requires them.
# Relative paths won't work because Claude Code doesn't know what directory to resolve them from.

cat > "$INSTALL_DIR/.mcp.json" << EOF
{
  "mcpServers": {
    "peq-devices": {
      "type": "stdio",
      "command": "$INSTALL_DIR/venv/bin/python",
      "args": ["$INSTALL_DIR/tools/peq_devices/server.py"],
      "env": {}
    },
    "squiglink": {
      "type": "stdio",
      "command": "$INSTALL_DIR/venv/bin/python",
      "args": ["$INSTALL_DIR/tools/squiglink/server.py"],
      "env": {}
    },
    "autoeq": {
      "type": "stdio",
      "command": "$INSTALL_DIR/venv/bin/python",
      "args": ["$INSTALL_DIR/tools/autoeq/server.py"],
      "env": {}
    }
  }
}
EOF

echo -e "${GREEN}✓${NC} MCP configuration generated at $INSTALL_DIR/.mcp.json"
echo ""

# ========================================
# 5. Test Installation
# ========================================

echo "Testing installation..."

# Test CLI tool
if $PYTHON_CMD "$INSTALL_DIR/cli.py" --list &> /dev/null; then
    echo -e "${GREEN}✓${NC} CLI tool working"
else
    echo -e "${YELLOW}⚠${NC} CLI tool test completed (no devices detected or error occurred)"
    echo "  This is normal if no DSP device is connected"
fi

echo ""

# ========================================
# 6. Display Success Message
# ========================================

echo "======================================"
echo -e "${GREEN}  Installation Complete!${NC}"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "1. To use the CLI tool:"
echo "   source venv/bin/activate"
echo "   python cli.py --list"
echo ""
echo "2. To use the Streamlit app:"
echo "   source venv/bin/activate"
echo "   streamlit run streamlit_app.py"
echo ""
echo "3. To use with Claude Code:"
echo "   cd $INSTALL_DIR"
echo "   claude"
echo ""
echo "   Claude Code will auto-detect the project-scoped MCP servers."
echo "   You'll be prompted to approve them on first use."
echo ""
echo "   Try: 'Search for Blessing 3 IEM measurements'"
echo "   Or: '/eq-advisor' for guided EQ workflow"
echo ""
echo "4. MCP servers configured:"
echo "   - peq-devices: PEQ device control"
echo "   - squiglink: IEM frequency response data"
echo "   - autoeq: EQ optimization"
echo ""
echo "5. To uninstall:"
echo "   ./uninstall.sh"
echo ""
echo "For more information, see README.md"
echo ""
