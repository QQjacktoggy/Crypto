"""
optimize_phase10_multiyear.py - Phase 10 optimizer

Phase 10 checks whether the current best control profile and selected phase-9
advanced-trend candidates remain competitive on 2-year and 3-year windows.
"""

import logging
import os
import sys
from datetime import datetime

logging.getLogger().setLevel(logging.CRITICAL)

from src.engine_backtest import BacktestEngine
from src.config import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


SCENARIOS = [
    {
        'label': 'Control-2Y',
        'days': 730,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
            'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
            'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
            'ENABLE_DONCHIAN_BREAKOUT': False, 'ENABLE_ADVANCED_TREND_FILTER': False,
        },
    },
    {
        'label': 'Control-3Y',
        'days': 1095,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
            'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
            'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
            'ENABLE_DONCHIAN_BREAKOUT': False, 'ENABLE_ADVANCED_TREND_FILTER': False,
        },
    },
    {
        'label': 'AdvA-2Y',
        'days': 730,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
            'ENABLE_DONCHIAN_BREAKOUT': True, 'DONCHIAN_LENGTH': 24, 'DONCHIAN_BREAKOUT_BUFFER_PCT': 0.0015,
            'DONCHIAN_VOLUME_MULT': 1.05, 'DONCHIAN_LONG_RSI_MIN': 52, 'DONCHIAN_LONG_RSI_MAX': 78,
            'DONCHIAN_SHORT_RSI_MIN': 20, 'DONCHIAN_SHORT_RSI_MAX': 48,
            'ENABLE_1H_TREND_FILTER': True, 'HOURLY_EMA_FAST': 10, 'HOURLY_EMA_SLOW': 30,
            'ENABLE_TREND_PYRAMIDING': True, 'TREND_PYRAMID_MAX_ADDS': 2, 'TREND_PYRAMID_TRIGGER_ROI': 0.05,
            'TREND_PYRAMID_MIN_PULLBACK': 0.008, 'ENABLE_TREND_EXIT': True, 'TREND_EXIT_ON_HOURLY_FLIP': True,
            'TREND_EXIT_USE_DONCHIAN_MID': True,
            'ENABLE_ADVANCED_TREND_FILTER': True, 'ADVANCED_TREND_ADX_LENGTH': 14, 'ADVANCED_TREND_ADX_THRESHOLD': 18,
            'ADVANCED_TREND_SLOPE_LOOKBACK': 3, 'ADVANCED_TREND_SLOPE_MIN': 0.0010, 'ADVANCED_TREND_STRUCTURE_BARS': 3,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
            'TRAILING_TP_ACTIVATE_ROI': 0.16, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
            'TP_MARGIN_ROI': 0.22, 'SL_MARGIN_ROI': -0.55,
        },
    },
    {
        'label': 'AdvA-3Y',
        'days': 1095,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
            'ENABLE_DONCHIAN_BREAKOUT': True, 'DONCHIAN_LENGTH': 24, 'DONCHIAN_BREAKOUT_BUFFER_PCT': 0.0015,
            'DONCHIAN_VOLUME_MULT': 1.05, 'DONCHIAN_LONG_RSI_MIN': 52, 'DONCHIAN_LONG_RSI_MAX': 78,
            'DONCHIAN_SHORT_RSI_MIN': 20, 'DONCHIAN_SHORT_RSI_MAX': 48,
            'ENABLE_1H_TREND_FILTER': True, 'HOURLY_EMA_FAST': 10, 'HOURLY_EMA_SLOW': 30,
            'ENABLE_TREND_PYRAMIDING': True, 'TREND_PYRAMID_MAX_ADDS': 2, 'TREND_PYRAMID_TRIGGER_ROI': 0.05,
            'TREND_PYRAMID_MIN_PULLBACK': 0.008, 'ENABLE_TREND_EXIT': True, 'TREND_EXIT_ON_HOURLY_FLIP': True,
            'TREND_EXIT_USE_DONCHIAN_MID': True,
            'ENABLE_ADVANCED_TREND_FILTER': True, 'ADVANCED_TREND_ADX_LENGTH': 14, 'ADVANCED_TREND_ADX_THRESHOLD': 18,
            'ADVANCED_TREND_SLOPE_LOOKBACK': 3, 'ADVANCED_TREND_SLOPE_MIN': 0.0010, 'ADVANCED_TREND_STRUCTURE_BARS': 3,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
            'TRAILING_TP_ACTIVATE_ROI': 0.16, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
            'TP_MARGIN_ROI': 0.22, 'SL_MARGIN_ROI': -0.55,
        },
    },
    {
        'label': 'AdvB-2Y',
        'days': 730,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
            'ENABLE_DONCHIAN_BREAKOUT': True, 'DONCHIAN_LENGTH': 20, 'DONCHIAN_BREAKOUT_BUFFER_PCT': 0.0010,
            'DONCHIAN_VOLUME_MULT': 1.00, 'DONCHIAN_LONG_RSI_MIN': 50, 'DONCHIAN_LONG_RSI_MAX': 82,
            'DONCHIAN_SHORT_RSI_MIN': 18, 'DONCHIAN_SHORT_RSI_MAX': 50,
            'ENABLE_1H_TREND_FILTER': True, 'HOURLY_EMA_FAST': 12, 'HOURLY_EMA_SLOW': 36,
            'ENABLE_TREND_PYRAMIDING': True, 'TREND_PYRAMID_MAX_ADDS': 2, 'TREND_PYRAMID_TRIGGER_ROI': 0.04,
            'TREND_PYRAMID_MIN_PULLBACK': 0.005, 'ENABLE_TREND_EXIT': True, 'TREND_EXIT_ON_HOURLY_FLIP': True,
            'TREND_EXIT_USE_DONCHIAN_MID': False,
            'ENABLE_ADVANCED_TREND_FILTER': True, 'ADVANCED_TREND_ADX_LENGTH': 14, 'ADVANCED_TREND_ADX_THRESHOLD': 22,
            'ADVANCED_TREND_SLOPE_LOOKBACK': 4, 'ADVANCED_TREND_SLOPE_MIN': 0.0015, 'ADVANCED_TREND_STRUCTURE_BARS': 3,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
            'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
            'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
        },
    },
    {
        'label': 'AdvB-3Y',
        'days': 1095,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.0, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.45, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.50,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.090, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 33, 'RSI_SHORT_ENTRY': 67, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.45,
            'ENABLE_DONCHIAN_BREAKOUT': True, 'DONCHIAN_LENGTH': 20, 'DONCHIAN_BREAKOUT_BUFFER_PCT': 0.0010,
            'DONCHIAN_VOLUME_MULT': 1.00, 'DONCHIAN_LONG_RSI_MIN': 50, 'DONCHIAN_LONG_RSI_MAX': 82,
            'DONCHIAN_SHORT_RSI_MIN': 18, 'DONCHIAN_SHORT_RSI_MAX': 50,
            'ENABLE_1H_TREND_FILTER': True, 'HOURLY_EMA_FAST': 12, 'HOURLY_EMA_SLOW': 36,
            'ENABLE_TREND_PYRAMIDING': True, 'TREND_PYRAMID_MAX_ADDS': 2, 'TREND_PYRAMID_TRIGGER_ROI': 0.04,
            'TREND_PYRAMID_MIN_PULLBACK': 0.005, 'ENABLE_TREND_EXIT': True, 'TREND_EXIT_ON_HOURLY_FLIP': True,
            'TREND_EXIT_USE_DONCHIAN_MID': False,
            'ENABLE_ADVANCED_TREND_FILTER': True, 'ADVANCED_TREND_ADX_LENGTH': 14, 'ADVANCED_TREND_ADX_THRESHOLD': 22,
            'ADVANCED_TREND_SLOPE_LOOKBACK': 4, 'ADVANCED_TREND_SLOPE_MIN': 0.0015, 'ADVANCED_TREND_STRUCTURE_BARS': 3,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.35, 'MAX_CONSECUTIVE_LOSSES': 5,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.1, 'TIER_3_ATR_DEV_MULT': 1.8, 'MIN_TIER_DEV_PCT': 0.0025,
            'TRAILING_TP_ACTIVATE_ROI': 0.15, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.12,
            'TP_MARGIN_ROI': 0.20, 'SL_MARGIN_ROI': -0.55,
        },
    },
    {
        'label': 'AdvC-2Y',
        'days': 730,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.1, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.48, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.52,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.085, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.42,
            'ENABLE_DONCHIAN_BREAKOUT': True, 'DONCHIAN_LENGTH': 30, 'DONCHIAN_BREAKOUT_BUFFER_PCT': 0.0020,
            'DONCHIAN_VOLUME_MULT': 1.10, 'DONCHIAN_LONG_RSI_MIN': 54, 'DONCHIAN_LONG_RSI_MAX': 80,
            'DONCHIAN_SHORT_RSI_MIN': 18, 'DONCHIAN_SHORT_RSI_MAX': 46,
            'ENABLE_1H_TREND_FILTER': True, 'HOURLY_EMA_FAST': 12, 'HOURLY_EMA_SLOW': 48,
            'ENABLE_TREND_PYRAMIDING': True, 'TREND_PYRAMID_MAX_ADDS': 1, 'TREND_PYRAMID_TRIGGER_ROI': 0.06,
            'TREND_PYRAMID_MIN_PULLBACK': 0.010, 'ENABLE_TREND_EXIT': True, 'TREND_EXIT_ON_HOURLY_FLIP': True,
            'TREND_EXIT_USE_DONCHIAN_MID': True,
            'ENABLE_ADVANCED_TREND_FILTER': True, 'ADVANCED_TREND_ADX_LENGTH': 14, 'ADVANCED_TREND_ADX_THRESHOLD': 25,
            'ADVANCED_TREND_SLOPE_LOOKBACK': 4, 'ADVANCED_TREND_SLOPE_MIN': 0.0020, 'ADVANCED_TREND_STRUCTURE_BARS': 4,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.7, 'MIN_TIER_DEV_PCT': 0.0025,
            'TRAILING_TP_ACTIVATE_ROI': 0.18, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.10,
            'TP_MARGIN_ROI': 0.24, 'SL_MARGIN_ROI': -0.55,
        },
    },
    {
        'label': 'AdvC-3Y',
        'days': 1095,
        'params': {
            'DYNAMIC_TPSL': True, 'ATR_TP_MULT': 3.1, 'ATR_SL_MULT': 1.4,
            'ATR_TP_MIN_ROI': 0.12, 'ATR_TP_MAX_ROI': 0.48, 'ATR_SL_MIN_ROI': -0.14, 'ATR_SL_MAX_ROI': -0.52,
            'LEVERAGE': 7, 'TIER_MARGIN_PCT': 0.085, 'SIGNAL_MODE': 'classic',
            'RSI_LONG_ENTRY': 34, 'RSI_SHORT_ENTRY': 66, 'BB_ENTRY_BUFFER_PCT': 0.006, 'VOLUME_FILTER_MULT': 0.42,
            'ENABLE_DONCHIAN_BREAKOUT': True, 'DONCHIAN_LENGTH': 30, 'DONCHIAN_BREAKOUT_BUFFER_PCT': 0.0020,
            'DONCHIAN_VOLUME_MULT': 1.10, 'DONCHIAN_LONG_RSI_MIN': 54, 'DONCHIAN_LONG_RSI_MAX': 80,
            'DONCHIAN_SHORT_RSI_MIN': 18, 'DONCHIAN_SHORT_RSI_MAX': 46,
            'ENABLE_1H_TREND_FILTER': True, 'HOURLY_EMA_FAST': 12, 'HOURLY_EMA_SLOW': 48,
            'ENABLE_TREND_PYRAMIDING': True, 'TREND_PYRAMID_MAX_ADDS': 1, 'TREND_PYRAMID_TRIGGER_ROI': 0.06,
            'TREND_PYRAMID_MIN_PULLBACK': 0.010, 'ENABLE_TREND_EXIT': True, 'TREND_EXIT_ON_HOURLY_FLIP': True,
            'TREND_EXIT_USE_DONCHIAN_MID': True,
            'ENABLE_ADVANCED_TREND_FILTER': True, 'ADVANCED_TREND_ADX_LENGTH': 14, 'ADVANCED_TREND_ADX_THRESHOLD': 25,
            'ADVANCED_TREND_SLOPE_LOOKBACK': 4, 'ADVANCED_TREND_SLOPE_MIN': 0.0020, 'ADVANCED_TREND_STRUCTURE_BARS': 4,
            'ENABLE_MONTHLY_CIRCUIT_BREAKER': True, 'MONTHLY_LOSS_LIMIT_PCT': -0.30, 'MAX_CONSECUTIVE_LOSSES': 5,
            'DYNAMIC_TIER_DEVIATIONS': True, 'TIER_2_ATR_DEV_MULT': 1.0, 'TIER_3_ATR_DEV_MULT': 1.7, 'MIN_TIER_DEV_PCT': 0.0025,
            'TRAILING_TP_ACTIVATE_ROI': 0.18, 'TRAILING_TP_CALLBACK_ROI': 0.05,
            'TIER_2_DEV_PCT': 0.008, 'TIER_3_DEV_PCT': 0.015, 'SL_GLOBAL_CAP_PCT': -0.10,
            'TP_MARGIN_ROI': 0.24, 'SL_MARGIN_ROI': -0.55,
        },
    },
]


