"""Home Assistant integration: MQTT auto-discovery entities + events, and/or a webhook.

Broker and webhook are set on the Settings page (or MQTT_* / HA_WEBHOOK_URL in .env); a change there reconnects
within CHECK_SECONDS without a restart.

MQTT (recommended): set the broker host. camwatch appears in HA as a device with
  binary sensors   motion, one per detected object type (person, car...), camera online
  camera           snapshot of the latest event
  sensors          last event (timestamp), last identified person
  event entity     fires for every detection/identification - use it as an automation trigger
Webhook: http://<ha>:8123/api/webhook/<id>; every event is POSTed as JSON.
"""
import datetime as dt
import json
import threading
import time
import urllib.request

from common import env
import settings

EVENT_TYPES = ["motion", "loitering", "plate", "vehicle_arrived", "vehicle_left", "identified", "unknown_face",
               "camera_offline", "camera_online", "recording_stalled", "recording_resumed", "package_delivered", "package_picked_up", "unusual", "test"]
CHECK_SECONDS = 10


def zone_key(name):
    return "zone_" + "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


class HomeAssistant:
    def __init__(self, log, role, labels=(), on_armed=None):
        """role 'recorder' owns discovery and availability; other roles only publish.
        on_armed(bool) is called when the Armed switch is flipped in Home Assistant."""
        self.log = log
        self.on_armed = on_armed
        self.zones = []
        self.published_zones = set()
        self.camera = env("CAMERA_NAME", "camera")
        self.base = f"{env('MQTT_TOPIC_PREFIX', 'camwatch')}/{self.camera}"
        self.discovery_prefix = env("MQTT_DISCOVERY_PREFIX", "homeassistant")
        self.web = (env("WEB_BASE_URL", "") or "").rstrip("/")
        self.webhook = None
        self.labels = list(labels)
        self.role = role
        self.client = None
        self.broker = None
        self.retained_msgs = {}  # topic -> payload, sent again after (re)connecting to a broker
        self.lock = threading.RLock()
        self.next_check = 0.0
        self.conf_mtime = None
        self._check()

    def _check(self):
        """Pick up broker / webhook changes from the Settings page."""
        if time.time() < self.next_check:
            return
        with self.lock:
            self.next_check = time.time() + CHECK_SECONDS
            if settings.mtime() == self.conf_mtime:
                return
            self.conf_mtime = settings.mtime()
            cfg = settings.integration()
            self.webhook = cfg["ha_webhook_url"] or None
            broker = (cfg["mqtt_host"], cfg["mqtt_port"], cfg["mqtt_user"], cfg["mqtt_password"])
            if broker == self.broker:
                return
            if self.client:
                self.log.info("MQTT settings changed - reconnecting")
                if self.role == "recorder":
                    self.client.publish(f"{self.base}/availability", "offline", retain=True)
                self.client.disconnect()
                self.client.loop_stop()
                self.client = None
            self.broker = broker
            if cfg["mqtt_host"]:
                self._connect(*broker)

    def _connect(self, host, port, user, password):
        import paho.mqtt.client as mqtt

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"camwatch-{self.camera}-{self.role}")
        if user:
            self.client.username_pw_set(user, password)
        if self.role == "recorder":
            self.client.will_set(f"{self.base}/availability", "offline", retain=True)
        self.client.on_connect = self._on_connect
        self.client.reconnect_delay_set(2, 60)
        self.client.connect_async(host, port, keepalive=60)
        self.client.loop_start()

    @property
    def enabled(self):
        return bool(self.client or self.webhook)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.log.warning("MQTT connection refused: %s", reason_code)
            return
        self.log.info("connected to MQTT")
        if self.role == "recorder":
            self._discovery()
            client.publish(f"{self.base}/availability", "online", retain=True)
            client.subscribe(f"{self.base}/armed/set")
            client.on_message = self._on_message
        for topic, payload in list(self.retained_msgs.items()):
            client.publish(topic, payload, retain=True)

    def _on_message(self, client, userdata, msg):
        if msg.topic.endswith("/armed/set") and self.on_armed:
            self.on_armed(msg.payload.decode().strip().upper() == "ON")

    def _publish_config(self, component, key, config):
        uid = f"camwatch_{self.camera}"
        device = {"identifiers": [uid], "name": f"camwatch {self.camera}", "manufacturer": "camwatch",
                  "model": "RTSP recorder"}
        if self.web:
            device["configuration_url"] = self.web
        config = {"device": device, "availability_topic": f"{self.base}/availability",
                  "unique_id": f"{uid}_{key}", "has_entity_name": True, **config}
        self.client.publish(f"{self.discovery_prefix}/{component}/{uid}/{key}/config",
                            json.dumps(config), retain=True)

    def set_zones(self, names):
        """Publish one binary sensor per trigger zone; remove sensors of deleted zones."""
        self.zones = list(names)
        self._check()
        if not self.client or self.role != "recorder":
            return
        keys = {zone_key(n): n for n in self.zones}
        for key, name in keys.items():
            self._publish_config("binary_sensor", key, {"name": f"Zone {name}", "device_class": "occupancy",
                                                        "state_topic": f"{self.base}/{key}"})
        uid = f"camwatch_{self.camera}"
        for key in self.published_zones - set(keys):
            self.client.publish(f"{self.discovery_prefix}/binary_sensor/{uid}/{key}/config", "", retain=True)
        self.published_zones = set(keys)

    def _discovery(self):
        publish = self._publish_config
        self.published_zones = set()
        self.set_zones(self.zones)
        publish("switch", "armed", {"name": "Armed", "icon": "mdi:shield-home",
                                    "state_topic": f"{self.base}/armed", "command_topic": f"{self.base}/armed/set"})
        publish("binary_sensor", "motion", {"name": "Motion", "device_class": "motion",
                                            "state_topic": f"{self.base}/motion"})
        for label in self.labels:
            key = label.replace(" ", "_")
            config = {"name": label.title(), "state_topic": f"{self.base}/{key}"}
            if label == "person":
                config["device_class"] = "occupancy"
            publish("binary_sensor", key, config)
        publish("binary_sensor", "online", {"name": "Camera online", "device_class": "connectivity",
                                            "entity_category": "diagnostic", "state_topic": f"{self.base}/online"})
        publish("camera", "snapshot", {"name": "Last event", "topic": f"{self.base}/snapshot"})
        publish("sensor", "last_event", {"name": "Last event time", "device_class": "timestamp",
                                         "state_topic": f"{self.base}/last_event",
                                         "value_template": "{{ value_json.time }}",
                                         "json_attributes_topic": f"{self.base}/last_event"})
        publish("sensor", "last_identified", {"name": "Last identified", "icon": "mdi:face-recognition",
                                              "state_topic": f"{self.base}/last_identified",
                                              "value_template": "{{ value_json.name }}",
                                              "json_attributes_topic": f"{self.base}/last_identified"})
        publish("sensor", "last_plate", {"name": "Last plate", "icon": "mdi:car-search",
                                         "state_topic": f"{self.base}/last_plate",
                                         "value_template": "{{ value_json.plate }}",
                                         "json_attributes_topic": f"{self.base}/last_plate"})
        publish("event", "detection", {"name": "Detection", "state_topic": f"{self.base}/event",
                                       "event_types": self.labels + EVENT_TYPES})

    # ---------- publishing ----------

    def _retain(self, key, payload):
        topic = f"{self.base}/{key}"
        self.retained_msgs[topic] = payload
        self._check()
        if self.client:
            self.client.publish(topic, payload, retain=True)

    def state(self, key, on):
        self._retain(key.replace(" ", "_"), "ON" if on else "OFF")

    def snapshot(self, jpg_bytes):
        self._retain("snapshot", jpg_bytes)

    def retained(self, key, payload):
        self._retain(key, json.dumps(payload))

    def links(self, day, stem):
        if not self.web:
            return {}
        return {"clip_url": f"{self.web}/clip/{day}/{stem}", "snapshot_url": f"{self.web}/media/{day}/{stem}.jpg"}

    def event(self, event_type, **data):
        payload = {"event_type": event_type, "camera": self.camera,
                   "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"), **data}
        self._check()
        if self.client:
            self.client.publish(f"{self.base}/event", json.dumps(payload))
        if self.webhook:
            threading.Thread(target=self._post, args=(payload,), daemon=True).start()
        return payload

    def _post(self, payload):
        url = self.webhook
        if not url:
            return
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10).read()
        except OSError as exc:
            self.log.warning("Home Assistant webhook failed: %s", exc)
