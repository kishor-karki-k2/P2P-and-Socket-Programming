import sys
import os
import base64
import textwrap

from PyQt5.QtCore import pyqtSignal, QThread, QTimer, Qt, QSettings, QSize
from PyQt5.QtGui import QIcon, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QMessageBox, QFileDialog, QProgressBar, QDockWidget,
    QListWidget, QToolBar, QAction, QStackedWidget, QLabel, QFormLayout, QInputDialog,
    QDialog, QDialogButtonBox, QComboBox
)

from network import PeerNetwork

# --------------------------------------------------------------------------
# Non-blocking File Transfer Thread
# --------------------------------------------------------------------------
class FileTransferThread(QThread):
    progress = pyqtSignal(int)

    def __init__(self, total_bytes):
        super().__init__()
        self.total_bytes = total_bytes

    def run(self):
        for i in range(101):
            self.progress.emit(i)
            self.msleep(20)

# --------------------------------------------------------------------------
# Preferences Dialog (stores default sending username)
# --------------------------------------------------------------------------
class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(300, 120)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        form_layout = QFormLayout()
        self.username_edit = QLineEdit()
        form_layout.addRow("Default Sending Username:", self.username_edit)
        self.layout.addLayout(form_layout)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

        # Load settings
        self.load_settings()

    def load_settings(self):
        settings = QSettings("MyCompany", "P2PChatApp")
        default_username = settings.value("defaultSendingUsername", "")
        self.username_edit.setText(default_username)

    def save_settings(self):
        settings = QSettings("MyCompany", "P2PChatApp")
        settings.setValue("defaultSendingUsername", self.username_edit.text())

    def accept(self):
        self.save_settings()
        super().accept()

# --------------------------------------------------------------------------
# Setup Widget: Collect two usernames and two ports
# --------------------------------------------------------------------------
class SetupWidget(QWidget):
    # Signal: (sendUser, sendPort, listenUser, listenPort)
    setupCompleted = pyqtSignal(str, int, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_default_sending_username()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)

        title = QLabel("P2P Chat Setup (Two Ports / Two Usernames)")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        form_layout = QFormLayout()
        form_layout.setSpacing(8)

        self.sending_username_edit = QLineEdit()
        form_layout.addRow("Sending Username:", self.sending_username_edit)

        self.sending_port_edit = QLineEdit()
        self.sending_port_edit.setPlaceholderText("e.g., 5000")
        form_layout.addRow("Sending Port:", self.sending_port_edit)

        self.listening_username_edit = QLineEdit()
        form_layout.addRow("Listening Username:", self.listening_username_edit)

        self.listening_port_edit = QLineEdit()
        self.listening_port_edit.setPlaceholderText("e.g., 5001")
        form_layout.addRow("Listening Port:", self.listening_port_edit)

        layout.addLayout(form_layout)

        self.start_button = QPushButton("Start Chat")
        self.start_button.clicked.connect(self.on_start)
        layout.addWidget(self.start_button)

        layout.addStretch()

    def load_default_sending_username(self):
        settings = QSettings("MyCompany", "P2PChatApp")
        default_username = settings.value("defaultSendingUsername", "")
        self.sending_username_edit.setText(default_username)

    def on_start(self):
        send_user = self.sending_username_edit.text().strip()
        send_port_str = self.sending_port_edit.text().strip()
        listen_user = self.listening_username_edit.text().strip()
        listen_port_str = self.listening_port_edit.text().strip()

        if not send_user or not listen_user:
            QMessageBox.warning(self, "Input Error", "Both usernames cannot be empty.")
            return

        if not (send_port_str.isdigit() and listen_port_str.isdigit()):
            QMessageBox.warning(self, "Input Error", "Ports must be positive integers.")
            return

        send_port = int(send_port_str)
        listen_port = int(listen_port_str)
        if send_port <= 0 or listen_port <= 0:
            QMessageBox.warning(self, "Input Error", "Ports must be greater than 0.")
            return

        self.setupCompleted.emit(send_user, send_port, listen_user, listen_port)

