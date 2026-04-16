# GCP SSH Setup & Remote Verification Guide

This guide explains how to set up SSH access to your GCP VM and run environment verification remotely.

## Prerequisites

- GCP Account with an e2-micro VM running Ubuntu 22.04 LTS
- `gcloud` CLI installed on your local machine
- Appropriate IAM permissions to manage Compute Engine instances

## 1. Install gcloud CLI

### On macOS:
```bash
brew install google-cloud-sdk
gcloud init
```

### On Linux:
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init
```

### On Windows:
Download and run the [Google Cloud SDK installer](https://cloud.google.com/sdk/docs/install-sdk)

## 2. Set up SSH Keys

### Option A: Using gcloud (Recommended)

```bash
# Set your GCP project
gcloud config set project YOUR_PROJECT_ID

# List your GCP instances
gcloud compute instances list

# Set the zone/region
gcloud config set compute/zone us-central1-a

# Generate and configure SSH key
gcloud compute config-ssh
```

This will automatically:
- Generate SSH keys in `~/.ssh/google_compute_engine`
- Add your public key to the VM metadata
- Configure SSH config file

### Option B: Manual SSH Setup

```bash
# Generate SSH key pair
ssh-keygen -t rsa -b 4096 -f ~/.ssh/gcp_key -N ""

# Get your VM's external IP
GCP_IP=$(gcloud compute instances describe YOUR_VM_NAME \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

# Add your public key to the VM's SSH metadata
gcloud compute instances add-metadata YOUR_VM_NAME \
  --metadata-from-file ssh-keys=- << EOF
$USER:$(cat ~/.ssh/gcp_key.pub)
EOF
```

## 3. Test SSH Connection

```bash
# Using gcloud (easiest)
gcloud compute ssh YOUR_VM_NAME

# Or using SSH directly
ssh -i ~/.ssh/google_compute_engine YOUR_USERNAME@YOUR_GCP_IP
```

## 4. Run Remote Environment Verification

### Using the provided script:

```bash
# From your local machine, in the repo root
chmod +x deploy/gcp-verify.sh

# Run verification on your GCP VM
./deploy/gcp-verify.sh YOUR_GCP_IP

# Or with testnet mode
./deploy/gcp-verify.sh YOUR_GCP_IP testnet
```

### Manual SSH + Verify:

```bash
# SSH into VM
gcloud compute ssh YOUR_VM_NAME

# Once on the VM, clone or pull the latest code
git clone https://github.com/QQjacktoggy/Crypto.git crypto-quant-bot
cd crypto-quant-bot
git checkout claude/gcp-environment-verification-bot-mKWUL

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file with your credentials
nano .env

# Run verification
python verify_env.py

# Or test with testnet
python verify_env.py --testnet
```

## 5. Automate Setup with Cloud Init

When creating a new GCP VM, you can use the cloud-init script to automate initial setup:

```bash
# Create VM with cloud-init script
gcloud compute instances create crypto-bot \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --metadata-from-file startup-script=deploy/gcp-cloud-init.sh
```

Or in the GCP Console:
1. Go to Compute Engine → VM instances → Create Instance
2. Expand "Advanced options" → Management
3. Paste the contents of `deploy/gcp-cloud-init.sh` in the "Startup script" field
4. Create the instance

After VM boots, SSH in and set up `.env`:
```bash
cd crypto-quant-bot
nano .env  # Add your Binance API credentials
python verify_env.py
```

## 6. Useful SSH Commands

```bash
# List all GCP instances
gcloud compute instances list

# SSH into VM
gcloud compute ssh INSTANCE_NAME

# Copy file from local to VM
gcloud compute scp ./local-file INSTANCE_NAME:/remote/path

# Copy file from VM to local
gcloud compute scp INSTANCE_NAME:/remote/file ./local-file

# View VM serial port output (useful for debugging)
gcloud compute instances get-serial-port-output INSTANCE_NAME

# Stop VM (saves costs)
gcloud compute instances stop INSTANCE_NAME

# Start VM
gcloud compute instances start INSTANCE_NAME

# Delete VM
gcloud compute instances delete INSTANCE_NAME
```

## 7. Environment Variables for Scripts

You can set these environment variables to customize the behavior:

```bash
export GCP_USER=your_username
export GCP_PROJECT=your-gcp-project
export GCP_ZONE=us-central1-a
export SSH_KEY=~/.ssh/google_compute_engine

./deploy/gcp-verify.sh YOUR_GCP_IP
```

## 8. Troubleshooting

### SSH Connection Timeout
- Make sure VM is running: `gcloud compute instances list`
- Check firewall rules allow SSH (port 22)
- Verify external IP is assigned: `gcloud compute instances describe INSTANCE_NAME`

### Permission Denied
- Check SSH key permissions: `chmod 600 ~/.ssh/google_compute_engine`
- Verify user exists on VM: `gcloud compute ssh INSTANCE_NAME -- whoami`

### Verification Script Fails
- Check `.env` file exists on VM
- Verify Binance API credentials are correct
- Check API key has Futures trading enabled
- Try testnet first: `python verify_env.py --testnet`

## 9. Next Steps After Verification

Once `verify_env.py` passes:

```bash
# Deploy using Docker
docker build -t quant-bot -f deploy/Dockerfile .
docker run -d --name trading-bot --env-file .env --restart unless-stopped quant-bot

# Or run as systemd service
sudo nano /etc/systemd/system/quantbot.service
# (Copy content from deploy/README.md Step 5)

sudo systemctl daemon-reload
sudo systemctl enable quantbot
sudo systemctl start quantbot
sudo systemctl status quantbot
```

## Security Best Practices

1. **Firewall**: Only allow SSH from your IP
   ```bash
   gcloud compute firewall-rules create allow-ssh-from-home \
     --allow=tcp:22 \
     --source-ranges=YOUR_PUBLIC_IP/32
   ```

2. **Rotate API Keys**: Regularly update Binance API keys in `.env`

3. **Secure .env file**: Never commit `.env` to git
   ```bash
   echo ".env" >> .gitignore
   ```

4. **Monitor Logs**: Check bot logs regularly
   ```bash
   docker logs -f trading-bot
   # or
   journalctl -u quantbot -f
   ```

5. **Resource Limits**: Monitor VM CPU/memory usage in GCP Console
