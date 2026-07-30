import socket
import threading
import time
import struct

DISCOVERY_PORT = 57322
BROADCAST_INTERVAL = 2
SERVICE_NAME = "LAB-SHARING"


def get_all_interfaces():
    """Get all active network interfaces with their broadcast addresses"""
    interfaces = []
    try:
        import fcntl
        import array
        import struct

        SIOCGIFCONF = 0x8912
        SIOCGIFBRDADDR = 0x8919

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Get list of interfaces
        buf = array.array('B', b'\0' * 4096)
        ifconf = struct.pack('iL', buf.buffer_info()[1], buf.buffer_info()[0])
        fcntl.ioctl(s.fileno(), SIOCGIFCONF, ifconf)
        outbytes = struct.unpack('iL', ifconf)[0]
        namestr = buf.tobytes()

        for i in range(0, outbytes, 40):
            name = namestr[i:i+16].split(b'\0', 1)[0].decode()
            ip = socket.inet_ntoa(namestr[i+20:i+24])
            if ip != '127.0.0.1':
                # Get broadcast address
                try:
                    ifreq = struct.pack('16sH2s4s8s', name.encode(),
                                       socket.AF_INET, b'\x00'*2, b'\x00'*4, b'\x00'*8)
                    res = fcntl.ioctl(s.fileno(), SIOCGIFBRDADDR, ifreq)
                    bcast = socket.inet_ntoa(res[20:24])
                    interfaces.append((name, ip, bcast))
                except Exception:
                    pass
        s.close()
    except Exception:
        pass

    # Fallback
    if not interfaces:
        interfaces.append(('any', '0.0.0.0', '255.255.255.255'))

    return interfaces


class DeviceDiscovery:
    def __init__(self, on_device_found=None, on_device_lost=None):
        self.on_device_found = on_device_found
        self.on_device_lost = on_device_lost
        self.devices = {}  # ip -> {name, last_seen}
        self.running = False
        self.hostname = socket.gethostname()

    def start(self):
        self.running = True
        threading.Thread(target=self._broadcast, daemon=True).start()
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._cleanup, daemon=True).start()

    def stop(self):
        self.running = False

    def force_refresh(self):
        """Send immediate broadcast on all interfaces"""
        threading.Thread(target=self._send_broadcast_now, daemon=True).start()

    def _send_broadcast_now(self):
        msg = f"{SERVICE_NAME}:{self.hostname}".encode()
        interfaces = get_all_interfaces()
        for name, ip, bcast in interfaces:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.sendto(msg, (bcast, DISCOVERY_PORT))
                sock.sendto(msg, ('255.255.255.255', DISCOVERY_PORT))
                sock.close()
            except Exception:
                pass

    def _broadcast(self):
        msg = f"{SERVICE_NAME}:{self.hostname}".encode()
        while self.running:
            interfaces = get_all_interfaces()
            for name, ip, bcast in interfaces:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    # Send to specific interface broadcast
                    sock.sendto(msg, (bcast, DISCOVERY_PORT))
                    # Also send to global broadcast
                    sock.sendto(msg, ('255.255.255.255', DISCOVERY_PORT))
                    sock.close()
                except Exception:
                    pass
            time.sleep(BROADCAST_INTERVAL)

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', DISCOVERY_PORT))
        sock.settimeout(1)
        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                msg = data.decode()
                if msg.startswith(SERVICE_NAME + ":"):
                    ip = addr[0]
                    name = msg.split(":", 1)[1]
                    my_ips = self._get_all_local_ips()
                    if ip not in my_ips:
                        is_new = ip not in self.devices
                        self.devices[ip] = {"name": name, "last_seen": time.time()}
                        if is_new and self.on_device_found:
                            self.on_device_found(ip, name)
                        else:
                            # Update last seen
                            self.devices[ip]["last_seen"] = time.time()
            except socket.timeout:
                pass
            except Exception:
                pass
        sock.close()

    def _cleanup(self):
        while self.running:
            now = time.time()
            lost = [ip for ip, d in self.devices.items()
                    if now - d["last_seen"] > BROADCAST_INTERVAL * 5]
            for ip in lost:
                name = self.devices.pop(ip)["name"]
                if self.on_device_lost:
                    self.on_device_lost(ip, name)
            time.sleep(BROADCAST_INTERVAL)

    def _get_all_local_ips(self):
        ips = {'127.0.0.1'}
        try:
            hostname = socket.gethostname()
            ips.add(socket.gethostbyname(hostname))
        except Exception:
            pass
        for name, ip, bcast in get_all_interfaces():
            ips.add(ip)
        return ips

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
