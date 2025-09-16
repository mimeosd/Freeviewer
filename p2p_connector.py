import socket
import struct
import random
import string
import json
import threading
import time
import requests
from typing import Optional, Tuple, Dict
import base64

class STUNClient:
    """The `STUNClient` class in Python implements a STUN client that can query multiple STUN servers to obtain the external IP address and port of the client."""
    STUN_SERVERS = [
        ('stun.l.google.com', 19302),
        ('stun1.l.google.com', 19302),
        ('stun2.l.google.com', 19302),
        ('stun3.l.google.com', 19302),
        ('stun4.l.google.com', 19302),
        ('stun.stunprotocol.org', 3478),
        ('stun.voip.eutelia.it', 3478),
        ('stun.voipbuster.com', 3478),
    ]
    
    def __init__(self):
        self.transaction_id = None
        
    def get_external_address(self) -> Optional[Tuple[str, int]]:
        for server_host, server_port in self.STUN_SERVERS:
            try:
                result = self._query_stun_server(server_host, server_port)
                if result:
                    return result
            except:
                continue
        return None
    
    def _query_stun_server(self, host: str, port: int) -> Optional[Tuple[str, int]]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        
        try:
            message = self._build_binding_request()
            sock.sendto(message, (host, port))
            
            data, addr = sock.recvfrom(1024)
            return self._parse_binding_response(data)
        except:
            return None
        finally:
            sock.close()
    
    def _build_binding_request(self) -> bytes:
        msg_type = 0x0001
        msg_length = 0x0000
        magic_cookie = 0x2112A442
        self.transaction_id = random.getrandbits(96)
        
        message = struct.pack('>HHI', msg_type, msg_length, magic_cookie)
        message += self.transaction_id.to_bytes(12, 'big')
        return message
    
    def _parse_binding_response(self, data: bytes) -> Optional[Tuple[str, int]]:
        if len(data) < 20:
            return None
        
        msg_type, msg_length, magic_cookie = struct.unpack('>HHI', data[:8])
        transaction_id = int.from_bytes(data[8:20], 'big')
        
        if transaction_id != self.transaction_id:
            return None
        
        i = 20
        while i < len(data):
            if i + 4 > len(data):
                break
                
            attr_type, attr_length = struct.unpack('>HH', data[i:i+4])
            i += 4
            
            if attr_type == 0x0001:
                if i + 8 <= len(data):
                    family = data[i+1]
                    port = struct.unpack('>H', data[i+2:i+4])[0]
                    ip = socket.inet_ntoa(data[i+4:i+8])
                    return (ip, port)
            elif attr_type == 0x0020:
                if i + 8 <= len(data):
                    family = data[i+1]
                    port = struct.unpack('>H', data[i+2:i+4])[0] ^ (magic_cookie >> 16)
                    ip_bytes = bytes([b ^ ((magic_cookie >> (24 - i*8)) & 0xFF) for i, b in enumerate(data[i+4:i+8])])
                    ip = socket.inet_ntoa(ip_bytes)
                    return (ip, port)
            
            i += attr_length
            if attr_length % 4:
                i += 4 - (attr_length % 4)
        
        return None