# --------------------------------------------------------------------------
# Chat Widget: Two networks: net_sending (user1/port1) & net_listening (user2/port2)
# --------------------------------------------------------------------------
class ChatWidget(QWidget):
    incomingMessage = pyqtSignal(object)

    def __init__(self, send_user, send_port, listen_user, listen_port, parent=None):
        super().__init__(parent)
        self.send_user = send_user
        self.send_port = send_port
        self.listen_user = listen_user
        self.listen_port = listen_port

        self.network_sending = None
        self.network_listening = None

        self.setup_ui()
        self.incomingMessage.connect(self.process_incoming_message)
        self.initialize_networks()

    def setup_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)
        self.setLayout(self.layout)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.layout.addWidget(self.chat_display)

        # Identity selection: pick which local user to send as
        identity_layout = QHBoxLayout()
        identity_layout.setSpacing(8)

        self.identity_combo = QComboBox()
        self.identity_combo.addItem(self.send_user)
        self.identity_combo.addItem(self.listen_user)
        identity_layout.addWidget(QLabel("Send As:"))
        identity_layout.addWidget(self.identity_combo)

        self.layout.addLayout(identity_layout)

        # Bottom input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        self.msg_entry = QLineEdit()
        self.msg_entry.setPlaceholderText("Type your message here...")
        self.msg_entry.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.msg_entry)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        self.layout.addLayout(input_layout)

        # Extra actions
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)

        self.group_button = QPushButton("Group Chat")
        self.group_button.clicked.connect(self.send_group_message)
        action_layout.addWidget(self.group_button)

        self.file_button = QPushButton("Send File")
        self.file_button.clicked.connect(self.send_file)
        action_layout.addWidget(self.file_button)

        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.clicked.connect(self.clear_chat)
        action_layout.addWidget(self.clear_button)

        self.layout.addLayout(action_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

    def initialize_networks(self):
        # net_sending
        self.network_sending = PeerNetwork(self.send_user, "0.0.0.0", self.send_port)
        self.network_sending.message_callback = self.handle_incoming_message
        self.network_sending.start_server()
        self.network_sending.broadcast_presence("online")

        # net_listening
        self.network_listening = PeerNetwork(self.listen_user, "0.0.0.0", self.listen_port)
        self.network_listening.message_callback = self.handle_incoming_message
        self.network_listening.start_server()
        self.network_listening.broadcast_presence("online")

        self.append_chat(f"[INFO] Sending Identity: '{self.send_user}' on port {self.send_port}.", msg_type="info")
        self.append_chat(f"[INFO] Listening Identity: '{self.listen_user}' on port {self.listen_port}.", msg_type="info")

    def handle_incoming_message(self, message):
        self.incomingMessage.emit(message)

    def process_incoming_message(self, msg):
        if isinstance(msg, dict):
            msg_type = msg.get("type")
            if msg_type == "file_transfer":
                self.process_file_transfer(msg)
            elif msg_type == "group_chat":
                sender = msg.get("sender")
                group = msg.get("group")
                content = msg.get("content")
                bubble_text = f"{sender} in [{group}]: {content}"
                self.append_chat(bubble_text, msg_type="group", sender=sender)
            else:
                self.append_chat(str(msg), msg_type="info")
        else:
            text = str(msg)
            if "[ERROR]" in text:
                self.append_chat(text, msg_type="error")
            elif "[INFO]" in text or "[WARN]" in text or "[PRESENCE]" in text:
                self.append_chat(text, msg_type="info")
            elif "[CHAT]" in text:
                try:
                    _, rest = text.split("] ", 1)
                    sender, content = rest.split(":", 1)
                    sender = sender.strip()
                    content = content.strip()
                    bubble_text = f"{sender}: {content}"
                    self.append_chat(bubble_text, msg_type="chat", sender=sender)
                except:
                    self.append_chat(text, msg_type="chat")
            else:
                self.append_chat(text, msg_type="chat")

    def process_file_transfer(self, msg):
        sender = msg.get("sender")
        filename = msg.get("filename")
        filesize = msg.get("filesize")
        filedata = msg.get("content")
        reply = QMessageBox.question(
            self, "File Transfer",
            f"Receive file '{filename}' ({filesize} bytes) from {sender}?\nSave file?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            save_path, _ = QFileDialog.getSaveFileName(self, "Save File", filename)
            if save_path:
                try:
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(filedata))
                    self.append_chat(f"Saved '{filename}' from {sender} to {save_path}.", msg_type="info")
                except Exception as e:
                    self.append_chat(f"[ERROR] Failed to save file: {e}", msg_type="error")
            else:
                self.append_chat(f"File '{filename}' not saved.", msg_type="info")
        else:
            self.append_chat(f"File '{filename}' from {sender} was rejected.", msg_type="info")

    def append_chat(self, text, msg_type="chat", sender=None):
        align = "left"
        bubble_color = "#E0F7FA"
        text_color = "#333333"

        if msg_type == "info":
            bubble_color = "#F5F5F5"
            text_color = "#666666"
        elif msg_type == "error":
            bubble_color = "#FCE4EC"
            text_color = "#C62828"
        elif msg_type == "group":
            bubble_color = "#E8F5E9"
            text_color = "#2E7D32"

        # If local user is the sender, align right
        if sender and (sender == self.send_user or sender == self.listen_user):
            align = "right"
            bubble_color = "#C8E6C9"

        bubble_html = textwrap.dedent(f"""
        <div style="
            background-color: {bubble_color};
            color: {text_color};
            border-radius: 8px;
            margin: 4px;
            padding: 6px 10px;
            max-width: 60%;
            text-align: left;
            float: {align};
            clear: both;
        ">
            {text}
        </div>
        <div style="clear: both;"></div>
        """)

        self.chat_display.insertHtml(bubble_html)
        self.chat_display.moveCursor(QTextCursor.End)
        self.chat_display.ensureCursorVisible()

    def get_all_peers(self):
        # Merge peers from both networks
        peers_sending = self.network_sending.list_peers()
        peers_listening = self.network_listening.list_peers()
        return sorted(set(peers_sending + peers_listening))

    def send_message(self):
        message = self.msg_entry.text().strip()
        if not message:
            return
        all_peers = self.get_all_peers()
        if not all_peers:
            QMessageBox.warning(self, "Warning", "No connected peer available. Please connect first.")
            return

        if len(all_peers) == 1:
            recipient = all_peers[0]
        else:
            recipient, ok = QInputDialog.getItem(self, "Select Recipient", "Select a recipient:", all_peers, 0, False)
            if not ok or not recipient:
                QMessageBox.information(self, "Info", "Recipient required.")
                return

        # Decide which identity to send as:
        chosen_identity = self.identity_combo.currentText()
        if chosen_identity == self.send_user:
            net = self.network_sending
        else:
            net = self.network_listening

        net.send_chat_message(recipient, message)
        self.append_chat(f"{chosen_identity}: {message}", msg_type="chat", sender=chosen_identity)
        self.msg_entry.clear()

    def send_group_message(self):
        message = self.msg_entry.text().strip()
        if not message:
            return
        group, ok = QInputDialog.getText(self, "Group Chat", "Enter group name:")
        if not ok or not group:
            QMessageBox.warning(self, "Warning", "Group name required.")
            return
        chosen_identity = self.identity_combo.currentText()
        group_msg = {
            "type": "group_chat",
            "sender": chosen_identity,
            "group": group,
            "content": message
        }
        all_peers = self.get_all_peers()
        for peer in all_peers:
            if chosen_identity == self.send_user:
                self.network_sending.send_chat_message(peer, group_msg, is_dict=True)
            else:
                self.network_listening.send_chat_message(peer, group_msg, is_dict=True)

        self.append_chat(f"{chosen_identity} in [{group}]: {message}", msg_type="group", sender=chosen_identity)
        self.msg_entry.clear()

    def send_file(self):
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

        all_peers = self.get_all_peers()
        if not all_peers:
            QMessageBox.warning(self, "Warning", "No connected peer available.")
            return

        if len(all_peers) == 1:
            recipient = all_peers[0]
        else:
            recipient, ok = QInputDialog.getItem(self, "Select Recipient", "Select a recipient:", all_peers, 0, False)
            if not ok or not recipient:
                QMessageBox.information(self, "Info", "Recipient required.")
                return

        chosen_identity = self.identity_combo.currentText()
        file_msg = {
            "type": "file_transfer",
            "sender": chosen_identity,
            "recipient": recipient,
            "filename": filename,
            "filesize": filesize,
            "content": encoded_data
        }

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.file_thread = FileTransferThread(filesize)
        self.file_thread.progress.connect(self.progress_bar.setValue)
        self.file_thread.finished.connect(lambda: self.on_file_transfer_complete(chosen_identity, recipient, filename, filesize, file_msg))
        self.file_thread.start()

    def on_file_transfer_complete(self, chosen_identity, recipient, filename, filesize, file_msg):
        if chosen_identity == self.send_user:
            self.network_sending.send_chat_message(recipient, file_msg, is_dict=True)
        else:
            self.network_listening.send_chat_message(recipient, file_msg, is_dict=True)

        self.append_chat(f"Sent '{filename}' ({filesize} bytes) to {recipient}.", msg_type="info")
        self.progress_bar.setVisible(False)

    def clear_chat(self):
        self.chat_display.clear()

    def connect_to_peer(self):
        # We'll always connect from net_sending to remain consistent with original design
        # but you could also pick which identity to connect from if you like.
        if not self.network_sending:
            QMessageBox.warning(self, "Error", "Sending network not initialized.")
            return
        ip, ok = QInputDialog.getText(self, "Connect to Peer", "Enter peer IP address:")
        if not ok or not ip:
            return
        port, ok = QInputDialog.getInt(self, "Connect to Peer", "Enter peer port:")
        if not ok or port <= 0:
            return
        self.network_sending.connect_to_peer(ip, port)
        self.append_chat(f"[INFO] Attempting to connect to {ip}:{port}...", msg_type="info")

    def shutdown_networks(self):
        if self.network_sending:
            self.network_sending.broadcast_presence("offline")
            self.network_sending.shutdown()
        if self.network_listening:
            self.network_listening.broadcast_presence("offline")
            self.network_listening.shutdown()

# --------------------------------------------------------------------------
# Main Window
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("P2P Chat Application ")
        self.resize(900, 650)
        self.setup_ui()

    def setup_ui(self):
        self.create_menu_bar()
        self.create_tool_bar()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.setup_widget = SetupWidget(self)
        self.setup_widget.setupCompleted.connect(self.on_setup_completed)
        self.stack.addWidget(self.setup_widget)

        self.chat_widget = None

        # Dock widget for connected peers
        self.peer_dock = QDockWidget("Connected Peers", self)
        self.peer_list_widget = QListWidget()
        self.peer_dock.setWidget(self.peer_list_widget)
        self.peer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self.peer_dock)

        # Status label & indicator
        self.status_label = QLabel("No peers connected")
        self.status_indicator = QLabel("●")  # We'll color this circle
        self.status_indicator.setStyleSheet("color: red; font-size: 14px;")
        self.statusBar().addPermanentWidget(self.status_indicator)
        self.statusBar().addPermanentWidget(self.status_label)
        self.statusBar().showMessage("Enter two usernames and two ports to start.")

        # Timer to periodically update peer list & status
        self.peer_timer = QTimer(self)
        self.peer_timer.timeout.connect(self.update_peer_list)
        self.peer_timer.start(3000)

    def create_menu_bar(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self.connect_action = QAction("Connect", self)
        self.connect_action.triggered.connect(self.connect_peer)
        file_menu.addAction(self.connect_action)

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.exit_app)
        file_menu.addAction(self.exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        self.prefs_action = QAction("Preferences", self)
        self.prefs_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(self.prefs_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_tool_bar(self):
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)  # Show text beside icon
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Example icons (replace with your own icon paths if you want icons)
        connect_icon = QIcon("connect_icon.png")
        exit_icon = QIcon("exit_icon.png")
        pref_icon = QIcon("settings_icon.png")

        # Connect action (Green)
        self.connect_action.setIcon(connect_icon)
        self.connect_action.setText("Connect")
        connect_btn = toolbar.addAction(self.connect_action)
        toolbar_widget_connect = toolbar.widgetForAction(self.connect_action)
        toolbar_widget_connect.setObjectName("connectButton")

        # Preferences action (Blue)
        self.prefs_action.setIcon(pref_icon)
        self.prefs_action.setText("Preferences")
        prefs_btn = toolbar.addAction(self.prefs_action)
        toolbar_widget_prefs = toolbar.widgetForAction(self.prefs_action)
        toolbar_widget_prefs.setObjectName("prefsButton")

        # Exit action (Red)
        self.exit_action.setIcon(exit_icon)
        self.exit_action.setText("Exit")
        exit_btn = toolbar.addAction(self.exit_action)
        toolbar_widget_exit = toolbar.widgetForAction(self.exit_action)
        toolbar_widget_exit.setObjectName("exitButton")

    def on_setup_completed(self, send_user, send_port, listen_user, listen_port):
        self.chat_widget = ChatWidget(send_user, send_port, listen_user, listen_port, self)
        self.stack.addWidget(self.chat_widget)
        self.stack.setCurrentWidget(self.chat_widget)
        self.statusBar().showMessage(
            f"Chat started with sending user '{send_user}' on port {send_port}, "
            f"listening user '{listen_user}' on port {listen_port}."
        )

    def connect_peer(self):
        if self.chat_widget:
            self.chat_widget.connect_to_peer()

    def update_peer_list(self):
        if self.chat_widget:
            all_peers = self.chat_widget.get_all_peers()
            self.peer_list_widget.clear()
            self.peer_list_widget.addItems(all_peers)

            count = len(all_peers)
            if count > 0:
                self.status_indicator.setStyleSheet("color: green; font-size: 14px;")
                self.status_label.setText(f"{count} peer(s) connected")
            else:
                self.status_indicator.setStyleSheet("color: red; font-size: 14px;")
                self.status_label.setText("No peers connected")

    def show_preferences(self):
        dialog = PreferencesDialog(self)
        dialog.exec_()

    def exit_app(self):
        if self.chat_widget:
            if len(self.chat_widget.get_all_peers()) > 0:
                reply = QMessageBox.question(
                    self,
                    "Confirm Exit",
                    "You have active connections. Are you sure you want to exit?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            self.chat_widget.shutdown_networks()
        self.close()

    def show_about(self):
        QMessageBox.information(
            self, "About",
            "P2P Chat Application with Two Different Usernames & Ports\n"
            "Connect=Green, Preferences=Blue, Exit=Red.\n"
            "Now you can pick which local identity to send from."
        )

    def closeEvent(self, event):
        if self.chat_widget and len(self.chat_widget.get_all_peers()) > 0:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "You have active connections. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self.chat_widget.shutdown_networks()
        super().closeEvent(event)

# --------------------------------------------------------------------------
# Entry Point
# --------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Light theme QSS with forced button colors
    light_qss = """
    QMainWindow {
        background-color: #F0F0F0;
        color: #333333;
    }
    QWidget {
        background-color: #F8F8F8;
        color: #333333;
        font-size: 14px;
    }
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #FFFFFF !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
        color: #333333 !important;
        padding: 4px !important;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid #4CAF50 !important;
    }
    QPushButton {
        background-color: #E0E0E0 !important;
        color: #333333 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
        padding: 6px 12px !important;
    }
    QPushButton:hover {
        background-color: #D0D0D0 !important;
    }
    QPushButton:pressed {
        background-color: #C0C0C0 !important;
    }
    QToolBar {
        background-color: #E0E0E0 !important;
        border: 1px solid #CCCCCC !important;
    }
    QToolBar QToolButton {
        margin: 2px;
        padding: 6px 10px;
        border-radius: 4px;
    }
    QToolButton#connectButton {
        background-color: #4CAF50 !important; /* green */
        color: #FFFFFF !important;
    }
    QToolButton#prefsButton {
        background-color: #2196F3 !important; /* blue */
        color: #FFFFFF !important;
    }
    QToolButton#exitButton {
        background-color: #F44336 !important; /* red */
        color: #FFFFFF !important;
    }
    QProgressBar {
        background-color: #E0E0E0 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
        text-align: center !important;
        color: #333333 !important;
    }
    QProgressBar::chunk {
        background-color: #4CAF50 !important;
    }
    QDockWidget {
        background-color: #F8F8F8 !important;
    }
    QDockWidget::title {
        background-color: #E0E0E0 !important;
        padding: 4px !important;
        font-weight: bold !important;
        color: #333333 !important;
    }
    QListWidget {
        background-color: #FFFFFF !important;
        color: #333333 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
    }
    QTabWidget::pane {
        border: 1px solid #CCCCCC !important;
        background: #F8F8F8 !important;
    }
    QTabBar::tab {
        background: #E0E0E0 !important;
        color: #333333 !important;
        padding: 6px 12px !important;
        border-top-left-radius: 4px !important;
        border-top-right-radius: 4px !important;
        margin: 2px !important;
    }
    QTabBar::tab:selected {
        background: #4CAF50 !important;
        color: #FFFFFF !important;
    }
    QMenuBar {
        background-color: #E0E0E0 !important;
        color: #333333 !important;
    }
    QMenuBar::item {
        background-color: #E0E0E0 !important;
        padding: 4px 8px !important;
    }
    QMenuBar::item:selected {
        background-color: #D0D0D0 !important;
    }
    QMenu {
        background-color: #FFFFFF !important;
        color: #333333 !important;
        margin: 2px !important;
        border: 1px solid #CCCCCC !important;
    }
    QMenu::item:selected {
        background-color: #F0F0F0 !important;
    }
    """

    app.setStyleSheet(light_qss)
    app.setOrganizationName("MyCompany")
    app.setApplicationName("P2PChatApp")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
