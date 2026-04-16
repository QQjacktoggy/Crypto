#!/bin/bash

# GCP Cloud Init Script for Crypto Quant Bot
# This script runs automatically when the GCP VM starts
# Add this as a startup script when creating the VM instance

set -e

echo "=== Crypto Quant Bot GCP Setup Started ===" >> /var/log/startup-script.log

# Update system
apt-get update
apt-get upgrade -y

# Install required packages
apt-get install -y \
    git \
    python3-pip \
    python3-venv \
    docker.io \
    docker-compose

# Add current user to docker group
usermod -aG docker $(whoami)

# Clone repository
cd /home/$(whoami)
if [ ! -d "crypto-quant-bot" ]; then
    git clone https://github.com/QQjacktoggy/Crypto.git crypto-quant-bot
    cd crypto-quant-bot
    git checkout claude/gcp-environment-verification-bot-mKWUL
else
    cd crypto-quant-bot
    git pull origin claude/gcp-environment-verification-bot-mKWUL
fi

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create .env.example if doesn't exist
if [ ! -f ".env.example" ]; then
    cat > .env.example << 'ENVFILE'
API_KEY=your_binance_api_key
API_SECRET=your_binance_api_secret
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
ENVFILE
fi

# Log completion
echo "=== Crypto Quant Bot GCP Setup Completed ===" >> /var/log/startup-script.log
echo "Next step: Create .env file with your Binance credentials" >> /var/log/startup-script.log
echo "Then run: python verify_env.py to test the connection" >> /var/log/startup-script.log
