"""
Discrete Event Bus for RADAR (In-Memory Ring Buffer + Local Disk JSON Persistence).
eTrade v5.0 — Option C Hybrid Implementation
"""
import os
import json
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from app.core.logger import log_info, log_error, log_warning
from app.radar.config import RADAR_PARAMS, MODULE


class RadarEventBus:
    """
    Manages in-memory ring buffers of discrete market events per symbol,
    persisted locally to disk to survive worker restarts without consuming Supabase egress.
    """
    _instance = None

    def __init__(self, max_events_per_symbol: int = 100, cache_file: str = None):
        self.max_events = max_events_per_symbol
        self.cache_file = cache_file or RADAR_PARAMS['events_cache_path']
        self._events: Dict[str, deque] = {}  # symbol -> deque of events
        self._last_events: Dict[str, Dict[str, Any]] = {}  # (symbol, event_type) -> last event
        self._load_from_disk()

    @classmethod
    def get_instance(cls) -> 'RadarEventBus':
        if cls._instance is None:
            cls._instance = RadarEventBus()
        return cls._instance

    def publish(self, symbol: str, event: Dict[str, Any]) -> None:
        """
        Publishes a discrete event for a symbol and flushes to local disk.
        """
        sym = symbol.upper()
        if sym not in self._events:
            self._events[sym] = deque(maxlen=self.max_events)

        # Attach metadata if missing
        if 'timestamp' not in event:
            event['timestamp'] = datetime.now(timezone.utc).isoformat()
        if 'symbol' not in event:
            event['symbol'] = sym

        # Append to in-memory deque
        self._events[sym].append(event)
        
        # Track latest occurrence of this specific event_type for fast lookup
        event_type = event.get('event_type')
        if event_type:
            key = f"{sym}:{event_type}"
            self._last_events[key] = event

        # Persist to disk
        self._save_to_disk()

    def get_events(
        self, 
        symbol: str, 
        event_type: Optional[str] = None, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the most recent events for a symbol, optionally filtered by event_type.
        """
        sym = symbol.upper()
        if sym not in self._events:
            return []

        all_events = list(self._events[sym])
        if event_type:
            all_events = [e for e in all_events if e.get('event_type') == event_type]

        return all_events[-limit:]

    def get_latest_event(self, symbol: str, event_type: str) -> Optional[Dict[str, Any]]:
        """
        Returns the latest recorded event of a specific type for a symbol.
        """
        sym = symbol.upper()
        key = f"{sym}:{event_type}"
        return self._last_events.get(key)

    def _save_to_disk(self) -> None:
        """
        Saves all in-memory events to the local cache JSON file.
        """
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            data_to_save = {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'events': {sym: list(events) for sym, events in self._events.items()}
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, default=str)
        except Exception as e:
            log_error(f"[{MODULE}] Failed to persist events to disk ({self.cache_file}): {e}")

    def _load_from_disk(self) -> None:
        """
        Restores events from the local disk cache file on startup.
        """
        if not os.path.exists(self.cache_file):
            return

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                events_by_sym = data.get('events', {})
                for sym, ev_list in events_by_sym.items():
                    self._events[sym] = deque(ev_list, maxlen=self.max_events)
                    for ev in ev_list:
                        ev_type = ev.get('event_type')
                        if ev_type:
                            self._last_events[f"{sym}:{ev_type}"] = ev
            log_info(f"[{MODULE}] Restored {sum(len(v) for v in self._events.values())} events from local cache.")
        except Exception as e:
            log_warning(f"[{MODULE}] Could not load events cache from disk: {e}")
