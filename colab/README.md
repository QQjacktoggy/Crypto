# Kronos AI - Google Colab Deployment Guide

This guide explains how to run the `Kronos-mini` model on a free Google Colab instance, exposing it as a REST API using `ngrok` so your GCP trading bot can securely query it for AI-augmented predictions.

## Step 1: Open Google Colab
1. Go to [Google Colab](https://colab.research.google.com/) and create a new notebook.
2. Go to **Runtime > Change runtime type**, and select **T4 GPU** (or CPU if GPU is unavailable, though GPU is faster).

## Step 2: Install Dependencies in Colab
Create a cell and run the following command to install the required libraries:
```python
!git clone https://github.com/shiyu-coder/Kronos.git
%cd Kronos
!pip install -r requirements.txt
!pip install fastapi uvicorn pyngrok nest-asyncio
```

## Step 3: Start the API Server with Ngrok
Create another cell, paste the following code, and replace `"YOUR_NGROK_AUTHTOKEN"` with your actual token from [ngrok.com](https://dashboard.ngrok.com/get-started/your-authtoken).

```python
import nest_asyncio
from pyngrok import ngrok
import uvicorn
import os

# 1. Set Ngrok Token
os.environ["NGROK_AUTHTOKEN"] = "YOUR_NGROK_AUTHTOKEN"
ngrok.set_auth_token(os.environ["NGROK_AUTHTOKEN"])

# 2. Upload our API script
# (You need to upload the `colab/kronos_api.py` file to the Colab environment first)
# For ease of use, we assume you saved it as `kronos_api.py` in the current directory.

# 3. Create a public URL
public_url = ngrok.connect(8000).public_url
print(f"🚀 YOUR KRONOS AI API URL: {public_url}")
print(f"Copy this URL and paste it into your GCP bot's .env file as AI_API_URL")

# 4. Start the server
nest_asyncio.apply()
uvicorn.run("kronos_api:app", host="0.0.0.0", port=8000)
```

## Step 4: Configure your GCP Trading Bot
Once the Colab cell is running, it will output a URL like `https://xxxx-xxx-xxx.ngrok-free.app`.

In your GCP Trading Bot, edit the `.env` file:
```env
AI_API_URL=https://xxxx-xxx-xxx.ngrok-free.app
```
Restart your trading bot, and it will automatically start querying the Colab AI API!

> **⚠️ Important Note:** Google Colab instances shut down after a period of inactivity or a maximum of 12 hours. You will need to manually re-run the notebook and update the `AI_API_URL` in your GCP bot daily. If the GCP bot fails to reach the API, it safely falls back to standard traditional indicators.
