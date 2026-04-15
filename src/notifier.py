import requests
import logging
from src.config import config

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            logger.warning("Telegram Notifier disabled. Missing TOKEN or CHAT_ID.")

    def send_message(self, message: str):
        if not self.enabled:
            logger.info(f"[Telegram Simulator] {message}")
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def notify_trade(self, symbol: str, tier: int, amount: float, price: float):
        msg = (
            f"🚀 <b>Trade Executed</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Tier:</b> {tier}\n"
            f"<b>Amount (Base):</b> {amount:.6f}\n"
            f"<b>Price:</b> {price:.4f} USDT"
        )
        self.send_message(msg)

    def notify_tp(self, symbol: str, pnl: float):
        msg = (
            f"✅ <b>Take Profit Triggered</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Net Profit:</b> {pnl:.4f} USDT"
        )
        self.send_message(msg)

    def notify_sl(self, symbol: str, pnl: float):
        msg = (
            f"🛑 <b>Stop Loss Triggered</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Loss:</b> {pnl:.4f} USDT\n"
            f"<i>Entering cooldown phase.</i>"
        )
        self.send_message(msg)

    def notify_error(self, error_msg: str):
        msg = (
            f"⚠️ <b>System Alert</b>\n"
            f"<code>{error_msg}</code>"
        )
        self.send_message(msg)
