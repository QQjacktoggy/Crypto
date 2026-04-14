import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import pandas as pd
import logging
import sys

# Suppress overly verbose logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kronos AI Predictor API")

# Global variables for model
model = None
tokenizer = None
predictor = None

class KLineData(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0

class PredictionRequest(BaseModel):
    symbol: str
    lookback_data: List[KLineData]
    pred_len: int = 1

@app.on_event("startup")
async def startup_event():
    global model, tokenizer, predictor
    try:
        logger.info("Attempting to load Kronos-mini model. This might take a while...")
        # Since this code runs in Colab, we expect the user to have installed the model dependencies
        # In a generic environment where they might not be installed, we gracefully fallback.
        try:
            from model import Kronos, KronosTokenizer, KronosPredictor
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Using device: {device}")

            tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-2k")
            model = Kronos.from_pretrained("NeoQuasar/Kronos-mini")

            predictor = KronosPredictor(model, tokenizer, max_context=2048, device=device)
            logger.info("Kronos model successfully loaded!")
        except ImportError as e:
            logger.error(f"Failed to import Kronos dependencies. Are you running this in the right Colab environment? Error: {e}")
            # We don't crash, we just let requests fail gracefully so the API stays up
    except Exception as e:
        logger.error(f"Initialization error: {e}")

@app.post("/predict")
async def predict(request: PredictionRequest):
    if predictor is None:
        raise HTTPException(status_code=503, detail="Model is not loaded. Ensure colab dependencies are installed.")

    try:
        # Convert request data to pandas DataFrame
        df = pd.DataFrame([dict(item) for item in request.lookback_data])
        df['timestamps'] = pd.to_datetime(df['timestamp'])

        # We need historical timestamps and future timestamps
        x_timestamp = df['timestamps']

        # Generate future dummy timestamps based on the last known interval (assuming 15m)
        last_time = x_timestamp.iloc[-1]
        freq = pd.Timedelta(minutes=15)
        y_timestamp = pd.Series([last_time + freq * (i+1) for i in range(request.pred_len)])

        # Keep only required columns
        x_df = df[['open', 'high', 'low', 'close', 'volume', 'amount']]

        logger.info(f"Received request for {request.symbol}. Lookback length: {len(x_df)}")

        # Predict
        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=request.pred_len,
            T=1.0,          # Temperature
            top_p=0.9,      # Nucleus sampling
            sample_count=1
        )

        # We assume we only care about the final predicted close price for the next bar
        predicted_close = float(pred_df['close'].iloc[-1])
        logger.info(f"Prediction for {request.symbol}: {predicted_close}")

        return {
            "symbol": request.symbol,
            "predicted_close": predicted_close,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "alive", "model_loaded": predictor is not None}
