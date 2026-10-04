"""MQTT subscriber that decouples the paho network thread from the GUI thread."""
from __future__ import annotations

import logging
import os
import queue

import paho.mqtt.client as mqtt

from csi_packets import parse_csi_payload

logger = logging.getLogger(__name__)


class CsiSubscriber:
    """Subscribes to the CSI topic and buffers parsed packets in a queue."""

    def __init__(self, host: str, port: int, topic, max_queue: int = 1024):
        self._host, self._port = host, port
        # One topic string or several patterns (multi-ESP32 links): the
        # subscriber registers exactly what it will subscribe to - no
        # hidden single-topic state (review finding R3-1).
        self._topics = tuple(topic) if isinstance(topic, (list, tuple)) else (topic,)
        self._queue: "queue.Queue" = queue.Queue(maxsize=max_queue)
        self._connected = False
        self._dropped = 0
        self._client = mqtt.Client(client_id=f"csi-backend-{os.getpid()}")
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # lifecycle --------------------------------------------------------------
    def start(self) -> None:
        logger.info("connecting to MQTT broker %s:%s", self._host, self._port)
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.disconnect()
        finally:
            self._client.loop_stop()

    # paho callbacks -----------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        self._connected = (rc == 0)
        if self._connected:
            for topic in self._topics:
                client.subscribe(topic, qos=0)
            logger.info("MQTT connected, subscribed to %s", ", ".join(self._topics))
        else:
            logger.warning("MQTT connect refused rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        logger.warning("MQTT disconnected (rc=%s); auto-reconnecting", rc)

    def _on_message(self, client, userdata, msg):
        packet = parse_csi_payload(msg.payload)
        if packet is None:
            return
        try:
            self._queue.put_nowait(packet)
        except queue.Full:
            self._dropped += 1

    # accessors ---------------------------------------------------------------
    def is_connected(self) -> bool:
        return self._connected

    def dropped(self) -> int:
        return self._dropped

    def drain(self, limit: int = 256):
        """Move up to `limit` buffered packets out of the queue."""
        out = []
        while len(out) < limit:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out
