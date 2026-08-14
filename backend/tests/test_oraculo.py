"""
Unit tests for ORÁCULO module (Economic Calendar, Pause Manager, Bracket Manager).
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.halcon_centinela.oraculo.calendar_service import EconomicCalendarService
from app.halcon_centinela.oraculo.pause_manager import OraculoPauseManager
from app.halcon_centinela.oraculo.bracket_manager import BracketManager
from app.halcon_centinela.config import ORACULO_PARAMS


def test_global_event_detection():
    service = EconomicCalendarService(api_key="test")
    assert service._is_global_event("US Non-Farm Payrolls") == True
    assert service._is_global_event("FOMC Rate Decision") == True
    assert service._is_global_event("German ZEW Economic Sentiment") == False


def test_currency_to_symbol_mapping():
    service = EconomicCalendarService(api_key="test")
    
    # USD impacts EURUSD, USDJPY, GBPUSD, XAUUSD, etc.
    usd_symbols = service._map_currency_to_symbols('USD', is_global=False)
    assert 'EURUSD' in usd_symbols
    assert 'USDJPY' in usd_symbols

    # Global impacts all
    global_symbols = service._map_currency_to_symbols('USD', is_global=True)
    assert len(global_symbols) >= 4


def test_bracket_calculation():
    manager = BracketManager(ORACULO_PARAMS)
    
    pos_long = {
        'id': 'pos_b1',
        'symbol': 'EURUSD',
        'direction': 'long',
        'entry_price': 1.0800,
        'current_price': 1.0750,
        'lots': 0.1,
        'current_pnl': -5.0
    }
    
    bracket = manager.place_bracket(pos_long, squeeze_active=False, market_type='forex')
    assert bracket['bracket_placed'] == True
    assert 'sl_price' in bracket
    assert bracket['sl_price'] < 1.0800
