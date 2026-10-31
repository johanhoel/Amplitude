"""ONVIF camera discovery."""
import socket, time

def discover_cameras(subnet="192.168.1"):
    results = []
    onvif_results = discover_onvif(subnet)
    if onvif_results: return onvif_results
    for i in range(1, 255):
        host = f"{subnet}.{i}"
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, 554))
            sock.close()
            if result == 0:
                results.append({"ip": host, "port": 554, "protocol": "RTSP", "name": f"Camera at {host}", "rtsp_url": f"rtsp://{host}:554/stream1"})
        except Exception: continue
    return results

def discover_onvif(subnet="192.168.1"):
    results = []
    probe = b'<?xml version="1.0"?><soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body/></soap:Envelope>'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)
    try:
        for i in range(1, 5):
            host = f"{subnet}.{i}"
            try: sock.sendto(probe, ("239.255.255.250", 3702))
            except Exception: continue
        start_time = time.time()
        while time.time() - start_time < 5.0:
            try:
                data, addr = sock.recvfrom(4096)
                name = f"ONVIF Camera at {addr[0]}"
                results.append({"ip": addr[0], "name": name, "protocol": "ONVIF", "rtsp_url": f"rtsp://{addr[0]}:554/stream1"})
            except socket.timeout: break
    finally: sock.close()
    return results