class SessionManager:
    def __init__(self):
        self.session_code = None
        self.peer_info = None
        
    def generate_session_code(self) -> str:
        parts = []
        for _ in range(3):
            parts.append(''.join(random.choices(string.ascii_uppercase + string.digits, k=4)))
        self.session_code = '-'.join(parts)
        return self.session_code
    
    def publish_session(self, ip: str, port: int, password: str = '') -> str:
        session_data = {
            'ip': ip,
            'port': port,
            'password': password,
            'timestamp': time.time()
        }
        
        encoded = base64.b64encode(json.dumps(session_data).encode()).decode()
        
        try:
            response = requests.post(
                'https://dpaste.com/api/',
                data={
                    'content': encoded,
                    'expiry_days': 1
                },
                timeout=10
            )
            if response.status_code == 200 or response.status_code == 201:
                # Extract paste ID from response
                result = response.text.strip()
                return result
        except Exception as e:
            print(f"dpaste.com failed: {e}")
        
        try:
            response = requests.post(
                'https://hastebin.com/documents',
                data=encoded,
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                return result.get('key', '')
        except Exception as e:
            print(f"hastebin failed: {e}")
        
        return None

    def fetch_session(self, session_id: str) -> Optional[Dict]:
        session_id = session_id.strip()
        
        try:
            response = requests.get(f'https://dpaste.com/{session_id}/raw', timeout=5)
            if response.status_code == 200:
                decoded = json.loads(base64.b64decode(response.text.strip()))
                return decoded
        except Exception as e:
            print(f"dpaste fetch failed: {e}")
        
        try:
            response = requests.get(f'https://hastebin.com/raw/{session_id}', timeout=5)
            if response.status_code == 200:
                decoded = json.loads(base64.b64decode(response.text.strip()))
                return decoded
        except Exception as e:
            print(f"hastebin fetch failed: {e}")
        
        return None

class UPnPManager:
    def __init__(self):
        self.enabled = False
        
    def try_port_forward(self, ports: list) -> bool:
        try:
            import miniupnpc
            
            upnp = miniupnpc.UPnP()
            upnp.discoverdelay = 200
            
            if upnp.discover() == 0:
                return False
                
            upnp.selectigd()
            
            for port in ports:
                try:
                    upnp.addportmapping(
                        port, 'TCP', upnp.lanaddr, port,
                        'FreeViewer', ''
                    )
                except:
                    pass
            
            self.enabled = True
            return True
        except:
            return False
    
    def cleanup(self, ports: list):
        if not self.enabled:
            return
            
        try:
            import miniupnpc
            upnp = miniupnpc.UPnP()
            upnp.discoverdelay = 200
            
            if upnp.discover() > 0:
                upnp.selectigd()
                for port in ports:
                    try:
                        upnp.deleteportmapping(port, 'TCP')
                    except:
                        pass
        except:
            pass

class HolePuncher:
    def __init__(self, local_port: int):
        self.local_port = local_port
        self.sock = None
        
    def punch_hole(self, peer_ip: str, peer_port: int) -> bool:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', self.local_port))
        self.sock.settimeout(0.5)
        
        punch_thread = threading.Thread(target=self._punch_loop, args=(peer_ip, peer_port))
        punch_thread.daemon = True
        punch_thread.start()
        
        start_time = time.time()
        while time.time() - start_time < 10:
            try:
                data, addr = self.sock.recvfrom(1024)
                if data == b'PUNCH_ACK':
                    self.sock.sendto(b'PUNCH_CONFIRM', addr)
                    time.sleep(0.1)
                    self.sock.close()
                    return True
            except socket.timeout:
                continue
            except:
                break
        
        try:
            self.sock.close()
        except:
            pass
        return False
    
    def _punch_loop(self, peer_ip: str, peer_port: int):
        for _ in range(20):
            try:
                self.sock.sendto(b'PUNCH_ACK', (peer_ip, peer_port))
                time.sleep(0.5)
            except:
                break

class P2PConnector:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self.stun_client = STUNClient()
        self.session_manager = SessionManager()
        self.upnp_manager = UPnPManager()
        self.external_address = None
        self.connection_mode = None
        
    def log_status(self, message: str):
        if self.status_callback:
            self.status_callback(message)
    
    def setup_host_p2p(self, password: str = '') -> Optional[str]:
        self.log_status("Setting up P2P hosting...")
        
        # Get external IP first
        external_ip = self._get_public_ip()
        if not external_ip:
            self.log_status("Could not get public IP, trying STUN...")
            external_addr = self.stun_client.get_external_address()
            if external_addr:
                external_ip = external_addr[0]
                self.log_status(f"Got external IP via STUN: {external_ip}")
            else:
                self.log_status("STUN failed, cannot determine external IP")
                return None
        else:
            self.log_status(f"Got public IP: {external_ip}")
        
        # Try UPnP
        ports = [5000, 5001, 5002, 5003, 5004, 5005]
        if self.upnp_manager.try_port_forward(ports):
            self.log_status("UPnP port forwarding successful")
        else:
            self.log_status("UPnP not available - using direct connection")
        
        # Publish session
        session_id = self.session_manager.publish_session(external_ip, 5003, password)
        if session_id:
            self.log_status(f"Session published successfully!")
            self.log_status(f"Share this code: {session_id}")
            return session_id
        else:
            self.log_status("Failed to publish session to paste service")
            return None
    
    def connect_p2p(self, session_code: str) -> Optional[Tuple[str, int]]:
        # Clean session code
        session_code = session_code.strip()
        if "Session:" in session_code:
            session_code = session_code.replace("Session:", "").strip()
        
        self.log_status(f"Looking up session: {session_code}")
        
        session_data = self.session_manager.fetch_session(session_code)
        if not session_data:
            self.log_status(f"Could not find session with code: {session_code}")
            return None
        
        peer_ip = session_data.get('ip')
        peer_port = session_data.get('port', 5003)
        
        self.log_status(f"Found peer at {peer_ip}:{peer_port}")
        
        # Try direct connection
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(5)
            test_sock.connect((peer_ip, peer_port))
            test_sock.close()
            self.log_status("Direct connection successful!")
            return (peer_ip, peer_port)
        except Exception as err:
            self.log_status(f"Direct connection failed: {err}")
            self.log_status("Try ensuring both computers can access the internet")
            return None
    
    def _get_public_ip(self) -> Optional[str]:
        services = [
            'https://api.ipify.org',
            'https://ifconfig.me/ip',
            'https://icanhazip.com'
        ]
        
        for service in services:
            try:
                response = requests.get(service, timeout=3)
                if response.status_code == 200:
                    return response.text.strip()
            except:
                continue
        return None
    
    def cleanup(self):
        ports = [5000, 5001, 5002, 5003, 5004, 5005]
        self.upnp_manager.cleanup(ports)