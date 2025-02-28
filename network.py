import socket
import threading
from message import encode_message, decode_message

class PeerNetwork:
    def __init__(self, username, host, port):
        self.username = username
        self.host = host
        self.port = port
        self.server_socket = None
        self.connections = {}  # mapping: username -> socket
        self.lock = threading.Lock()
        self.running = True
        self.message_callback = None

    def start_server(self):
        """Start the server socket to listen for incoming connections."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"[INFO] Server listening on {self.host}:{self.port}")

        # Start a thread to accept incoming connections
        threading.Thread(target=self.accept_connections, daemon=True).start()

    def accept_connections(self):
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                print(f"[INFO] Accepted connection from {addr}")
                threading.Thread(target=self.handle_connection, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Accepting connection: {e}")

    def handle_connection(self, conn, addr):
        buffer = b""
        try:
            # Wait for introduction message.
            while b'\n' not in buffer:
                data = conn.recv(4096)
                if not data:
                    conn.close()
                    return
                buffer += data

            line, buffer = buffer.split(b'\n', 1)
            message = decode_message(line)
            if message and message.get("type") == "introduce":
                peer_username = message.get("username")
                print(f"[INFO] Connection request from {peer_username} at {addr}")
                accepted = True
                if hasattr(self, "connection_request_callback") and self.connection_request_callback:
                    accepted = self.connection_request_callback(peer_username, addr)
                if accepted:
                    print(f"[INFO] Connection accepted from {peer_username} at {addr}")
                    introduce_msg = {"type": "introduce", "username": self.username}
                    conn.sendall(encode_message(introduce_msg) + b'\n')
                    with self.lock:
                        self.connections[peer_username] = conn
                    while self.running:
                        data = conn.recv(4096)
                        if not data:
                            print(f"[INFO] Connection closed by {peer_username}")
                            break
                        buffer += data
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            self.process_message(line, peer_username)
                else:
                    print(f"[INFO] Connection rejected from {peer_username} at {addr}")
                    conn.close()
                    return
            else:
                print(f"[WARN] Did not receive valid introduction from {addr}. Closing connection.")
        except Exception as e:
            print(f"[ERROR] Handling connection from {addr}: {e}")
        finally:
            conn.close()
            with self.lock:
                to_remove = None
                for user, sock in self.connections.items():
                    if sock == conn:
                        to_remove = user
                        break
                if to_remove:
                    del self.connections[to_remove]

    def connect_to_peer(self, peer_host, peer_port):
        """Initiate connection to a peer given host and port."""
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect((peer_host, peer_port))
            introduce_msg = {"type": "introduce", "username": self.username}
            conn.sendall(encode_message(introduce_msg) + b'\n')

            data = b""
            while b'\n' not in data:
                part = conn.recv(4096)
                if not part:
                    break
                data += part
            if data:
                line, _ = data.split(b'\n', 1)
                message = decode_message(line)
                if message and message.get("type") == "introduce":
                    peer_username = message.get("username")
                    print(f"[INFO] Connected to peer: {peer_username} at {peer_host}:{peer_port}")
                    with self.lock:
                        self.connections[peer_username] = conn
                    threading.Thread(target=self.listen_to_peer, args=(conn, peer_username), daemon=True).start()
                else:
                    print("[ERROR] Did not receive valid introduction from peer.")
                    conn.close()
            else:
                print("[ERROR] No data received for introduction.")
                conn.close()
        except ConnectionRefusedError:
            print(f"[ERROR] Connecting to peer {peer_host}:{peer_port} - Connection refused.")
        except Exception as e:
            print(f"[ERROR] Connecting to peer {peer_host}:{peer_port} - {e}")

    def listen_to_peer(self, conn, peer_username):
        buffer = b""
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    print(f"[INFO] Connection closed by {peer_username}")
                    break
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    self.process_message(line, peer_username)
        except Exception as e:
            print(f"[ERROR] Listening to peer {peer_username}: {e}")
        finally:
            conn.close()
            with self.lock:
                if peer_username in self.connections:
                    del self.connections[peer_username]

    def process_message(self, data, peer_username):
        message = decode_message(data)
        if not message:
            output = "[WARN] Received invalid message."
        else:
            msg_type = message.get("type")
            if msg_type == "chat":
                sender = message.get("sender")
                content = message.get("content")
                output = f"[CHAT] {sender}: {content}"
            elif msg_type == "presence":
                sender = message.get("sender")
                status = message.get("status")
                output = f"[PRESENCE] {sender} is now {status}."
            else:
                # For file_transfer, group_chat, etc., pass the raw dict
                output = message
        if self.message_callback:
            self.message_callback(output)
        else:
            print(output)

    def send_chat_message(self, recipient_username, content, msg_type="chat", extra_fields=None, is_dict=False):
        with self.lock:
            conn = self.connections.get(recipient_username)
        if not conn:
            print(f"[ERROR] No connection found for {recipient_username}")
            return
        if is_dict:
            chat_msg = content
        else:
            chat_msg = {
                "type": msg_type,
                "sender": self.username,
                "recipient": recipient_username,
                "content": content
            }
            if extra_fields:
                chat_msg.update(extra_fields)
        try:
            conn.sendall(encode_message(chat_msg) + b'\n')
        except Exception as e:
            print(f"[ERROR] Sending chat message to {recipient_username}: {e}")

    def list_peers(self):
        with self.lock:
            return list(self.connections.keys())

    def broadcast_presence(self, status):
        presence_msg = {
            "type": "presence",
            "sender": self.username,
            "status": status
        }
        with self.lock:
            for peer_username, conn in self.connections.items():
                try:
                    conn.sendall(encode_message(presence_msg) + b'\n')
                except Exception as e:
                    print(f"[ERROR] Broadcasting to {peer_username}: {e}")

    def shutdown(self):
        self.running = False
        self.broadcast_presence("offline")
        with self.lock:
            for peer_username, conn in self.connections.items():
                try:
                    conn.close()
                except Exception as e:
                    print(f"[ERROR] Closing connection to {peer_username}: {e}")
            self.connections.clear()
        if self.server_socket:
            self.server_socket.close()
        print("[INFO] Network shutdown complete.")
