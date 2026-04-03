"""
eTrader — Binance Provider (Wrapper)
=====================================
Re-exports the existing BinanceCryptoProvider from data_provider.py
as part of the unified providers package.

This file exists so that the provider_factory can import from
a consistent location (app.execution.providers.*).
"""
from app.execution.data_provider import BinanceCryptoProvider

__all__ = ['BinanceCryptoProvider']
