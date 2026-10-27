"""Forecast for Family info / Desktop: Home Assistant's weather entity (found automatically, or [entities] weather)."""
import threading, time

from . import discover
from .ha import ha_forecast, ha_get, ha_states

_wx = {'at': 0, 'data': None}
_wx_lock = threading.Lock()


def weather_state():
    with _wx_lock:
        if _wx['data'] is None or time.time() - _wx['at'] > 50:
            try:
                ent = discover.weather_entity(ha_states() or [])
                if not ent:
                    return {'configured': False, 'error': 'no weather entity in Home Assistant (add the Met.no integration)'}
                st = ha_get('/api/states/' + ent)
                a = st.get('attributes', {})
                keep = ('datetime', 'condition', 'temperature', 'templow', 'precipitation', 'precipitation_probability', 'wind_speed', 'wind_gust_speed')
                def fc(kind):
                    try:
                        return [{k: f.get(k) for k in keep} for f in ha_forecast(ent, kind)]
                    except Exception:
                        return []
                _wx['data'] = {
                    'now': {'condition': st.get('state'), **{k: a.get(k) for k in ('temperature', 'apparent_temperature', 'humidity', 'wind_speed', 'wind_gust_speed', 'wind_bearing', 'uv_index')}},
                    'units': {k: a.get(k) for k in ('temperature_unit', 'wind_speed_unit', 'precipitation_unit')},
                    'hourly': fc('hourly')[:24], 'daily': fc('daily'), 'fetched': time.time()}
                _wx['at'] = time.time()
            except Exception as e:
                if _wx['data'] is None:
                    raise
                _wx['data'], _wx['at'] = {**_wx['data'], 'stale': str(e)[:120]}, time.time() - 20
        return _wx['data']
