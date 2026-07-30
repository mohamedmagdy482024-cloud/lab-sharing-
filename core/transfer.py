import socket
import os
import struct
import threading
import time
from core.logger import logger

TRANSFER_PORT = 57321
BUFFER_SIZE = 65536


def send_folder(folder_path: str, receiver_ip: str, progress_callback=None, done_callback=None, speed_callback=None):
    def _send():
        logger.info(f"=== SEND START ===")
        logger.info(f"Folder: {folder_path}")
        logger.info(f"Receiver IP: {receiver_ip}:{TRANSFER_PORT}")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            logger.info(f"Connecting to {receiver_ip}:{TRANSFER_PORT}...")
            sock.connect((receiver_ip, TRANSFER_PORT))
            sock.settimeout(None)
            logger.info("Connected successfully")

            files = []
            for root, dirs, filenames in os.walk(folder_path):
                for filename in filenames:
                    files.append(os.path.join(root, filename))

            total_files = len(files)
            base = os.path.dirname(folder_path)
            logger.info(f"Total files to send: {total_files}")

            sock.sendall(struct.pack(">I", total_files))

            for i, filepath in enumerate(files):
                rel_path = os.path.relpath(filepath, base)
                rel_path_encoded = rel_path.encode("utf-8")
                file_size = os.path.getsize(filepath)
                logger.info(f"Sending [{i+1}/{total_files}]: {rel_path} ({file_size} bytes)")

                sock.sendall(struct.pack(">I", len(rel_path_encoded)))
                sock.sendall(rel_path_encoded)
                sock.sendall(struct.pack(">Q", file_size))

                sent = 0
                start_time = time.time()
                last_time = start_time
                last_sent = 0

                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(BUFFER_SIZE)
                        if not chunk:
                            break
                        sock.sendall(chunk)
                        sent += len(chunk)

                        now = time.time()
                        elapsed = now - last_time
                        if elapsed >= 0.5:
                            speed = (sent - last_sent) / elapsed / (1024 * 1024)
                            last_time = now
                            last_sent = sent
                            if speed_callback:
                                speed_callback(speed)

                logger.info(f"Sent: {rel_path} ✅")
                if progress_callback:
                    progress_callback(i + 1, total_files, rel_path)

            sock.close()
            if speed_callback:
                speed_callback(0)
            logger.info("=== SEND COMPLETE ===")
            if done_callback:
                done_callback(True, f"✅ Transfer complete! {total_files} files sent.")

        except ConnectionRefusedError:
            msg = "Connection refused — make sure the other device pressed 'Receive Files' first"
            logger.error(f"SEND FAILED: {msg}")
            if done_callback:
                done_callback(False, msg)
        except socket.timeout:
            msg = "Connection timed out — press 'Receive' on the other device first, then try Send."
            logger.error(f"SEND FAILED: {msg}")
            if done_callback:
                done_callback(False, msg)
        except ConnectionResetError:
            msg = "Connection reset — make sure the other device pressed 'Receive Files' BEFORE you press 'Send'."
            logger.error(f"SEND FAILED: {msg}")
            if done_callback:
                done_callback(False, msg)
        except Exception as e:
            msg = f"Unexpected error: {str(e)}"
            logger.error(f"SEND FAILED: {msg}", exc_info=True)
            if done_callback:
                done_callback(False, msg)

    threading.Thread(target=_send, daemon=True).start()


def start_receiver(save_path: str, progress_callback=None, done_callback=None, speed_callback=None):
    def _receive():
        logger.info(f"=== RECEIVE START ===")
        logger.info(f"Save path: {save_path}")
        logger.info(f"Listening on port {TRANSFER_PORT}...")
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", TRANSFER_PORT))
            server.listen(1)
            server.settimeout(120)
            logger.info(f"Waiting for connection on 0.0.0.0:{TRANSFER_PORT}")

            conn, addr = server.accept()
            logger.info(f"Connection from: {addr[0]}:{addr[1]}")
            server.close()

            total_files = struct.unpack(">I", _recv_exact(conn, 4))[0]
            logger.info(f"Total files to receive: {total_files}")

            for i in range(total_files):
                path_len = struct.unpack(">I", _recv_exact(conn, 4))[0]
                rel_path = _recv_exact(conn, path_len).decode("utf-8")
                file_size = struct.unpack(">Q", _recv_exact(conn, 8))[0]
                logger.info(f"Receiving [{i+1}/{total_files}]: {rel_path} ({file_size} bytes)")

                out_path = os.path.join(save_path, rel_path)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)

                received = 0
                last_time = time.time()
                last_received = 0

                with open(out_path, "wb") as f:
                    while received < file_size:
                        chunk = conn.recv(min(BUFFER_SIZE, file_size - received))
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)

                        now = time.time()
                        elapsed = now - last_time
                        if elapsed >= 0.5:
                            speed = (received - last_received) / elapsed / (1024 * 1024)
                            last_time = now
                            last_received = received
                            if speed_callback:
                                speed_callback(speed)

                logger.info(f"Received: {rel_path} ✅")
                if progress_callback:
                    progress_callback(i + 1, total_files, rel_path)

            conn.close()
            if speed_callback:
                speed_callback(0)
            logger.info("=== RECEIVE COMPLETE ===")
            if done_callback:
                done_callback(True, f"✅ Received {total_files} files\nSaved to: {save_path}")

        except socket.timeout:
            msg = "Timed out waiting for sender (120s). Try again."
            logger.error(f"RECEIVE FAILED: {msg}")
            if done_callback:
                done_callback(False, msg)
        except Exception as e:
            msg = f"Receive error: {str(e)}"
            logger.error(f"RECEIVE FAILED: {msg}", exc_info=True)
            if done_callback:
                done_callback(False, msg)

    threading.Thread(target=_receive, daemon=True).start()


def _recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed unexpectedly")
        data += chunk
    return data
