import socket
import threading
from core.logger import logger

MSG_PORT = 57323  # TCP — separate from discovery UDP port (57322)

def start_message_listener(on_message_callback):
    def _listen():
        logger.info(f"Starting message listener on port {MSG_PORT}...")
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Allow immediate port reuse after restart
            try:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
            server.bind(("0.0.0.0", MSG_PORT))
            server.listen(5)
            server.settimeout(2.0)  # Don't block forever
            while True:
                try:
                    conn, addr = server.accept()
                    data = conn.recv(65536)
                    if data:
                        msg = data.decode('utf-8')
                        logger.info(f"Message received from {addr[0]}")
                        on_message_callback(addr[0], msg)
                    conn.close()
                except socket.timeout:
                    continue  # just loop back
                except Exception as e:
                    logger.error(f"Message connection error: {e}")
        except Exception as e:
            logger.error(f"Failed to start message listener: {e}")
                
    threading.Thread(target=_listen, daemon=True).start()

def send_message(ip, message):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((ip, MSG_PORT))
        sock.sendall(message.encode('utf-8'))
        sock.close()
        return True, "Message sent"
    except ConnectionRefusedError:
        return False, f"Connection refused on port {MSG_PORT}. Make sure Lab Sharing is open and running on the other device."
    except socket.timeout:
        return False, "Connection timed out. The device might be offline."
    except Exception as e:
        return False, str(e)
