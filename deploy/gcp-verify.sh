#!/bin/bash

# GCP SSH Environment Verification Script
# Usage: ./deploy/gcp-verify.sh <GCP_VM_IP> [testnet]

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GCP_VM_IP=${1:-}
USE_TESTNET=${2:-false}
GCP_USER=${GCP_USER:-$USER}
GCP_PROJECT=${GCP_PROJECT:-}
GCP_ZONE=${GCP_ZONE:-us-central1-a}
SSH_KEY=${SSH_KEY:-~/.ssh/google_compute_engine}

# Check if IP is provided
if [ -z "$GCP_VM_IP" ]; then
    echo -e "${RED}Error: GCP VM IP address is required${NC}"
    echo "Usage: ./deploy/gcp-verify.sh <GCP_VM_IP> [testnet]"
    echo ""
    echo "Example:"
    echo "  ./deploy/gcp-verify.sh 34.123.456.789"
    echo "  ./deploy/gcp-verify.sh 34.123.456.789 testnet"
    exit 1
fi

echo -e "${BLUE}=== GCP SSH Environment Verification ===${NC}"
echo "VM IP: $GCP_VM_IP"
echo "Testnet Mode: $USE_TESTNET"
echo ""

# Test SSH connection
echo -e "${BLUE}Step 1: Testing SSH connection...${NC}"
if ssh -o ConnectTimeout=5 -i "$SSH_KEY" "$GCP_USER@$GCP_VM_IP" "echo '✅ SSH connection successful'" 2>/dev/null; then
    echo -e "${GREEN}✅ SSH connection successful${NC}"
else
    echo -e "${RED}❌ SSH connection failed${NC}"
    echo "Make sure:"
    echo "  1. GCP VM is running"
    echo "  2. SSH key is available at: $SSH_KEY"
    echo "  3. VM IP is correct: $GCP_VM_IP"
    echo "  4. Firewall allows SSH (port 22)"
    exit 1
fi

echo ""
echo -e "${BLUE}Step 2: Checking repository on VM...${NC}"

# Copy repo to VM if needed
ssh -i "$SSH_KEY" "$GCP_USER@$GCP_VM_IP" << 'EOF'
if [ ! -d "crypto-quant-bot" ]; then
    echo "Repository not found, cloning..."
    git clone https://github.com/QQjacktoggy/Crypto.git crypto-quant-bot
else
    echo "✅ Repository already exists"
fi
cd crypto-quant-bot
git fetch origin
git checkout claude/gcp-environment-verification-bot-mKWUL
EOF

echo ""
echo -e "${BLUE}Step 3: Setting up Python environment on VM...${NC}"

# Setup Python environment and run verification
TESTNET_FLAG=""
if [ "$USE_TESTNET" = "testnet" ]; then
    TESTNET_FLAG="--testnet"
fi

ssh -i "$SSH_KEY" "$GCP_USER@$GCP_VM_IP" << EOF
cd crypto-quant-bot

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate and install dependencies
source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo -e "\033[0;34m=== Running Environment Verification ===\"\033[0m"
python verify_env.py $TESTNET_FLAG

echo ""
echo -e "\033[0;32m=== Verification Complete ===\"\033[0m"
EOF

echo ""
echo -e "${GREEN}✅ All checks passed! Bot is ready to deploy.${NC}"
echo ""
echo "Next steps:"
echo "  1. Deploy using Docker: docker build -t quant-bot -f deploy/Dockerfile ."
echo "  2. Or run directly: python main.py --mode live"
