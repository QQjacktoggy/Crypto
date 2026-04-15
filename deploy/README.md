# GCP Deployment Guide (e2-micro)

This guide provides instructions on how to deploy the Crypto Quant Bot to a Google Cloud Platform (GCP) Compute Engine `e2-micro` instance (Always Free Tier).

## Prerequisites
1. A GCP Account with Billing Enabled.
2. Create an `e2-micro` VM instance in an eligible region (e.g., `us-central1`, `us-east1`, `us-west1`).
3. OS: Ubuntu 22.04 LTS (recommended).

## Setup Instructions

### 1. SSH into your VM and install Docker
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io docker-compose -y
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```
*(You may need to log out and log back in for the docker group to take effect.)*

### 2. Clone the Repository
```bash
git clone <your-repo-url> crypto-quant-bot
cd crypto-quant-bot
```

### 3. Setup Configuration
Create a `.env` file in the root directory:
```bash
nano .env
```
Paste your credentials:
```env
API_KEY=your_binance_api_key
API_SECRET=your_binance_api_secret
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

### 4. Verify Environment (Optional but Recommended)
Before running the bot, you can verify that your API credentials and network connection are working correctly.

```bash
# Verify connection to Binance Mainnet
python verify_env.py

# Or verify connection to Binance Testnet
python verify_env.py --testnet
```

### 5. Build and Run using Docker Compose
Create a `docker-compose.yml` file in the root if you prefer, or build directly:

#### Option A: Direct Docker Run
```bash
docker build -t quant-bot -f deploy/Dockerfile .
docker run -d --name trading-bot --env-file .env --restart unless-stopped quant-bot
```

#### Option B: Systemd Service (Running Python without Docker)
If you want to run the python script directly as a background service:
1. Setup Python environment:
```bash
sudo apt install python3-pip python3-venv -y
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
2. Create a systemd service file:
```bash
sudo nano /etc/systemd/system/quantbot.service
```
Paste the following (adjust `/home/username/crypto-quant-bot` to your path):
```ini
[Unit]
Description=Crypto Quant Bot
After=network.target

[Service]
User=your_ubuntu_user
WorkingDirectory=/home/your_ubuntu_user/crypto-quant-bot
ExecStart=/home/your_ubuntu_user/crypto-quant-bot/venv/bin/python main.py --mode live
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
3. Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable quantbot
sudo systemctl start quantbot
sudo systemctl status quantbot
```

## Logs
To view docker logs:
```bash
docker logs -f trading-bot
```

To view systemd logs:
```bash
journalctl -u quantbot -f
```
