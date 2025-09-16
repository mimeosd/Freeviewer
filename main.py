#!/usr/bin/env python3

import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import io
import struct
import time
import json
import zlib
from concurrent.futures import ThreadPoolExecutor
import queue
from file_transfer import FileTransferManager, FileTransferWindow
from p2p_connector import P2PConnector

try:
    import pynput
    from pynput.mouse import Button
    from pynput.keyboard import Key
    CONTROL_AVAILABLE = True
except ImportError:
    CONTROL_AVAILABLE = False

# Configuration
DEFAULT_HOST = '127.0.0.1'
AUTH_PORT = 5003      # Authentication port
SCREEN_PORT = 5000    # Screen sharing port  
CONTROL_PORT = 5004   # Remote control port
AUDIO_PORT = 5001     # Audio port (reserved for future)
FILE_PORT = 5002      # File transfer port (reserved for future)
CHAT_PORT = 5005      # Chat port (reserved for future)

MAX_CLIENTS = 5       # Maximum concurrent client connections
SCREEN_QUALITY = 70   # JPEG compression quality (1-100)
SCREEN_FPS = 15       # Screen capture frames per second

class NetworkManager:
    """Network manager"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        
    def create_server_socket(self, port):
        """Create and configure server socket"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', port))
        sock.listen(MAX_CLIENTS)
        return sock
    
    def create_client_socket(self, host, port, timeout=10):
        """Create client socket with timeout"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.settimeout(None)  # Remove timeout after connection
        return sock
    
    def recvall(self, sock, n):
        """Receive exactly n bytes"""
        data = b''
        while len(data) < n:
            try:
                packet = sock.recv(n - len(data))
                if not packet:
                    return None
                data += packet
            except socket.error:
                return None
        return data
    
    def send_with_length(self, sock, data):
        """Send data with length prefix"""
        try:
            length_prefix = struct.pack('!I', len(data))
            sock.sendall(length_prefix + data)
            return True
        except socket.error:
            return False
    
    def recv_with_length(self, sock):
        """Receive data with length prefix"""
        length_data = self.recvall(sock, 4)
        if not length_data:
            return None
        data_length = struct.unpack('!I', length_data)[0]
        if data_length > 10 * 1024 * 1024:  # 10MB max message size
            return None
        return self.recvall(sock, data_length)
    
    def shutdown(self):
        """Shutdown the thread pool"""
        try:
            self.executor.shutdown(wait=True, timeout=2)  # Have 2 seconds to clean up else
        except:
            self.executor.shutdown(wait=False)  # force shutdown if timeout

class AuthenticationManager:
    """Handle authentication"""
    
    def __init__(self):
        self.password = None
        self.connected_clients = set()
        self.client_lock = threading.Lock()
    
    def set_password(self, password):
        """Set the session password"""
        self.password = password if password else None
    
    def verify_password(self, test_password):
        """Verify password"""
        if not self.password:
            return True
        return self.password == test_password
    
    def add_client(self, client_addr):
        """Track connected client"""
        with self.client_lock:
            self.connected_clients.add(client_addr)
            return len(self.connected_clients)
    
    def remove_client(self, client_addr):
        """Remove disconnected client"""
        with self.client_lock:
            self.connected_clients.discard(client_addr)
            return len(self.connected_clients)
    
    def get_client_count(self):
        """Get current client count"""
        with self.client_lock:
            return len(self.connected_clients)

class RemoteControlManager:
    """Enhanced remote control with coordinate handling"""
    
    def __init__(self, network_manager):
        self.network_manager = network_manager
        self.running = False
        self.mouse_controller = None
        self.keyboard_controller = None
        self.remote_screen_size = (1920, 1080)
        
        if CONTROL_AVAILABLE:
            self.mouse_controller = pynput.mouse.Controller()
            self.keyboard_controller = pynput.keyboard.Controller()
    
    def start_control_server(self, conn, client_addr, status_callback=None):
        """Start control server for a client"""
        if not CONTROL_AVAILABLE:
            return
            
        self.running = True
        
        try:
            # Get actual screen dimensions
            import tkinter # could have imported this all at top
            root = tkinter.Tk()
            root.withdraw()
            self.remote_screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
            root.destroy()
            
            if status_callback:
                status_callback(f"Control connected: {client_addr[0]}")
            
            while self.running:
                cmd_data = self.network_manager.recv_with_length(conn)
                if not cmd_data:
                    break
                
                try:
                    command = json.loads(cmd_data.decode())
                    self._execute_command(command)
                except (json.JSONDecodeError, KeyError):
                    continue
                    
        except Exception:
            pass
        finally:
            if status_callback:
                status_callback(f"Control disconnected: {client_addr[0]}")
            try:
                conn.close()
            except:
                pass
    
    def _execute_command(self, command):
        """Execute remote control command with validation"""
        if not CONTROL_AVAILABLE or not self.running:
            return
            
        try:
            cmd_type = command.get('type')
            
            if cmd_type == 'mouse_move':
                x = int(command['x'] * self.remote_screen_size[0])
                y = int(command['y'] * self.remote_screen_size[1])
                # Clamp to screen bounds
                x = max(0, min(x, self.remote_screen_size[0] - 1))
                y = max(0, min(y, self.remote_screen_size[1] - 1))
                self.mouse_controller.position = (x, y)
            
            elif cmd_type == 'mouse_click':
                if 'x' in command and 'y' in command:
                    x = int(command['x'] * self.remote_screen_size[0])
                    y = int(command['y'] * self.remote_screen_size[1])
                    x = max(0, min(x, self.remote_screen_size[0] - 1))
                    y = max(0, min(y, self.remote_screen_size[1] - 1))
                    self.mouse_controller.position = (x, y)
                    time.sleep(0.01)
                
                button = Button.left if command.get('button') == 'left' else Button.right
                action = command.get('action', 'click')
                
                if action == 'press':
                    self.mouse_controller.press(button)
                elif action == 'release':
                    self.mouse_controller.release(button)
                elif action == 'click':
                    self.mouse_controller.click(button)
            
            elif cmd_type == 'mouse_scroll':
                dx = command.get('dx', 0)
                dy = command.get('dy', 0)
                # Limit scroll amount
                dx = max(-5, min(5, dx))
                dy = max(-5, min(5, dy))
                self.mouse_controller.scroll(dx, dy)
            
            elif cmd_type == 'key_press':
                key_name = command.get('key', '')
                if key_name:
                    try:
                        if hasattr(Key, key_name.lower()):
                            key = getattr(Key, key_name.lower())
                            self.keyboard_controller.press(key)
                            self.keyboard_controller.release(key)
                        elif len(key_name) == 1:
                            self.keyboard_controller.press(key_name)
                            self.keyboard_controller.release(key_name)
                    except:
                        pass
                    
        except Exception:
            pass
    
    def send_control_event(self, sock, event_type, **kwargs):
        """Send control event to remote host"""
        if not sock:
            return False
            
        command = {'type': event_type, **kwargs}
        cmd_json = json.dumps(command).encode()
        return self.network_manager.send_with_length(sock, cmd_json)
    
    def stop(self):
        """Stop control manager"""
        self.running = False

class ScreenManager:
    """Enhanced screen capture and streaming"""
    
    def __init__(self, network_manager):
        self.network_manager = network_manager
        self.running = False
        self.quality = SCREEN_QUALITY
        self.fps = SCREEN_FPS
        self.frame_time = 1.0 / self.fps
    
    def start_host(self, conn, client_addr, status_callback=None):
        """Stream screen to client"""
        self.running = True
        
        if status_callback:
            status_callback(f"Screen streaming to: {client_addr[0]}")
        
        try:
            from PIL import ImageGrab
            last_frame_time = time.time()
            
            while self.running:
                current_time = time.time()
                elapsed = current_time - last_frame_time
                
                if elapsed < self.frame_time:
                    time.sleep(self.frame_time - elapsed)
                    continue
                
                last_frame_time = current_time
                
                # Capture screen
                screenshot = ImageGrab.grab()
                screenshot = screenshot.convert('RGB')
                
                # Compress
                img_byte_arr = io.BytesIO()
                screenshot.save(img_byte_arr, format='JPEG', quality=self.quality)
                img_bytes = img_byte_arr.getvalue()
                
                # Further compress
                compressed = zlib.compress(img_bytes, level=1)
                
                if not self.network_manager.send_with_length(conn, compressed):
                    break
                    
        except Exception:
            pass
        finally:
            if status_callback:
                status_callback(f"Screen streaming ended: {client_addr[0]}")
            try:
                conn.close()
            except:
                pass
    
    def start_client(self, sock, remote_window=None, status_callback=None):
        """Receive and display screen from host"""
        self.running = True
        
        try:
            frame_count = 0
            start_time = time.time()
            
            while self.running:
                data = self.network_manager.recv_with_length(sock)
                if not data:
                    break
                
                try:
                    # Decompress and decode
                    img_bytes = zlib.decompress(data)
                    img = Image.open(io.BytesIO(img_bytes))
                    
                    if remote_window:
                        remote_window.update_remote_screen(img)
                        
                        # Update FPS counter every second
                        frame_count += 1
                        if time.time() - start_time >= 1.0:
                            fps = frame_count / (time.time() - start_time)
                            remote_window.update_status(f"Connected - {fps:.1f} FPS")
                            frame_count = 0
                            start_time = time.time()
                    
                    if status_callback:
                        status_callback("Connected")
                        
                except Exception:
                    pass
                    
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except:
                pass
    
    def stop(self):
        """Stop screen manager"""
        self.running = False

class RemoteDesktopWindow:
    """Remote desktop viewer with improved controls"""
    
    def __init__(self, parent, disconnect_callback, control_manager, control_socket, file_manager=None, file_socket=None):
        self.parent = parent
        self.disconnect_callback = disconnect_callback
        self.control_manager = control_manager
        self.control_socket = control_socket
        self.file_manager = file_manager
        self.file_socket = file_socket
        self.scale_mode = "Fit"
        self.is_fullscreen = False
        self.remote_control_enabled = True
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Remote Desktop - Connected")
        
        # Window size to cover 90% of screen
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        window_width = int(screen_width * 0.9)
        window_height = int(screen_height * 0.9)
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self.setup_gui()
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        # Focus window
        self.window.lift()
        self.window.focus_force()
    
    def setup_gui(self):
        """Setup the GUI components"""
        # Toolbar
        self.toolbar = ttk.Frame(self.window)
        self.toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # Control buttons
        ttk.Button(self.toolbar, text="Disconnect", 
                  command=self.on_window_close).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.toolbar, text="Fullscreen", 
                  command=self.toggle_fullscreen).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.toolbar, text="File Transfer", 
          command=self.open_file_transfer).pack(side=tk.LEFT, padx=5)
        
        # Remote control toggle
        self.control_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.toolbar, text="Remote Control", 
                       variable=self.control_var,
                       command=self.toggle_remote_control).pack(side=tk.LEFT, padx=10)
        
        # Scale options
        tk.Label(self.toolbar, text="Scale:").pack(side=tk.LEFT, padx=(20, 5))
        self.scale_var = tk.StringVar(value="Fit")
        scale_combo = ttk.Combobox(self.toolbar, textvariable=self.scale_var, 
                                  values=["25%", "50%", "75%", "100%", "Fit"], 
                                  width=8, state="readonly")
        scale_combo.pack(side=tk.LEFT, padx=5)
        scale_combo.bind("<<ComboboxSelected>>", self.on_scale_change)
        
        # Status label
        self.status_label = tk.Label(self.toolbar, text="Connecting...", fg="blue")
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # Canvas with scrollbars
        self.canvas = tk.Canvas(self.window, bg='black', highlightthickness=0)
        self.scrollbar_v = ttk.Scrollbar(self.window, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar_h = ttk.Scrollbar(self.window, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.canvas.configure(yscrollcommand=self.scrollbar_v.set, xscrollcommand=self.scrollbar_h.set)
        
        self.scrollbar_v.pack(side=tk.RIGHT, fill=tk.Y)
        self.scrollbar_h.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Screen display frame
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Screen label
        self.screen_label = tk.Label(self.scrollable_frame, bg='black', cursor="cross")
        self.screen_label.pack()
        
        # Bind events
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.setup_remote_control()
    
    def setup_remote_control(self):
        """Setup remote control event bindings"""
        if not CONTROL_AVAILABLE:
            self.control_var.set(False)
            return
        
        # Mouse events
        self.screen_label.bind("<Button-1>", self.on_left_click)
        self.screen_label.bind("<ButtonRelease-1>", self.on_left_release)
        self.screen_label.bind("<Button-3>", lambda e: self.on_right_click(e))
        self.screen_label.bind("<Motion>", self.on_mouse_motion)
        self.screen_label.bind("<B1-Motion>", self.on_mouse_drag)
        self.screen_label.bind("<MouseWheel>", self.on_mouse_wheel)
        
        # Keyboard events
        self.screen_label.bind("<KeyPress>", self.on_key_press)
        self.screen_label.config(takefocus=True)
    
    def get_normalized_coordinates(self, event):
        """Convert event coordinates to normalized (0-1) range"""
        widget_width = self.screen_label.winfo_width()
        widget_height = self.screen_label.winfo_height()
        
        if widget_width <= 1 or widget_height <= 1:
            return None, None
        
        x_norm = max(0.0, min(1.0, event.x / widget_width))
        y_norm = max(0.0, min(1.0, event.y / widget_height))
        
        return x_norm, y_norm
    
    def on_left_click(self, event):
        """Handle left mouse button press"""
        self.screen_label.focus_set()
        
        if not self.remote_control_enabled or not self.control_socket:
            return
        
        x_norm, y_norm = self.get_normalized_coordinates(event)
        if x_norm is None:
            return
        
        self.control_manager.send_control_event(
            self.control_socket, 'mouse_click',
            button='left', action='press', x=x_norm, y=y_norm
        )
    
    def on_left_release(self, event):
        """Handle left mouse button release"""
        if not self.remote_control_enabled or not self.control_socket:
            return
        
        x_norm, y_norm = self.get_normalized_coordinates(event)
        if x_norm is None:
            return
        
        self.control_manager.send_control_event(
            self.control_socket, 'mouse_click',
            button='left', action='release', x=x_norm, y=y_norm
        )
    
    def on_right_click(self, event):
        """Handle right mouse button click"""
        if not self.remote_control_enabled or not self.control_socket:
            return
        
        x_norm, y_norm = self.get_normalized_coordinates(event)
        if x_norm is None:
            return
        
        self.control_manager.send_control_event(
            self.control_socket, 'mouse_click',
            button='right', action='click', x=x_norm, y=y_norm
        )
    
    def on_mouse_motion(self, event):
        """Handle mouse motion"""
        if not self.remote_control_enabled or not self.control_socket:
            return
        
        x_norm, y_norm = self.get_normalized_coordinates(event)
        if x_norm is None:
            return
        
        self.control_manager.send_control_event(
            self.control_socket, 'mouse_move', x=x_norm, y=y_norm
        )
    
    def on_mouse_drag(self, event):
        """Handle mouse drag"""
        self.on_mouse_motion(event)
    
    def on_mouse_wheel(self, event):
        """Handle mouse wheel scroll"""
        if not self.remote_control_enabled or not self.control_socket:
            return
        
        dy = 1 if event.delta > 0 else -1
        self.control_manager.send_control_event(
            self.control_socket, 'mouse_scroll', dx=0, dy=dy
        )
    
    def on_key_press(self, event):
        """Handle keyboard input"""
        if not self.remote_control_enabled or not self.control_socket:
            return
        
        # Special key mappings
        special_keys = {
            'Return': 'enter', 'BackSpace': 'backspace', 'Tab': 'tab',
            'Escape': 'esc', 'Delete': 'delete', 'space': 'space',
            'Up': 'up', 'Down': 'down', 'Left': 'left', 'Right': 'right',
            'Home': 'home', 'End': 'end', 'Page_Up': 'page_up', 'Page_Down': 'page_down',
            'F1': 'f1', 'F2': 'f2', 'F3': 'f3', 'F4': 'f4', 'F5': 'f5', 'F6': 'f6',
            'F7': 'f7', 'F8': 'f8', 'F9': 'f9', 'F10': 'f10', 'F11': 'f11', 'F12': 'f12'
        }
        
        key_name = event.keysym
        
        if key_name in special_keys:
            key_name = special_keys[key_name]
        elif len(event.char) == 1 and event.char.isprintable():
            key_name = event.char
        else:
            return
        
        self.control_manager.send_control_event(
            self.control_socket, 'key_press', key=key_name
        )
    
    def toggle_remote_control(self):
        """Toggle remote control on/off"""
        self.remote_control_enabled = self.control_var.get()
        status = "ON" if self.remote_control_enabled else "OFF"
        color = "green" if self.remote_control_enabled else "red"
        self.status_label.config(text=f"Remote Control: {status}", fg=color)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self.is_fullscreen = not self.is_fullscreen
        self.window.attributes("-fullscreen", self.is_fullscreen)
        
        if self.is_fullscreen:
            self.toolbar.pack_forget()
            self.window.bind("<Escape>", lambda e: self.toggle_fullscreen())
        else:
            self.toolbar.pack(fill=tk.X, padx=5, pady=5, before=self.canvas)
            self.window.unbind("<Escape>")
    
    def on_scale_change(self, event=None):
        """Handle scale mode change"""
        self.scale_mode = self.scale_var.get()
        if hasattr(self, 'current_image'):
            self.update_remote_screen(self.current_image)
    
    def on_canvas_configure(self, event):
        """Handle canvas resize"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.scale_mode == "Fit" and hasattr(self, 'current_image'):
            self.update_remote_screen(self.current_image)
    
    def update_remote_screen(self, original_image):
        """Update the remote screen display"""
        try:
            self.current_image = original_image
            
            if self.scale_mode == "Fit":
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                
                if canvas_width > 1 and canvas_height > 1:
                    img_ratio = original_image.width / original_image.height
                    canvas_ratio = canvas_width / canvas_height
                    
                    if img_ratio > canvas_ratio:
                        new_width = canvas_width
                        new_height = int(canvas_width / img_ratio)
                    else:
                        new_height = canvas_height
                        new_width = int(canvas_height * img_ratio)
                else:
                    new_width, new_height = 1024, 768
                    
                display_img = original_image.resize((new_width, new_height), Image.LANCZOS)
                
            elif self.scale_mode == "100%":
                display_img = original_image
            else:
                # Percentage scaling
                scale_factor = float(self.scale_mode.rstrip('%')) / 100
                new_width = int(original_image.width * scale_factor)
                new_height = int(original_image.height * scale_factor)
                display_img = original_image.resize((new_width, new_height), Image.LANCZOS)
            
            # Update display
            img_tk = ImageTk.PhotoImage(display_img)
            self.screen_label.configure(image=img_tk)
            self.screen_label.image = img_tk
            
            # Update scroll region
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            
        except Exception:
            pass
    
    def update_status(self, status):
        """Update status display"""
        try:
            if "Connected" in status:
                self.status_label.config(text=status, fg="green")
            elif "Error" in status or "Failed" in status:
                self.status_label.config(text=status, fg="red")
            else:
                self.status_label.config(text=status, fg="blue")
        except:
            pass
    
    def on_window_close(self):
        """Handle window close"""
        try:
            # Close sockets first
            if self.control_socket:
                try:
                    self.control_socket.shutdown(socket.SHUT_RDWR)
                    self.control_socket.close()
                except:
                    pass
                self.control_socket = None
            
            if self.file_socket:
                try:
                    self.file_socket.shutdown(socket.SHUT_RDWR)
                    self.file_socket.close()
                except:
                    pass
                self.file_socket = None
        except:
            pass
        
        self.disconnect_callback()
        try:
            self.window.destroy()
        except:
            pass

    def open_file_transfer(self):
        """Open file transfer window"""
        if self.file_socket and self.file_manager:
            self.file_window = FileTransferWindow(self.window, self.file_manager, self.file_socket)
        else:
            messagebox.showwarning("File Transfer", "File transfer connection not available")

