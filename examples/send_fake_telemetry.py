"""Standalone telemetry protocol test, not an ezQuake integration."""
import json
import socket
import time

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    for i in range(20):
        packet = {'map': 'testmap', 'origin': [i * 110.0, 0.0, 24.0],
                  'yaw': 0, 'health': 100, 'on_ground': True}
        sock.sendto(json.dumps(packet).encode(), ('127.0.0.1', 27999))
        time.sleep(.25)
