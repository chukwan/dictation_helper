import socket
import sys

def check_port(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return True, None
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    common_ports = [3000, 5000, 8000, 8080, 8081, 8888, 9000, 9001, 9999]
    print(f"Scanning common ports: {common_ports}...")
    found_port = None
    for port in common_ports:
        success, error = check_port(port)
        if success:
            print(f"SUCCESS: Port {port} is available and bindable.")
            found_port = port
            break
        else:
            print(f"FAILED: Port {port} - {error}")
            
    if found_port:
        print(f"\nRecommended Action: Use port {found_port}")
    else:
        print("\nCould not find any bindable port in common list.")

