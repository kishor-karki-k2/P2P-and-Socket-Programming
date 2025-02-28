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
    QDialog, QDialogButtonBox, QComboBox, QGraphicsDropShadowEffect
)

from network import PeerNetwork

# ------------------- FileTransferThread -------------------
class FileTransferThread(QThread):
    progress = pyqtSignal(int)
    def __init__(self, total_bytes):
        super().__init__()
        self.total_bytes = total_bytes
    def run(self):
        for i in range(101):
            self.progress.emit(i)
            self.msleep(20)

# ------------------- PreferencesDialog -------------------
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

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

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

# ------------------- SetupWidget -------------------
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

# ------------------- ChatPanel -------------------
class ChatPanel(QWidget):
    def __init__(self, identity, network=None, parent=None):
        super().__init__(parent)
        self.identity = identity
        self.network = network

        # We name this panel "chatPanel" for QSS styling
        self.setObjectName("chatPanel")

        self.setup_ui()
        self.apply_teal_panel()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        title_label = QLabel(f"Chat Panel - {self.identity}")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)

        # Horizontal layout for message entry + Send
        input_layout = QHBoxLayout()

        self.msg_entry = QLineEdit()
        self.msg_entry.setPlaceholderText("Type your message here...")
        self.msg_entry.setObjectName("msgEntry")  # For QSS styling
        self.msg_entry.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.msg_entry)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendBtn")  # For QSS styling => green
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)

        layout.addLayout(input_layout)

        # Another row for "Send File" (orange) + "Clear Chat" (red)
        actions_layout = QHBoxLayout()

        self.send_file_button = QPushButton("Send File")
        self.send_file_button.setObjectName("fileBtn")  # For QSS => orange
        self.send_file_button.clicked.connect(self.send_file)
        actions_layout.addWidget(self.send_file_button)

        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.setObjectName("clearBtn")  # For QSS => red
        self.clear_button.clicked.connect(self.clear_chat)
        actions_layout.addWidget(self.clear_button)

        layout.addLayout(actions_layout)

        # Progress bar for file transfers
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def apply_teal_panel(self):
        """
        Teal background for the chat panel, with rounded corners.
        """
        self.setStyleSheet("""
            border-radius: 10px;
        """)
        # Drop shadow effect for a raised look
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setOffset(5, 5)
        shadow.setColor(Qt.gray)
        self.setGraphicsEffect(shadow)

    def append_message(self, text, msg_type="chat", sender=None):
        align = "left"
        bubble_color = "orange"
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

        # If the message is from the local identity, align right
        if sender and sender == self.identity:
            align = "right"
            bubble_color = "green"

        bubble_html = textwrap.dedent(f"""
        <div style="
            background-color: {bubble_color};
            color: {text_color};
            border-radius: 10px;
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

    def send_message(self):
        message = self.msg_entry.text().strip()
        if not message:
            return
        if self.network is None:
            QMessageBox.warning(self, "Error", "Network not initialized.")
            return
        all_peers = self.network.list_peers()
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
        self.network.send_chat_message(recipient, message)
        self.append_message(f"{self.identity}: {message}", msg_type="chat", sender=self.identity)
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
        all_peers = self.network.list_peers()
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
        file_msg = {
            "type": "file_transfer",
            "sender": self.identity,
            "recipient": recipient,
            "filename": filename,
            "filesize": filesize,
            "content": encoded_data
        }
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.file_thread = FileTransferThread(filesize)
        self.file_thread.progress.connect(self.progress_bar.setValue)
        self.file_thread.finished.connect(lambda: self.on_file_transfer_complete(recipient, filename, filesize, file_msg))
        self.file_thread.start()

    def on_file_transfer_complete(self, recipient, filename, filesize, file_msg):
        self.network.send_chat_message(recipient, file_msg, is_dict=True)
        self.append_message(f"Sent '{filename}' ({filesize} bytes) to {recipient}.", msg_type="info")
        self.progress_bar.setVisible(False)

    def clear_chat(self):
        self.chat_display.clear()

# ------------------- ChatWidget -------------------
class ChatWidget(QWidget):
    def __init__(self, send_user, send_port, listen_user, listen_port, parent=None):
        super().__init__(parent)
        self.send_user = send_user
        self.send_port = send_port
        self.listen_user = listen_user
        self.listen_port = listen_port
        self.network_sending = None
        self.network_listening = None
        self.setup_ui()
        self.initialize_networks()

    def setup_ui(self):
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Horizontal layout for two chat panels
        panels_layout = QHBoxLayout()
        self.sender_panel = ChatPanel(self.send_user)
        self.receiver_panel = ChatPanel(self.listen_user)
        panels_layout.addWidget(self.sender_panel)
        panels_layout.addWidget(self.receiver_panel)
        self.layout.addLayout(panels_layout)

        # Extra action: Connect to Peer button
        actions_layout = QHBoxLayout()
        self.connect_button = QPushButton("Connect to Peer")
        self.connect_button.clicked.connect(self.connect_to_peer)
        actions_layout.addWidget(self.connect_button)
        self.layout.addLayout(actions_layout)

    def initialize_networks(self):
        self.network_sending = PeerNetwork(self.send_user, "0.0.0.0", self.send_port)
        self.network_sending.message_callback = lambda msg: self.process_incoming_message(msg, "sender")
        self.network_sending.start_server()
        self.network_sending.broadcast_presence("online")

        self.network_listening = PeerNetwork(self.listen_user, "0.0.0.0", self.listen_port)
        self.network_listening.message_callback = lambda msg: self.process_incoming_message(msg, "receiver")
        self.network_listening.start_server()
        self.network_listening.broadcast_presence("online")

        self.sender_panel.network = self.network_sending
        self.receiver_panel.network = self.network_listening

        self.sender_panel.append_message(f"[INFO] Chat panel for '{self.send_user}' on port {self.send_port} started.", msg_type="info")
        self.receiver_panel.append_message(f"[INFO] Chat panel for '{self.listen_user}' on port {self.listen_port} started.", msg_type="info")

    def process_incoming_message(self, msg, panel_type):
        panel = self.sender_panel if panel_type == "sender" else self.receiver_panel
        if isinstance(msg, dict):
            msg_type = msg.get("type")
            if msg_type == "file_transfer":
                panel.append_message(f"[File Transfer] Received: {msg}", msg_type="info")
            elif msg_type == "group_chat":
                sender = msg.get("sender")
                group = msg.get("group")
                content = msg.get("content")
                bubble_text = f"{sender} in [{group}]: {content}"
                panel.append_message(bubble_text, msg_type="group", sender=sender)
            else:
                panel.append_message(str(msg), msg_type="info")
        else:
            text = str(msg)
            if "[ERROR]" in text:
                panel.append_message(text, msg_type="error")
            elif "[INFO]" in text or "[WARN]" in text or "[PRESENCE]" in text:
                panel.append_message(text, msg_type="info")
            elif "[CHAT]" in text:
                try:
                    _, rest = text.split("] ", 1)
                    sender, content = rest.split(":", 1)
                    sender = sender.strip()
                    content = content.strip()
                    bubble_text = f"{sender}: {content}"
                    panel.append_message(bubble_text, msg_type="chat", sender=sender)
                except:
                    panel.append_message(text, msg_type="chat")
            else:
                panel.append_message(text, msg_type="chat")

    def connect_to_peer(self):
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
        self.sender_panel.append_message(f"[INFO] Attempting to connect to {ip}:{port}...", msg_type="info")

    def shutdown_networks(self):
        if self.network_sending:
            self.network_sending.broadcast_presence("offline")
            self.network_sending.shutdown()
        if self.network_listening:
            self.network_listening.broadcast_presence("offline")
            self.network_listening.shutdown()

# ------------------- MainWindow -------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("P2P Chat Application")
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

        self.peer_dock = QDockWidget("Connected Peers", self)
        self.peer_list_widget = QListWidget()
        self.peer_dock.setWidget(self.peer_list_widget)
        self.peer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self.peer_dock)

        self.status_label = QLabel("No peers connected")
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: red; font-size: 14px;")
        self.statusBar().addPermanentWidget(self.status_indicator)
        self.statusBar().addPermanentWidget(self.status_label)
        self.statusBar().showMessage("Enter two usernames and two ports to start.")

        self.peer_timer = QTimer(self)
        self.peer_timer.timeout.connect(self.update_peer_list)
        self.peer_timer.start(3000)

    def create_menu_bar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        self.connect_action = QAction("Connect", self)
        self.connect_action.triggered.connect(self.connect_peer)
        file_menu.addAction(self.connect_action)
        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.exit_app)
        file_menu.addAction(self.exit_action)
        edit_menu = menubar.addMenu("&Edit")
        self.prefs_action = QAction("Preferences", self)
        self.prefs_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(self.prefs_action)
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_tool_bar(self):
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        connect_icon = QIcon("connect_icon.png")
        exit_icon = QIcon("exit_icon.png")
        pref_icon = QIcon("settings_icon.png")

        self.connect_action.setIcon(connect_icon)
        self.connect_action.setText("Connect")
        toolbar.addAction(self.connect_action)

        self.prefs_action.setIcon(pref_icon)
        self.prefs_action.setText("Preferences")
        toolbar.addAction(self.prefs_action)

        self.exit_action.setIcon(exit_icon)
        self.exit_action.setText("Exit")
        toolbar.addAction(self.exit_action)

        connect_widget = toolbar.widgetForAction(self.connect_action)
        if connect_widget:
            connect_widget.setObjectName("connectButton")
        prefs_widget = toolbar.widgetForAction(self.prefs_action)
        if prefs_widget:
            prefs_widget.setObjectName("prefsButton")
        exit_widget = toolbar.widgetForAction(self.exit_action)
        if exit_widget:
            exit_widget.setObjectName("exitButton")

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
            peers_sending = self.chat_widget.network_sending.list_peers() if self.chat_widget.network_sending else []
            peers_listening = self.chat_widget.network_listening.list_peers() if self.chat_widget.network_listening else []
            all_peers = sorted(set(peers_sending + peers_listening))
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
            if (len(self.chat_widget.network_sending.list_peers()) > 0 or
                len(self.chat_widget.network_listening.list_peers()) > 0):
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
            "P2P Chat Application with a teal ChatPanel background.\n"
            "Send=Green, Send File=Orange, Clear Chat=Red, each with a contrasting border.\n"
            "Message typing box is white with a rounded border.\n"
            "All previous teal overshadow issues are resolved."
        )

    def closeEvent(self, event):
        if self.chat_widget and (len(self.chat_widget.network_sending.list_peers()) > 0 or
                                 len(self.chat_widget.network_listening.list_peers()) > 0):
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

# ------------------- main() -------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # QSS with teal panel, green/orange/red buttons, white message box, etc.
    custom_qss = """
    /* Global Window & Basic Widgets */
    QMainWindow {
        background-color: #F0F0F0;
        color: #333333;
    }
    QWidget {
        background-color: white;
        color: #333333;
        font-size: 14px;
    }
    QPushButton {
    background-color: #00b241 !important;
        color: #FFFFFF !important;
        border: 2px solid #ffffff !important; /* Dark green border for contrast */
        border-radius: 10px !important;
        padding: 6px 12px !important;
    }

    /* Input fields styling */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: white !important;
        border: 2px solid #CCCCCC !important;
        border-radius: 10px !important;
        color: #333333 !important;
        padding: 4px !important;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 2px solid #4CAF50 !important;
    }

    /* The message typing box (objectName="msgEntry") => white + bigger border radius + contrasting border */
    #msgEntry {
        background-color: #FFFFFF !important;
        border: 2px solid #666666 !important; /* Contrasting border */
        border-radius: 8px !important;
        padding: 6px !important;
        color: #333333 !important;
    }

    /* The send button => green background */
    #sendBtn {
        background-color: #00b241 !important;
        color: #FFFFFF !important;
        border: 2px solid #ffffff !important; /* Dark green border for contrast */
        border-radius: 10px !important;
        padding: 6px 12px !important;
    }
    #sendBtn:hover {
        background-color: #008200 !important; /* Slightly darker green on hover */
    }

    /* The send file button => orange background */
    #fileBtn {
        background-color: #0099fa !important;
        color: #FFFFFF !important;
        border: 2px solid #ffffff !important;
        border-radius: 10px !important;
        padding: 6px 12px !important;
    }
    #fileBtn:hover {
        background-color: #00568f !important; /* Slightly darker blue */
    }

    /* The clear chat button => red background */
    #clearBtn {
        background-color: red !important;
        color: #FFFFFF ;
        border: 2px solid #ffffff !important;
        border-radius: 10px !important;
        padding: 6px 12px !important;
    }
    #clearBtn:hover {
        background-color: #CC0000 !important; /* Slightly darker red */
    }

    /* ToolBar & QToolButton */
    QToolBar {
        background-color: #2c2c2c !important;
        border: 1px solid #CCCCCC !important;
    }
    QToolBar QToolButton {
        margin: 2px;
        padding: 6px 10px;
        border-radius: 20px;
    }
    QToolButton#connectButton {
        background-color: #4CAF50 !important;
        color: #FFFFFF !important;
        border-radius: 10px;
    }
    QToolButton#prefsButton {
        background-color: #2196F3 !important;
        color: #FFFFFF !important;
        border-radius: 10px;
    }
    QToolButton#exitButton {
        background-color: #F44336 !important;
        color: #FFFFFF !important;
        border-radius: 10px;
    }

    /* Progress Bar */
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

    /* DockWidget & QListWidget */
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
    """

    app.setStyleSheet(custom_qss)
    app.setOrganizationName("MyCompany")
    app.setApplicationName("P2PChatApp")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
