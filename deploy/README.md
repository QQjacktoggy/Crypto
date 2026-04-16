# GCP Deployment Guide

This guide provides instructions on how to deploy the Crypto Quant Bot to a GCP VM instance.

## Important: GCP Region Selection

> **Binance blocks IP addresses from US-based GCP regions** (`us-central1`, `us-east1`, `us-west1`).
> You must use an Asia region VM (note: not free tier).

| Region | GCP Zone | Binance Access |
|--------|----------|---------------|
| Taiwan | `asia-east1-b` | ✅ |
| Singapore | `asia-southeast1-b` | ✅ |
| Tokyo | `asia-northeast1-b` | ✅ |
| US (free tier) | `us-central1-a` | ❌ Blocked |

**Free alternative**: Oracle Cloud always-free tier supports Asia regions (Tokyo/Singapore).

## Prerequisites

1. GCP VM running Ubuntu 22.04 LTS in an Asia region
2. Binance account with:
   - API Key with **Futures trading enabled**
   - **USDT in USD-M Futures wallet** (minimum 150 USDT)
3. Telegram Bot Token and Chat ID (see [Telegram Setup](#telegram-setup))

---

## Setup Instructions

### Step 1: SSH into VM

```bash
# Using gcloud CLI
gcloud compute ssh YOUR_VM_NAME --zone=asia-east1-b

# Or using SSH directly
ssh -i ~/.ssh/google_compute_engine YOUR_USERNAME@YOUR_VM_IP
```

### Step 2: Add SWAP (Required for 1GB RAM VMs)

Docker build requires more than 1GB RAM. Add SWAP before building:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Persist after reboot
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Step 3: Install Docker

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io -y
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

**Log out and SSH back in** for docker group to take effect.

### Step 4: Clone Repository

```bash
git clone https://github.com/QQjacktoggy/Crypto.git crypto-quant-bot
cd crypto-quant-bot
```

### Step 5: Create .env Configuration

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

> **Important**: Always edit `.env` inside the `crypto-quant-bot/` directory.

### Step 6: Build Docker Image

```bash
docker build -t quant-bot -f deploy/Dockerfile .
```

> Uses Python 3.12 (required for `pandas-ta`). Build takes 3-5 minutes.

### Step 7: Verify Environment

Run the verification script via Docker before going live:

```bash
docker run --rm --env-file .env quant-bot python verify_env.py
```

A successful run shows:
```
✅ API Key and Secret found in environment variables.
✅ Successfully loaded 4310 markets.
✅ Successfully authenticated! Current USDT free balance: 150.0
--- Environment Verification Completed Successfully ---
```

### Step 8: Start the Bot

```bash
docker run -d --name trading-bot --env-file .env --restart unless-stopped quant-bot
```

### Step 9: Check Logs

```bash
docker logs -f trading-bot
```

---

## Telegram Setup

### 1. Create a Bot via BotFather

1. Open Telegram, search **`@BotFather`**
2. Send `/newbot` and follow instructions
3. Copy the Token (format: `1234567890:AAFxxxxx...`)

### 2. Get Your Chat ID

After creating the bot, send it any message (e.g. `hi`), then open:
```
https://api.telegram.org/botYOUR_TOKEN/getUpdates
```

Find your Chat ID in the response:
```json
"chat": { "id": 1234567890 }
```

### 3. Verify Token is Valid

```
https://api.telegram.org/botYOUR_TOKEN/getMe
```

Should return your bot's name and info.

---

## Binance Futures Account Setup

The bot trades **USD-M Futures** using USDT margin.

### Transfer Funds to Futures Wallet

1. Log in to Binance
2. Go to **Wallet** → **Transfer**
3. From: `Spot Account` → To: `USD-M Futures`
4. Currency: `USDT`, Amount: minimum `150`

> The bot requires at least **150 USDT** in the Futures wallet to start trading.

---

## Updating Configuration

If you change `.env`, you must recreate the container (restart alone won't apply new values):

```bash
docker stop trading-bot
docker rm trading-bot
docker run -d --name trading-bot --env-file .env --restart unless-stopped quant-bot
```

---

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| `Service unavailable from restricted location` | Binance blocks US GCP IPs | Switch to Asia region VM |
| `pandas-ta no matching distribution` | Python < 3.12 | Use Docker (Python 3.12 built-in) |
| Telegram `400 Bad Request` | Wrong Chat ID or editing wrong `.env` | Get Chat ID via `getUpdates`, edit `.env` in `crypto-quant-bot/` dir |
| Telegram `404 Not Found` | Invalid Bot Token | Recreate bot via `@BotFather` |
| `USDT free balance: 0.0` | No funds in Futures wallet | Transfer USDT to USD-M Futures account |
| OOM during Docker build | 1GB RAM too small | Add 2GB SWAP (Step 2) |

---

## Useful Commands

```bash
# View live logs
docker logs -f trading-bot

# Stop bot
docker stop trading-bot

# Restart bot (does NOT reload .env)
docker restart trading-bot

# Full restart with new .env
docker stop trading-bot && docker rm trading-bot
docker run -d --name trading-bot --env-file .env --restart unless-stopped quant-bot

# Check container status
docker ps

# Rebuild image after code changes
docker build -t quant-bot -f deploy/Dockerfile .
```
