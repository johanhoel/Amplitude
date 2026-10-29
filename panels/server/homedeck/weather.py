"""Forecast for Family info: Home Assistant's met.no entity ([entities] weather), now + 24 h hourly + daily."""
import re, threading, time

from .config import C
from .ha import ha_forecast, ha_get
from .layouts import layout_get

_wx = {'at': 0, 'data': None, 'eid': None}
_wx_lock = threading.Lock()


def entity():
    """The weather entity the editor picked, else the one in homedeck.toml."""
    try:
        eid = str((layout_get('familyinfo').get('weather') or {}).get('id') or '')
    except Exception:
        eid = ''
    return eid if re.fullmatch(r'weather\.[a-z0-9_]+', eid) else C.WEATHER


def weather_state():
    eid = entity()
    with _wx_lock:
        # A new entity means the cached forecast is for the wrong place, not merely old.
        if _wx['data'] is None or _wx['eid'] != eid or time.time() - _wx['at'] > 50:
            try:
                st = ha_get('/api/states/' + eid)
                a = st.get('attributes', {})
                keep = ('datetime', 'condition', 'temperature', 'templow', 'precipitation', 'precipitation_probability', 'wind_speed', 'wind_gust_speed')
                _wx['data'] = {
                    'now': {'condition': st.get('state'), **{k: a.get(k) for k in ('temperature', 'apparent_temperature', 'humidity', 'wind_speed', 'wind_gust_speed', 'wind_bearing', 'uv_index')}},
                    'units': {k: a.get(k) for k in ('temperature_unit', 'wind_speed_unit', 'precipitation_unit')},
                    'hourly': [{k: f.get(k) for k in keep} for f in ha_forecast('hourly', eid)[:24]],
                    'daily': [{k: f.get(k) for k in keep} for f in ha_forecast('daily', eid)],
                    'entity': eid, 'fetched': time.time()}
                _wx['at'], _wx['eid'] = time.time(), eid
            except Exception as e:
                if _wx['data'] is None:
                    raise
                _wx['data'], _wx['at'] = {**_wx['data'], 'stale': str(e)[:120]}, time.time() - 20
        return _wx['data']
