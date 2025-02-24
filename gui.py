import sys
import os
import base64
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton,
    QMessageBox, QInputDialog, QFileDialog
)
from PyQt5.QtCore import pyqtSignal
from network import PeerNetwork  # Ensure your updated network.py is in the same directory

# Import qt_material to apply a Material Design theme.
from qt_material import apply_stylesheet

class P2PChatWindow(QMainWindow):
    # Signal to carry incoming messages (string or dict)
    incomingMessage = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("P2P Chat")
        # We remove our own manual stylesheet so that qt_material styling takes over.
        # You can add minimal customizations later if needed.
        # self.setStyleSheet("")

        self.network = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout()
        central_widget.setLayout(self.main_layout)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.main_layout.addWidget(self.chat_display)

        # Message entry and Send button
        msg_layout = QHBoxLayout()
        self.msg_entry = QLineEdit()
        self.msg_entry.returnPressed.connect(self.send_message)
        msg_layout.addWidget(self.msg_entry)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        msg_layout.addWidget(self.send_button)
        self.main_layout.addLayout(msg_layout)

        # Extra features: Group Chat and File Transfer
        extra_btn_layout = QHBoxLayout()
        self.group_button = QPushButton("Group Chat")
        self.group_button.clicked.connect(self.send_group_message)
        extra_btn_layout.addWidget(self.group_button)
        self.file_button = QPushButton("Send File")
        self.file_button.clicked.connect(self.send_file)
        extra_btn_layout.addWidget(self.file_button)
        self.main_layout.addLayout(extra_btn_layout)

        # Bottom buttons: Connect, List Peers, Exit
        bottom_layout = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_to_peer)
        bottom_layout.addWidget(self.connect_button)
        self.list_button = QPushButton("List Peers")
        self.list_button.clicked.connect(self.list_peers)
        bottom_layout.addWidget(self.list_button)
        self.exit_button = QPushButton("Exit")
        self.exit_button.clicked.connect(self.exit_app)
        bottom_layout.addWidget(self.exit_button)
        self.main_layout.addLayout(bottom_layout)

        # Connect incoming message signal to our handler.
        self.incomingMessage.connect(self.process_incoming_message)

        self.initialize_network()

    def initialize_network(self):
        username, ok = QInputDialog.getText(self, "Username", "Enter your username:")
        if not ok or not username:
            QMessageBox.warning(self, "Error", "Username cannot be empty.")
            self.close()
            return
        self.setWindowTitle(username)
        port, ok = QInputDialog.getInt(self, "Port", "Enter port to listen on:")
        if not ok or port <= 0:
            QMessageBox.warning(self, "Error", "Invalid port number.")
            self.close()
            return
        self.network = PeerNetwork(username, "0.0.0.0", port)
        # Set our message callback so that messages from the network are handled here.
        self.network.message_callback = self.handle_incoming_message
        self.network.start_server()
        self.network.broadcast_presence("online")
        self.append_chat(f"[INFO] Started chat as '{username}' on port {port}.")

    def handle_incoming_message(self, message):
        # message can be a string or a dict
        self.incomingMessage.emit(message)

    def process_incoming_message(self, msg):
        # Process file transfer messages, group chat messages, or direct messages.
        if isinstance(msg, dict):
            if msg.get("type") == "file_transfer":
                sender = msg.get("sender")
                filename = msg.get("filename")
                filesize = msg.get("filesize")
                filedata = msg.get("content")
                reply = QMessageBox.question(
                    self,
                    "File Transfer",
                    f"Receive file '{filename}' ({filesize} bytes) from {sender}?\nSave file?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    save_path, _ = QFileDialog.getSaveFileName(self, "Save File", filename)
                    if save_path:
                        try:
                            with open(save_path, "wb") as f:
                                f.write(base64.b64decode(filedata))
                            self.append_chat(f"[FILE] Saved '{filename}' from {sender} to {save_path}.")
                        except Exception as e:
                            self.append_chat(f"[ERROR] Failed to save file: {e}")
                    else:
                        self.append_chat(f"[FILE] File '{filename}' not saved.")
                else:
                    self.append_chat(f"[FILE] File '{filename}' from {sender} was rejected.")
            elif msg.get("type") == "group_chat":
                sender = msg.get("sender")
                group = msg.get("group")
                content = msg.get("content")
                self.append_chat(f"[GROUP:{group}] {sender}: {content}")
            else:
                self.append_chat(str(msg))
        else:
            self.append_chat(msg)

    def append_chat(self, text):
        self.chat_display.append(text)

    def send_message(self):
        # Direct message sending
        message = self.msg_entry.text().strip()
        if not message:
            return
        peers = self.network.list_peers()
        if len(peers) == 0:
            QMessageBox.warning(self, "Warning", "No connected peer available. Please connect first.")
            return
        elif len(peers) == 1:
            recipient = peers[0]
        else:
            recipient, ok = QInputDialog.getItem(self, "Select Recipient", "Select a recipient:", peers, 0, False)
            if not ok or not recipient:
                QMessageBox.information(self, "Info", "Recipient required.")
                return
        self.network.send_chat_message(recipient, message)
        self.append_chat(f"[ME -> {recipient}]: {message}")
        self.msg_entry.clear()

    def send_group_message(self):
        # Group chat message sending
        message = self.msg_entry.text().strip()
        if not message:
            return
        group, ok = QInputDialog.getText(self, "Group Chat", "Enter group name:")
        if not ok or not group:
            QMessageBox.warning(self, "Warning", "Group name required.")
            return
        group_msg = {
            "type": "group_chat",
            "sender": self.network.username,
            "group": group,
            "content": message
        }
        for recipient in self.network.list_peers():
            self.network.send_chat_message(recipient, group_msg, is_dict=True)
        self.append_chat(f"[GROUP:{group}] {self.network.username}: {message}")
        self.msg_entry.clear()

    def send_file(self):
        # File transfer functionality
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File to Send")
        if not file_path:
            return
        try:
            with open(file_path, "rb") as f:
                file_data = f.read()
            encoded_data = base64.b64encode(file_data).decode("utf-8")
            filename = os.path.basename(file_path)
            filesize = len(file_data)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to read file: {e}")
            return

        peers = self.network.list_peers()
        if len(peers) == 0:
            QMessageBox.warning(self, "Warning", "No connected peer available.")
            return
        elif len(peers) == 1:
            recipient = peers[0]
        else:
            recipient, ok = QInputDialog.getItem(self, "Select Recipient", "Select a recipient:", peers, 0, False)
            if not ok or not recipient:
                QMessageBox.information(self, "Info", "Recipient required.")
                return

        file_msg = {
            "type": "file_transfer",
            "sender": self.network.username,
            "recipient": recipient,
            "filename": filename,
            "filesize": filesize,
            "content": encoded_data
        }
        self.network.send_chat_message(recipient, file_msg, is_dict=True)
        self.append_chat(f"[FILE] Sent '{filename}' ({filesize} bytes) to {recipient}.")

    def connect_to_peer(self):
        ip, ok = QInputDialog.getText(self, "Connect to Peer", "Enter peer IP address:")
        if not ok or not ip:
            return
        port, ok = QInputDialog.getInt(self, "Connect to Peer", "Enter peer port:")
        if not ok or port <= 0:
            return
        self.network.connect_to_peer(ip, port)
        self.append_chat(f"[INFO] Attempting to connect to {ip}:{port}...")

    def list_peers(self):
        peers = self.network.list_peers()
        peers_str = "\n".join(peers) if peers else "No peers connected."
        QMessageBox.information(self, "Connected Peers", peers_str)

    def exit_app(self):
        if self.network:
            self.network.shutdown()
        self.close()


def main():
    app = QApplication(sys.argv)
    # Apply the Material Design stylesheet from qt-material.
    # Here, we use the 'light_green.xml' theme for a green accent.
    apply_stylesheet(app, theme='light_green.xml')
    # Create two chat windows (or more as needed)
    window1 = P2PChatWindow()
    window2 = P2PChatWindow()
    window1.show()
    window2.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