def run_scenario(iteration_num, scenario):
    try:
        full_params = {
            'EMA_FAST': config.EMA_FAST,
            'EMA_SLOW': config.EMA_SLOW,
            'MACD_FAST': config.MACD_FAST,
            'MACD_SLOW': config.MACD_SLOW,
            'MACD_SIGNAL': config.MACD_SIGNAL,
            'MACD_LONG_RSI_MAX': config.MACD_LONG_RSI_MAX,
            'MACD_SHORT_RSI_MIN': config.MACD_SHORT_RSI_MIN,
            'EMA_LONG_RSI_MAX': config.EMA_LONG_RSI_MAX,
            'EMA_SHORT_RSI_MIN': config.EMA_SHORT_RSI_MIN,
            'TREND_SMA_LENGTH': config.TREND_SMA_LENGTH,
            'FUNDING_RATE': config.FUNDING_RATE,
            'FUNDING_INTERVAL_HOURS': config.FUNDING_INTERVAL_HOURS,
            'FEE_RATE': config.FEE_RATE,
            'COMPOUND_MODE': config.COMPOUND_MODE,
            'BASE_CAPITAL': config.BASE_CAPITAL,
            'MAX_ACTIVE_TRADES': config.MAX_ACTIVE_TRADES,
            'COOLDOWN_CANDLES': config.COOLDOWN_CANDLES,
            'CONSECUTIVE_LOSS_COOLDOWN_MULT': config.CONSECUTIVE_LOSS_COOLDOWN_MULT,
            'MONTHLY_LOSS_LIMIT_PCT': config.MONTHLY_LOSS_LIMIT_PCT,
            'DONCHIAN_LENGTH': config.DONCHIAN_LENGTH,
            'DONCHIAN_BREAKOUT_BUFFER_PCT': config.DONCHIAN_BREAKOUT_BUFFER_PCT,
            'DONCHIAN_VOLUME_MULT': config.DONCHIAN_VOLUME_MULT,
            'DONCHIAN_LONG_RSI_MIN': config.DONCHIAN_LONG_RSI_MIN,
            'DONCHIAN_LONG_RSI_MAX': config.DONCHIAN_LONG_RSI_MAX,
            'DONCHIAN_SHORT_RSI_MIN': config.DONCHIAN_SHORT_RSI_MIN,
            'DONCHIAN_SHORT_RSI_MAX': config.DONCHIAN_SHORT_RSI_MAX,
            'ENABLE_1H_TREND_FILTER': config.ENABLE_1H_TREND_FILTER,
            'HOURLY_EMA_FAST': config.HOURLY_EMA_FAST,
            'HOURLY_EMA_SLOW': config.HOURLY_EMA_SLOW,
            'ENABLE_TREND_PYRAMIDING': config.ENABLE_TREND_PYRAMIDING,
            'TREND_PYRAMID_MAX_ADDS': config.TREND_PYRAMID_MAX_ADDS,
            'TREND_PYRAMID_TRIGGER_ROI': config.TREND_PYRAMID_TRIGGER_ROI,
            'TREND_PYRAMID_MIN_PULLBACK': config.TREND_PYRAMID_MIN_PULLBACK,
            'ENABLE_TREND_EXIT': config.ENABLE_TREND_EXIT,
            'TREND_EXIT_ON_HOURLY_FLIP': config.TREND_EXIT_ON_HOURLY_FLIP,
            'TREND_EXIT_USE_DONCHIAN_MID': config.TREND_EXIT_USE_DONCHIAN_MID,
            'ENABLE_ADVANCED_TREND_FILTER': config.ENABLE_ADVANCED_TREND_FILTER,
            'ADVANCED_TREND_ADX_LENGTH': config.ADVANCED_TREND_ADX_LENGTH,
            'ADVANCED_TREND_ADX_THRESHOLD': config.ADVANCED_TREND_ADX_THRESHOLD,
            'ADVANCED_TREND_SLOPE_LOOKBACK': config.ADVANCED_TREND_SLOPE_LOOKBACK,
            'ADVANCED_TREND_SLOPE_MIN': config.ADVANCED_TREND_SLOPE_MIN,
            'ADVANCED_TREND_STRUCTURE_BARS': config.ADVANCED_TREND_STRUCTURE_BARS,
        }
        full_params.update(scenario['params'])

        engine = BacktestEngine(days=scenario['days'], param_overrides=full_params)
        if not engine.run():
            raise RuntimeError(f"No historical data available for {scenario['days']}d window")

        closed_trades = [t for t in engine.trades if t['type'] == 'close']
        total_pnl = sum(t['pnl'] for t in closed_trades)
        monthly_data = engine.get_monthly_pnl_report()

        return {
            'iteration': iteration_num,
            'label': scenario['label'],
            'days': scenario['days'],
            'params': scenario['params'],
            'final_balance': engine.current_balance,
            'total_pnl': total_pnl,
            'total_trades': len(closed_trades),
            'win_rate': (sum(1 for t in closed_trades if t['pnl'] > 0) / len(closed_trades) * 100) if closed_trades else 0,
            'max_drawdown': engine.max_drawdown * 100,
            'avg_monthly_pnl': (sum(m['net_pnl'] for m in monthly_data) / len(monthly_data)) if monthly_data else 0,
        }
    except Exception as e:
        return {
            'iteration': iteration_num,
            'label': scenario['label'],
            'days': scenario['days'],
            'params': scenario['params'],
            'error': str(e),
            'final_balance': 0,
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'max_drawdown': 100,
            'avg_monthly_pnl': 0,
        }


