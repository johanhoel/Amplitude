"""Forecast for Family info: Home Assistant's met.no entity ([entities] weather), now + 24 h hourly + daily."""
import threading, time

from .config import C
from .ha import ha_forecast, ha_get

_wx = {'at': 0, 'data': None}
_wx_lock = threading.Lock()


def weather_state():
    with _wx_lock:
        if _wx['data'] is None or time.time() - _wx['at'] > 50:
            try:
                st = ha_get('/api/states/' + C.WEATHER)
                a = st.get('attributes', {})
                keep = ('datetime', 'condition', 'temperature', 'templow', 'precipitation', 'precipitation_probability', 'wind_speed', 'wind_gust_speed')
                _wx['data'] = {
                    'now': {'condition': st.get('state'), **{k: a.get(k) for k in ('temperature', 'apparent_temperature', 'humidity', 'wind_speed', 'wind_gust_speed', 'wind_bearing', 'uv_index')}},
                    'units': {k: a.get(k) for k in ('temperature_unit', 'wind_speed_unit', 'precipitation_unit')},
                    'hourly': [{k: f.get(k) for k in keep} for f in ha_forecast('hourly')[:24]],
                    'daily': [{k: f.get(k) for k in keep} for f in ha_forecast('daily')],
                    'fetched': time.time()}
                _wx['at'] = time.time()
            except Exception as e:
                if _wx['data'] is None:
                    raise
                _wx['data'], _wx['at'] = {**_wx['data'], 'stale': str(e)[:120]}, time.time() - 20
        return _wx['data']
