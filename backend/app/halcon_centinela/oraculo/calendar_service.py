import os
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from app.core.logger import log_info, log_warning, log_error
from app.core.supabase_client import get_supabase
from app.halcon_centinela.config import SYMBOL_CURRENCY_MAP, GLOBAL_EVENTS, MODULE

class EconomicCalendarService:
    """Fetches economic calendar from Finnhub API and caches to Supabase."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('FINNHUB_API_KEY')
        self.base_url = 'https://finnhub.io/api/v1'
    
    def fetch_upcoming_events(self, hours_ahead: int = 48) -> list:
        """GET /calendar/economic with date range from today to +48h.
        Filters to only 'high' impact events.
        Returns: [{event_name, country, currency, impact, event_datetime}, ...]
        Handle API errors gracefully - return empty list on failure, log warning.
        """
        if not self.api_key:
            log_warning("FINNHUB_API_KEY not set. Cannot fetch economic calendar.", MODULE)
            return []
            
        try:
            now = datetime.now(timezone.utc)
            from_date = now.strftime('%Y-%m-%d')
            to_date = (now + timedelta(hours=hours_ahead)).strftime('%Y-%m-%d')
            
            url = f"{self.base_url}/calendar/economic?from={from_date}&to={to_date}&token={self.api_key}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            events = data.get('economicCalendar', [])
            
            high_impact_events = []
            for ev in events:
                impact = str(ev.get('impact', '')).lower()
                if impact in ('3', 'high', 'h'):
                    event_date = ev.get('date', '')
                    event_time = ev.get('time', '')
                    dt_str = f"{event_date} {event_time}"
                    try:
                        event_dt = datetime.strptime(dt_str.strip(), '%Y-%m-%d %H:%M')
                        event_dt = event_dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        try:
                            # Try with seconds if needed
                            event_dt = datetime.strptime(dt_str.strip(), '%Y-%m-%d %H:%M:%S')
                            event_dt = event_dt.replace(tzinfo=timezone.utc)
                        except ValueError:
                            # Fallback if time missing
                            event_dt = datetime.strptime(event_date, '%Y-%m-%d')
                            event_dt = event_dt.replace(tzinfo=timezone.utc)
                            
                    country = ev.get('country', '')
                    # Map rough currency from country just in case it's needed in output
                    currency_map = {'US': 'USD', 'EU': 'EUR', 'UK': 'GBP', 'GB': 'GBP', 'JP': 'JPY', 'AU': 'AUD', 'CA': 'CAD', 'CH': 'CHF', 'NZ': 'NZD'}
                    currency = currency_map.get(country.upper(), country.upper())
                    
                    high_impact_events.append({
                        'event_name': ev.get('event', ''),
                        'country': country,
                        'currency': currency,
                        'impact': 'high',
                        'event_datetime': event_dt
                    })
            return high_impact_events
        except Exception as e:
            log_warning(f"Failed to fetch economic calendar: {e}", MODULE)
            return []
    
    def sync_calendar(self) -> int:
        """Fetches events and upserts to oraculo_events table in Supabase.
        Marks global events (FOMC, NFP, CPI, BOJ_RATE, ECB_RATE, BOE_RATE).
        Returns count of new/updated events.
        Fail-safe: on any error, log error and return 0 (don't crash).
        """
        events = self.fetch_upcoming_events(hours_ahead=48)
        if not events:
            return 0
            
        try:
            supabase = get_supabase()
            records = []
            for ev in events:
                is_global = self._is_global_event(ev['event_name'])
                affected_symbols = self._map_currency_to_symbols(ev['currency'], is_global)
                
                record = {
                    'id': f"{ev['event_name']}_{ev['event_datetime'].isoformat()}".replace(" ", "_"),
                    'event_name': ev['event_name'],
                    'country': ev['country'],
                    'currency': ev['currency'],
                    'impact': ev['impact'],
                    'event_datetime': ev['event_datetime'].isoformat(),
                    'is_global': is_global,
                    'affected_symbols': affected_symbols,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                records.append(record)
                
            if records:
                supabase.table('oraculo_events').upsert(records, on_conflict='id').execute()
                log_info(f"Synced {len(records)} events to oraculo_events.", MODULE)
                return len(records)
            return 0
        except Exception as e:
            log_error(f"Error syncing calendar: {e}", MODULE)
            return 0
    
    def _is_global_event(self, event_name: str) -> bool:
        """Check if event matches GLOBAL_EVENTS list (case-insensitive partial match)."""
        name_lower = event_name.lower()
        synonyms = ['fomc', 'nfp', 'non-farm', 'nonfarm', 'payroll', 'cpi', 'inflation',
                    'interest rate', 'rate decision', 'fed', 'ecb', 'boj', 'boe']
        for s in synonyms:
            if s in name_lower:
                return True
        for g_event in GLOBAL_EVENTS:
            if g_event.lower() in name_lower:
                return True
        return False
    
    def _map_currency_to_symbols(self, currency: str, is_global: bool) -> list:
        """Map event currency to affected trading symbols using SYMBOL_CURRENCY_MAP.
        Global events affect ALL symbols.
        """
        if is_global:
            return list(SYMBOL_CURRENCY_MAP.keys())
            
        affected = []
        for symbol, currencies in SYMBOL_CURRENCY_MAP.items():
            if currency in currencies:
                affected.append(symbol)
        return affected