def save_results(results, filename=None):
    if filename is None:
        filename = os.path.join(BASE_DIR, "optimization_phase10_multiyear.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Phase 10 Multi-Year Robustness Report\n")
        f.write(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Goal: robustness on 730d and 1095d windows using {config.BASE_CAPITAL} USDT capital\n")
        f.write("=" * 72 + "\n\n")
        for result in results:
            f.write(f"Iteration #{result['iteration']} | {result['label']}\n")
            if 'error' in result:
                f.write(f"  ERROR: {result['error']}\n\n")
                continue
            f.write(
                f"  Days={result['days']} | PnL={result['total_pnl']:+.2f} | Final={result['final_balance']:.2f} | "
                f"WR={result['win_rate']:.1f}% | DD={result['max_drawdown']:.1f}% | Trades={result['total_trades']} | "
                f"AvgM={result['avg_monthly_pnl']:+.2f}\n\n"
            )


def main():
    total_scenarios = len(SCENARIOS)
    print("=" * 72)
    print(f"🚀 PHASE 10 MULTI-YEAR ROBUSTNESS OPTIMIZER ({total_scenarios} SCENARIOS)")
    print("=" * 72)
    print(f"Initial Capital: {config.BASE_CAPITAL} USDT")
    print("Windows: 730d and 1095d")
    print("=" * 72)

    results = []
    for i, scenario in enumerate(SCENARIOS, start=1):
        sys.stdout.write(f"\r⏳ Running scenario {i}/{total_scenarios}...")
        sys.stdout.flush()
        result = run_scenario(i, scenario)
        results.append(result)
        if 'error' in result:
            sys.stdout.write(f"\r❌ Scenario {i}/{total_scenarios} | {scenario['label']} | ERROR: {result['error']}\n")
        else:
            sys.stdout.write(
                f"\r✅ Scenario {i}/{total_scenarios} | {scenario['label']} | PnL: {result['total_pnl']:+.2f} | "
                f"DD: {result['max_drawdown']:.1f}% | Trades: {result['total_trades']}\n"
            )

    valid = [r for r in results if 'error' not in r and r['total_trades'] > 0]
    valid.sort(key=lambda r: r['total_pnl'], reverse=True)
    if valid:
        print("\n" + "=" * 72)
        print("🏆 PHASE 10 RANKING BY TOTAL PNL")
        print("=" * 72)
        for rank, result in enumerate(valid, start=1):
            marker = " ⭐ BEST" if rank == 1 else ""
            print(
                f"#{rank} {result['label']}{marker} | Days {result['days']} | PnL {result['total_pnl']:+.2f} | "
                f"Final {result['final_balance']:.2f} | DD {result['max_drawdown']:.1f}% | Trades {result['total_trades']}"
            )
        print("\n" + "=" * 72)
        print(f"Best multi-year PnL: {valid[0]['total_pnl']:+.2f} USDT")
        print("=" * 72)

    save_results(results)


if __name__ == "__main__":
    main()
