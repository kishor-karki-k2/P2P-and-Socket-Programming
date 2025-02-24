# main.py
import threading
import time
from network import PeerNetwork

def print_help():
    help_text = """
Commands:
    connect <ip> <port>         Connect to a peer at the specified IP and port.
    send <username> <message>   Send a chat message to the specified user.
    list                        List connected peers.
    exit                        Exit the application.
    help                        Show this help message.
"""
    print(help_text)

def main():
    # Get user input for username and port to listen on
    username = input("Enter your username: ").strip()
    host = "0.0.0.0"  # Listen on all interfaces
    port_input = input("Enter port to listen on (e.g., 5000): ").strip()
    try:
        port = int(port_input)
    except ValueError:
        print("Invalid port number.")
        return

    # Initialize and start the peer network
    network = PeerNetwork(username, host, port)
    network.start_server()
    # Broadcast online presence
    network.broadcast_presence("online")
    
    print_help()
    
    # Command-line interface loop
    while True:
        try:
            command = input("> ").strip()
            if not command:
                continue
            tokens = command.split()
            if tokens[0] == "connect":
                if len(tokens) < 3:
                    print("Usage: connect <ip> <port>")
                    continue
                peer_ip = tokens[1]
                try:
                    peer_port = int(tokens[2])
                except ValueError:
                    print("Invalid port number.")
                    continue
                network.connect_to_peer(peer_ip, peer_port)
            elif tokens[0] == "send":
                if len(tokens) < 3:
                    print("Usage: send <username> <message>")
                    continue
                recipient = tokens[1]
                message = " ".join(tokens[2:])
                network.send_chat_message(recipient, message)
            elif tokens[0] == "list":
                peers = network.list_peers()
                if peers:
                    print("Connected peers:")
                    for peer in peers:
                        print(" -", peer)
                else:
                    print("No peers connected.")
            elif tokens[0] == "help":
                print_help()
            elif tokens[0] == "exit":
                print("Exiting...")
                network.shutdown()
                time.sleep(1)  # Allow some time for threads to close
                break
            else:
                print("Unknown command. Type 'help' for a list of commands.")
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt detected. Exiting...")
            network.shutdown()
            break

if __name__ == "__main__":
    main()
