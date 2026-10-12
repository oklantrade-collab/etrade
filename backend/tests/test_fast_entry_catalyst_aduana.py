"""
Unit tests for Phase 2 & Phase 3 Intraday Stock Engine:
- Fast Entry Engine (Multi-TF ADX, +DI/-DI, ORB Breakout, VWAP Absorption, ADX Explosion)
- Catalyst & News Classifier (Tier 0 Dilution Veto, Tier 1 FDA/M&A, Tier 2 Earnings Beat)
- Aduana Stocks Exit Engine (UPPER_5 TP50 Partial Profit, UPPER_6 Climax, EOD Hard-Exit at 15:50 ET)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import pytest

from app.stocks.catalyst_classifier import classify_catalyst_text, analyze_news_items
from app.stocks.fast_entry_engine import (
    compute_adx_di_summary,
    detect_candle_absorption_5m,
    evaluate_fast_entry,
)
from app.stocks.aduana_stocks_exit_engine import (
    is_eod_hard_deadline,
    is_eod_final_candles,
    evaluate_accelerated_trailing_stop,
    evaluate_aduana_stocks_exit,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. CATALYST CLASSIFIER TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_catalyst_classifier_tier0_toxic_dilution():
    """Verifica detección de noticias tóxicas de dilución (Tier 0 -> VETO)."""
    toxic_headlines = [
        "Company Announces Pricing of $10.0M Public Offering of Common Stock",
        "BioTech Corp Enters into At-The-Market (ATM) Offering Agreement",
        "Files S-3 Registration Statement with Series A Warrants Dilution",
        "Reverse Stock Split 1-for-20 to Maintain Nasdaq Compliance",
        "Company Receives Nasdaq Delisting Notice for Minimum Bid Violation",
    ]
    for headline in toxic_headlines:
        res = classify_catalyst_text(headline)
        assert res['tier'] == 0, f"Debería ser Tier 0: {headline}"
        assert res['is_toxic'] is True
        assert res['catalyst_name'] == 'TOXIC_DILUTION_RISK'
        assert res['impact_score'] < 0


def test_catalyst_classifier_tier1_transformative():
    """Verifica catalizadores de máximo impacto Tier 1 (FDA, M&A, Contratos)."""
    tier1_headlines = [
        ("FDA Approves New Drug Application for Novel Oncology Treatment", ""),
        ("Primary Endpoint Met in Pivotal Phase 3 Trial with P < 0.001", ""),
        ("Pharma Giant Signs Definitive Merger Agreement to Acquire Biotech at $45/sh", ""),
        ("Receives $120M Department of Defense Contract for Tactical Systems", ""),
    ]
    for headline, summary in tier1_headlines:
        res = classify_catalyst_text(headline, summary)
        assert res['tier'] == 1, f"Debería ser Tier 1: {headline}"
        assert res['is_toxic'] is False
        assert res['catalyst_name'] == 'TIER_1_TRANSFORMATIVE'
        assert res['impact_score'] >= 90


def test_catalyst_classifier_tier2_expansion():
    """Verifica catalizadores de alto crecimiento Tier 2 (Earnings beat, AI partnership)."""
    tier2_headlines = [
        "Reports Record Q3 Revenue and Substantial Earnings Beat, Raises Full-Year Guidance",
        "Announces Strategic Partnership with Tech Giant for AI-Powered Analytics",
    ]
    for headline in tier2_headlines:
        res = classify_catalyst_text(headline)
        assert res['tier'] == 2, f"Debería ser Tier 2: {headline}"
        assert res['is_toxic'] is False
        assert res['catalyst_name'] == 'TIER_2_EXPANSION'
        assert res['impact_score'] >= 70


def test_catalyst_news_items_toxic_veto_dominance():
    """Si una lista contiene una noticia positiva y otra de dilución, Tier 0 veta incondicionalmente."""
    news_feed = [
        {"title": "FDA Approves Breakthrough Therapy Designation", "summary": "Positive Phase 2 data"},
        {"title": "Company Prices $5M Public Offering and Pre-Funded Warrants", "summary": "Offering at discount"},
        {"title": "Q2 Earnings Beat Analysts Expectations", "summary": "Revenue up 40%"},
    ]
    res = analyze_news_items(news_feed)
    assert res['tier'] == 0
    assert res['is_toxic'] is True
    assert res['catalyst_name'] == 'TOXIC_DILUTION_RISK'


def test_catalyst_news_items_clean_tier1_selection():
    """Si no hay noticias tóxicas, la noticia más transformadora (Tier 1) domina la lista."""
    news_feed = [
        {"title": "Company Announces Presentation at Investor Conference", "summary": "PR general"},
        {"title": "FDA Clears Investigational New Drug Application for Lead Compound", "summary": "FDA clears IND"},
        {"title": "Quarterly Operational Updates", "summary": "Status report"},
    ]
    res = analyze_news_items(news_feed)
    assert res['tier'] == 1
    assert res['is_toxic'] is False
    assert res['catalyst_name'] == 'TIER_1_TRANSFORMATIVE'


# ══════════════════════════════════════════════════════════════════════════════
# 2. FAST ENTRY ENGINE TESTS
# ══════════════════════════════════════════════════════════════════════════════

def _generate_synthetic_candles(n: int, base_price: float = 10.0, trend: float = 0.05, high_wick: bool = False):
    """Genera dataframe sintético con columnas OHLCV para pruebas de ADX y velas."""
    data = []
    p = base_price
    for i in range(n):
        o = p
        p = p + trend + np.sin(i / 3.0) * 0.02
        c = p
        l = min(o, c) - 0.03
        h = max(o, c) + 0.04
        if high_wick and i == n - 1:
            l = min(o, c) - 0.15 # lower wick prominente
        data.append({
            'open': o,
            'high': h,
            'low': l,
            'close': c,
            'volume': 100000 + i * 5000
        })
    return pd.DataFrame(data)


def test_adx_di_summary_calculation():
    """Verifica que compute_adx_di_summary calcula correctamente ADX, +DI, -DI."""
    df_uptrend = _generate_synthetic_candles(30, base_price=10.0, trend=0.15)
    summary = compute_adx_di_summary(df_uptrend)
    assert summary['valid'] is True
    assert summary['plus_di'] > summary['minus_di']
    assert summary['is_bullish_di'] is True
    assert summary['adx'] > 0


def test_candle_absorption_5m_detection():
    """Verifica detección de mecha inferior >= 35% como absorción compradora."""
    df_wick = _generate_synthetic_candles(10, base_price=10.0, trend=0.01, high_wick=True)
    res = detect_candle_absorption_5m(df_wick)
    assert res['has_absorption'] is True
    assert res['lower_wick_pct'] >= 35.0


def test_fast_entry_blocked_by_trap():
    """Verifica que si is_trap=True, Fast Entry Engine rechaza la entrada de inmediato."""
    df_5m = _generate_synthetic_candles(20, base_price=15.0)
    res = evaluate_fast_entry(current_price=15.0, df_5m=df_5m, is_trap=True)
    assert res['fast_entry_triggered'] is False
    assert "Trap Shield" in res['entry_reason']


def test_fast_entry_orb_breakout():
    """Verifica gatillo ORB_BREAKOUT_FAST al superar el máximo de apertura con +DI dominante."""
    # Primeras velas establecen ORB_High en 10.50
    candles = [
        {'open': 10.0, 'high': 10.50, 'low': 9.90, 'close': 10.30, 'volume': 200000}, # Vela de apertura
        {'open': 10.30, 'high': 10.45, 'low': 10.20, 'close': 10.40, 'volume': 150000},
    ]
    # Agregar velas en tendencia para que ADX sea alcista
    for i in range(20):
        c = 10.40 + i * 0.02
        candles.append({'open': c - 0.01, 'high': c + 0.02, 'low': c - 0.02, 'close': c, 'volume': 100000})

    df_5m = pd.DataFrame(candles)
    # Precio actual 10.85 (claramente sobre 10.50 ORB High)
    res = evaluate_fast_entry(
        current_price=10.85,
        df_5m=df_5m,
        rvol=3.0,
        bands_15m={'upper_5': 11.50, 'upper_6': 12.00},
        is_trap=False
    )
    assert res['fast_entry_triggered'] is True
    assert res['entry_type'] == 'ORB_BREAKOUT_FAST'
    assert res['target_upper5'] == 11.50
    assert res['target_upper6'] == 12.00
    assert res['recommended_sl'] > 0


def test_fast_entry_adx_momentum_ignition():
    """Verifica gatillo ADX_DI_EXPLOSION con +DI fuerte, delta alto y RVOL explosivo."""
    df_5m = _generate_synthetic_candles(30, base_price=5.0, trend=0.12)
    # Simular precio y RVOL alto sin ORB (o tras el inicio)
    res = evaluate_fast_entry(
        current_price=8.50,
        df_5m=df_5m,
        rvol=4.0,
        bands_15m={'upper_5': 9.20, 'upper_6': 9.80},
        is_trap=False
    )
    assert res['fast_entry_triggered'] is True
    assert res['entry_type'] in ('ORB_BREAKOUT_FAST', 'ADX_DI_EXPLOSION')


# ══════════════════════════════════════════════════════════════════════════════
# 3. ADUANA STOCKS EXIT ENGINE TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_is_eod_hard_deadline_times():
    """Verifica el umbral estricto de cierre forzoso (15:50 ET a 16:05 ET)."""
    ny_tz = ZoneInfo('America/New_York')
    # 15:45 ET -> No es hard deadline
    dt_1545 = datetime(2026, 10, 9, 15, 45, tzinfo=ny_tz)
    assert is_eod_hard_deadline(dt_1545) is False

    # 15:50 ET -> Es hard deadline
    dt_1550 = datetime(2026, 10, 9, 15, 50, tzinfo=ny_tz)
    assert is_eod_hard_deadline(dt_1550) is True

    # 15:55 ET -> Es hard deadline
    dt_1555 = datetime(2026, 10, 9, 15, 55, tzinfo=ny_tz)
    assert is_eod_hard_deadline(dt_1555) is True

    # 16:05 ET -> Es hard deadline
    dt_1605 = datetime(2026, 10, 9, 16, 5, tzinfo=ny_tz)
    assert is_eod_hard_deadline(dt_1605) is True

    # 16:10 ET -> Fuera de la ventana del cierre regular
    dt_1610 = datetime(2026, 10, 9, 16, 10, tzinfo=ny_tz)
    assert is_eod_hard_deadline(dt_1610) is False


def test_accelerated_trailing_stop_upper5_tp50():
    """Verifica toma de ganancia parcial del 50% al tocar UPPER_5 cuando ganancia >= +2.5%."""
    position = {
        'symbol': 'TEST',
        'side': 'long',
        'entry_price': 10.0,
        'shares': 100,
        'tp_block1_executed': False,
        'climax_tp50_done': False
    }
    bands_15m = {
        'upper_5': 10.50,
        'upper_6': 11.20
    }
    # Precio actual toca UPPER_5 ($10.50, +5.0% gain)
    res = evaluate_accelerated_trailing_stop(
        position=position,
        current_price=10.50,
        df_5m=None,
        bands_15m=bands_15m,
        side='long'
    )
    assert res['action'] == 'TAKE_PROFIT_50_CLIMAX'
    assert res['pct'] == 50
    assert 'ADUANA_STK_CLIMAX_UPPER_5_TP50' in res['rule_code']
    assert "UPPER_5" in res['reason']


def test_accelerated_trailing_stop_upper6_tp50():
    """Verifica toma de ganancia parcial del 50% en clímax extremo al tocar UPPER_6."""
    position = {
        'symbol': 'TEST',
        'side': 'long',
        'entry_price': 10.0,
        'shares': 100,
        'tp_block1_executed': False,
        'climax_tp50_done': False
    }
    bands_15m = {
        'upper_5': 10.50,
        'upper_6': 11.20
    }
    # Precio actual toca UPPER_6 ($11.25, +12.5% gain)
    res = evaluate_accelerated_trailing_stop(
        position=position,
        current_price=11.25,
        df_5m=None,
        bands_15m=bands_15m,
        side='long'
    )
    assert res['action'] == 'TAKE_PROFIT_50_CLIMAX'
    assert res['pct'] == 50
    assert 'ADUANA_STK_CLIMAX_UPPER_6_TP50' in res['rule_code']


def test_stocks_aduana_exit_eod_hard_exit_1550_in_profit():
    """A las 15:50 ET, evaluate_stocks_aduana_exit liquida el 100% incondicionalmente con ganancia."""
    ny_tz = ZoneInfo('America/New_York')
    at_1550 = datetime(2026, 10, 9, 15, 50, 0, tzinfo=ny_tz)

    position = {
        'symbol': 'RUNNER',
        'side': 'long',
        'entry_price': 10.0,
        'shares': 500,
    }
    res = evaluate_aduana_stocks_exit(
        position=position,
        current_price=12.50, # Ganancia +25%
        now_dt=at_1550
    )
    assert res['should_close'] is True
    assert res['action'] == 'CLOSE_TOTAL'
    assert res['shares_to_close'] == 500
    assert res['pct_to_close'] == 100
    assert res['rule_code'] == 'ADUANA_STK_EOD_HARD_EXIT'
    assert "Cero overnight" in res['reason'] or "riesgo nocturno" in res['reason']


def test_stocks_aduana_exit_eod_hard_exit_1550_in_loss():
    """A las 15:50 ET, evaluate_aduana_stocks_exit liquida el 100% incondicionalmente AÚN SI ESTÁ EN PÉRDIDA."""
    ny_tz = ZoneInfo('America/New_York')
    at_1552 = datetime(2026, 10, 9, 15, 52, 0, tzinfo=ny_tz)

    position = {
        'symbol': 'FLAT',
        'side': 'long',
        'entry_price': 10.0,
        'shares': 200,
    }
    res = evaluate_aduana_stocks_exit(
        position=position,
        current_price=9.85, # Pérdida -1.5%
        now_dt=at_1552
    )
    assert res['should_close'] is True
    assert res['action'] == 'CLOSE_TOTAL'
    assert res['shares_to_close'] == 200
    assert res['pct_to_close'] == 100
    assert res['rule_code'] == 'ADUANA_STK_EOD_HARD_EXIT'
    assert res['gain_pct'] == -1.50