class RemoteDesktopApp:
    """Main application with improved architecture"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FreeViewer - TeamViewer Alternative")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        
        # Managers
        self.network_manager = NetworkManager()
        self.auth_manager = AuthenticationManager()
        self.screen_manager = ScreenManager(self.network_manager)
        self.control_manager = RemoteControlManager(self.network_manager)
        self.file_manager = FileTransferManager(self.network_manager, self.add_status)
        self.p2p_connector = P2PConnector(self.add_status)
        
        # State
        self.mode = None
        self.connections = {}
        self.servers = {}
        self.server_running = False
        self.remote_window = None
        self.status_queue = queue.Queue()
        
        self.setup_gui()
        self.process_status_updates()
        
        # Handle application close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_gui(self):
        """Setup the main GUI"""
        # Title frame
        title_frame = tk.Frame(self.root, bg='#2c3e50', pady=20)
        title_frame.pack(fill=tk.X)
        
        title = tk.Label(title_frame, text="FreeViewer", 
                        font=("Arial", 20, "bold"), fg='white', bg='#2c3e50')
        title.pack()
        
        subtitle = tk.Label(title_frame, text="Remote Desktop Control", 
                          font=("Arial", 10), fg='#ecf0f1', bg='#2c3e50')
        subtitle.pack()
        
        # Main content frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Mode selection
        mode_frame = ttk.LabelFrame(main_frame, text="Select Mode", padding="10")
        mode_frame.pack(fill=tk.X, pady=(0, 15))
        
        button_frame = ttk.Frame(mode_frame)
        button_frame.pack()
        
        self.host_btn = ttk.Button(button_frame, text="Host Session", 
                                  command=self.start_host_mode, width=20)
        self.host_btn.pack(side=tk.LEFT, padx=5)
        
        self.join_btn = ttk.Button(button_frame, text="Join Session", 
                                  command=self.start_client_mode, width=20)
        self.join_btn.pack(side=tk.LEFT, padx=5)
        
        # Connection settings
        conn_frame = ttk.LabelFrame(main_frame, text="Connection Settings", padding="10")
        conn_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Host IP
        ip_frame = ttk.Frame(conn_frame)
        ip_frame.pack(fill=tk.X, pady=5)
        ttk.Label(ip_frame, text="Remote IP:").pack(side=tk.LEFT, padx=(0, 10))
        self.host_entry = ttk.Entry(ip_frame, width=20)
        self.host_entry.insert(0, DEFAULT_HOST)
        self.host_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Password
        pwd_frame = ttk.Frame(conn_frame)
        pwd_frame.pack(fill=tk.X, pady=5)
        ttk.Label(pwd_frame, text="Password:").pack(side=tk.LEFT, padx=(0, 10))
        self.password_entry = ttk.Entry(pwd_frame, show="*", width=20)
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Action buttons
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.connect_btn = ttk.Button(btn_frame, text="Connect", 
                                     command=self.connect_to_host, state=tk.DISABLED)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="Disconnect", 
                                        command=self.disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        # Status display
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True)
        
        self.status_text = tk.Text(status_frame, height=5, width=50, 
                                  state=tk.DISABLED, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True)
        
        # Initial status
        self.add_status("Ready to connect or host a session")
    
    def add_status(self, message):
        """Add status message to display"""
        self.status_queue.put(message)
    
    def process_status_updates(self):
        """Process status updates from queue"""
        try:
            while True:
                message = self.status_queue.get_nowait()
                self.status_text.config(state=tk.NORMAL)
                self.status_text.insert(tk.END, f"• {message}\n")
                self.status_text.see(tk.END)
                self.status_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_status_updates)
    
    def start_host_mode(self):
        if self.server_running:
            messagebox.showwarning("Warning", "Server is already running")
            return
        
        self.mode = 'host'
        password = self.password_entry.get()
        self.auth_manager.set_password(password)
        
        try:
            self.server_running = True
            
            # Start servers first
            self.servers['auth'] = self.network_manager.create_server_socket(AUTH_PORT)
            self.network_manager.executor.submit(self._run_auth_server)
            
            self.servers['screen'] = self.network_manager.create_server_socket(SCREEN_PORT)
            self.network_manager.executor.submit(self._run_screen_server)
            
            self.servers['control'] = self.network_manager.create_server_socket(CONTROL_PORT)
            self.network_manager.executor.submit(self._run_control_server)
            
            self.servers['file'] = self.network_manager.create_server_socket(FILE_PORT)
            self.network_manager.executor.submit(self._run_file_server)
            
            # P2P
            session_code = self.p2p_connector.setup_host_p2p(password)
            
            if session_code:
                self.add_status(f"P2P Session Code: {session_code}")
                self.add_status("Share this code with clients to connect")
                
                # Session code
                info_msg = f"P2P Session Created!\n\nSession Code: {session_code}\n\nShare this EXACT code with others to connect"
                messagebox.showinfo("P2P Session", info_msg)
            else:
                # Fallback to showing IP if !(session code)
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                self.add_status(f"P2P setup failed, using direct IP: {local_ip}")
                messagebox.showinfo("Direct Connection", f"Share your IP: {local_ip}")
            
            self.host_btn.config(state=tk.DISABLED)
            self.join_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            
        except Exception as e:
            self.server_running = False
            messagebox.showerror("Error", f"Failed to start hosting: {e}")
            self.add_status(f"Error: {e}")

    
    def start_client_mode(self):
        """Enable client mode"""
        self.mode = 'client'
        self.connect_btn.config(state=tk.NORMAL)
        self.host_btn.config(state=tk.DISABLED)
        self.add_status("Client mode - Enter host IP and password to connect")
    
    def connect_to_host(self):
        host_input = self.host_entry.get().strip()
        if not host_input:
            messagebox.showerror("Error", "Please enter host IP or session code")
            return
        
        password = self.password_entry.get()
        
        if '-' in host_input and len(host_input) < 20:
            self.add_status(f"Connecting via P2P session {host_input}...")
            peer_info = self.p2p_connector.connect_p2p(host_input)
            
            if peer_info:
                host = peer_info[0]
                self.add_status(f"P2P connection established to {host}")
            else:
                messagebox.showerror("Error", "Failed to establish P2P connection")
                return
        else:
            host = host_input
            self.add_status(f"Direct connection to {host}...")
        
        self.network_manager.executor.submit(self._connect_to_host_thread, host, password)
    
    def _connect_to_host_thread(self, host, password):
        """Connect to host in background thread"""
        try:
            # Step 1: Authenticate
            auth_sock = self.network_manager.create_client_socket(host, AUTH_PORT)
            auth_request = {'password': password}
            auth_data = json.dumps(auth_request).encode()
            self.network_manager.send_with_length(auth_sock, auth_data)
            
            response_data = self.network_manager.recv_with_length(auth_sock)
            if not response_data:
                self.root.after(0, lambda: messagebox.showerror("Error", "No auth response"))
                return
            
            response = json.loads(response_data.decode())
            auth_sock.close()
            
            if response.get('status') != 'success':
                self.root.after(0, lambda: messagebox.showerror("Error", "Authentication failed"))
                return
            
            self.add_status("Authentication successful")
            
            # Next thing
            control_sock = None
            try:
                control_sock = self.network_manager.create_client_socket(host, CONTROL_PORT)
                self.connections['control'] = control_sock
                self.add_status("Control connection established")
            except Exception as e:
                self.add_status(f"Control connection failed: {e}")
            
            # Next thing 2
            file_sock = None
            try:
                file_sock = self.network_manager.create_client_socket(host, FILE_PORT)
                self.connections['file'] = file_sock
                self.add_status("File transfer connection established")
            except Exception as e:
                self.add_status(f"File transfer connection failed: {e}")
            
            # Screen sharing starts here
            screen_sock = self.network_manager.create_client_socket(host, SCREEN_PORT)
            self.connections['screen'] = screen_sock
            self.add_status("Screen connection established")
            
            # Create remote window
            self.root.after(0, lambda: self._create_remote_window(control_sock, screen_sock, file_sock))
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Connection failed: {e}"))
            self.add_status(f"Connection error: {e}")
    
    def _create_remote_window(self, control_sock, screen_sock, file_sock=None):
        """Create remote desktop window"""
        self.remote_window = RemoteDesktopWindow(
            self.root, 
            self.disconnect,
            self.control_manager,
            control_sock,
            self.file_manager,
            file_sock
        )
        
        # Start screen receiving thread
        self.network_manager.executor.submit(
            self.screen_manager.start_client,
            screen_sock,
            self.remote_window,
            self.add_status
        )
        
        # Update UI
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.add_status("Remote desktop connected")
    
    def _run_auth_server(self):
        """Run authentication server"""
        server_socket = self.servers.get('auth')
        if not server_socket:
            return
        
        while self.server_running:
            try:
                server_socket.settimeout(1.0)
                try:
                    conn, addr = server_socket.accept()
                except socket.timeout:
                    continue
                
                # Handle auth in separate thread to prevent clogging
                self.network_manager.executor.submit(self._handle_auth_client, conn, addr)
                
            except Exception:
                break
    
    def _handle_auth_client(self, conn, addr):
        """Handle authentication request"""
        try:
            data = self.network_manager.recv_with_length(conn)
            if not data:
                return
            
            request = json.loads(data.decode())
            client_password = request.get('password', '')
            
            if self.auth_manager.verify_password(client_password):
                response = {'status': 'success'}
                self.add_status(f"Client authenticated: {addr[0]}")
            else:
                response = {'status': 'failed'}
                self.add_status(f"Authentication failed: {addr[0]}")
            
            response_data = json.dumps(response).encode()
            self.network_manager.send_with_length(conn, response_data)
            
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except:
                pass
    
    def _run_screen_server(self):
        """Run screen sharing server"""
        server_socket = self.servers.get('screen')
        if not server_socket:
            return
        
        while self.server_running:
            try:
                server_socket.settimeout(1.0)
                try:
                    conn, addr = server_socket.accept()
                except socket.timeout:
                    continue
                
                # Check client limit
                if self.auth_manager.get_client_count() >= MAX_CLIENTS:
                    self.add_status(f"Connection rejected (max clients): {addr[0]}")
                    conn.close()
                    continue
                
                self.auth_manager.add_client(addr)
                
                # Handle screen sharing in separate thread
                self.network_manager.executor.submit(
                    self.screen_manager.start_host,
                    conn, addr, self.add_status
                )
                
            except Exception:
                break
    
    def _run_control_server(self):
        """Run remote control server"""
        server_socket = self.servers.get('control')
        if not server_socket:
            return
        
        while self.server_running:
            try:
                server_socket.settimeout(1.0)
                try:
                    conn, addr = server_socket.accept()
                except socket.timeout:
                    continue
                
                # Handle control in separate thread
                self.network_manager.executor.submit(
                    self.control_manager.start_control_server,
                    conn, addr, self.add_status
                )
                
            except Exception:
                break

    def _run_file_server(self):
        """Run file transfer server"""
        server_socket = self.servers.get('file')
        if not server_socket:
            return
        
        while self.server_running:
            try:
                server_socket.settimeout(1.0)
                try:
                    conn, addr = server_socket.accept()
                except socket.timeout:
                    continue
                
                # Handle file transfer in separate thread
                self.network_manager.executor.submit(
                    self.file_manager.start_file_server,
                    conn, addr
                )
                
            except Exception:
                break
    
    def disconnect(self):
        """Disconnect all connections"""
        # Stop managers
        self.screen_manager.stop()
        self.control_manager.stop()
        self.file_manager.stop()
        
        # Close client connections
        for name, sock in self.connections.items():
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except:
                pass
        self.connections.clear()
        
        # Close remote window
        if self.remote_window:
            try:
                self.remote_window.window.destroy()
            except:
                pass
            self.remote_window = None
        
        # Stop servers if hosting
        if self.server_running:
            self.server_running = False
            for name, sock in self.servers.items():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                    sock.close()
                except:
                    pass
            self.servers.clear()
        
        # Reset UI
        self.host_btn.config(state=tk.NORMAL)
        self.join_btn.config(state=tk.NORMAL)
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.DISABLED)
        
        self.mode = None
        self.add_status("Disconnected")
    
    def on_close(self):
        """Handle application close"""
        self.disconnect()
        self.p2p_connector.cleanup()
        self.network_manager.shutdown()
        
        try:
            for after_id in self.root.tk.call('after', 'info'):
                try:
                    self.root.after_cancel(after_id)
                except:
                    pass
        except:
            pass
        
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass  # Ignore Tcl errors
    
    def run(self):
        """Run the application"""
        self.root.mainloop()

if __name__ == "__main__":
    app = RemoteDesktopApp()
    app.run()