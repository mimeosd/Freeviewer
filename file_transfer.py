import os
import json
import hashlib
import threading
from pathlib import Path
from typing import Optional, Callable
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import platform

class FileTransferManager:
    """Manages file transfers between clients"""
    
    def __init__(self, network_manager, status_callback: Optional[Callable] = None):
        self.network_manager = network_manager
        self.status_callback = status_callback
        self.running = False
        self.current_transfer = None
        self.transfer_lock = threading.Lock()
        self.transfer_progress_callback = None
        
    def start_file_server(self, conn, client_addr):
        """Handle incoming file transfer requests"""
        self.running = True
        
        try:
            while self.running:
                request_data = self.network_manager.recv_with_length(conn)
                if not request_data:
                    break
                    
                request = json.loads(request_data.decode())
                action = request.get('action')
                
                if action == 'send_file':
                    self._receive_file(conn, request)
                elif action == 'request_file':
                    self._send_requested_file(conn, request)
                elif action == 'list_directory':
                    self._send_directory_listing(conn, request)
                    
        except Exception as e:
            if self.status_callback:
                self.status_callback(f"File transfer error: {e}")
        finally:
            conn.close()
    
    def _send_directory_listing(self, conn, request):
        """Send directory listing to remote client"""
        path = request.get('path', str(Path.home()))
        
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                path_obj = Path.home()
            
            items = []
            if path_obj.parent != path_obj:
                items.append({
                    'name': '..',
                    'path': str(path_obj.parent),
                    'is_dir': True,
                    'size': 0
                })
            
            # List directory contents
            for item in sorted(path_obj.iterdir()):
                try:
                    items.append({
                        'name': item.name,
                        'path': str(item),
                        'is_dir': item.is_dir(),
                        'size': item.stat().st_size if item.is_file() else 0
                    })
                except:
                    continue
            
            response = {
                'status': 'success',
                'current_path': str(path_obj),
                'items': items
            }
        except Exception as e:
            response = {
                'status': 'error',
                'message': str(e)
            }
        
        self.network_manager.send_with_length(conn, json.dumps(response).encode())
    
    def request_directory_listing(self, sock, path):
        """Request directory listing from remote"""
        request = {
            'action': 'list_directory',
            'path': path
        }
        
        self.network_manager.send_with_length(sock, json.dumps(request).encode())
        
        response_data = self.network_manager.recv_with_length(sock)
        if response_data:
            return json.loads(response_data.decode())
        return None
    
    def _receive_file(self, conn, request):
        """Receive a file from remote client"""
        filename = request.get('filename', 'unknown')
        filesize = request.get('filesize', 0)
        checksum = request.get('checksum', '')
        save_path = request.get('save_path', '')
        
        if not save_path:
            # Use Downloads as default path just in case
            save_path = str(Path.home() / "Downloads" / filename)
        
        # Send ready signal
        response = {'status': 'ready'}
        self.network_manager.send_with_length(conn, json.dumps(response).encode())
        
        # Receive file data
        received = 0
        sha256 = hashlib.sha256()
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(save_path, 'wb') as f:
            while received < filesize:
                chunk_size = min(8192, filesize - received)
                data = self.network_manager.recvall(conn, chunk_size)
                if not data:
                    break
                    
                f.write(data)
                sha256.update(data)
                received += len(data)
                
                # Update progress
                if self.status_callback:
                    progress = (received / filesize) * 100
                    self.status_callback(f"Receiving {filename}: {progress:.1f}%")
                
                if self.transfer_progress_callback:
                    self.transfer_progress_callback(filename, received, filesize)
        
        # Verify checksum
        if sha256.hexdigest() == checksum:
            if self.status_callback:
                self.status_callback(f"File received successfully: {filename}")
            response = {'status': 'success'}
        else:
            if self.status_callback:
                self.status_callback(f"File transfer failed - checksum mismatch: {filename}")
            os.remove(save_path)
            response = {'status': 'checksum_error'}
            
        self.network_manager.send_with_length(conn, json.dumps(response).encode())
    
    def send_file(self, sock, filepath, remote_path=None):
        """Send a file to remote client"""
        if not os.path.exists(filepath):
            return False
            
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        
        # Calculate checksum
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        checksum = sha256.hexdigest()
        
        # Send transfer request
        request = {
            'action': 'send_file',
            'filename': filename,
            'filesize': filesize,
            'checksum': checksum,
            'save_path': remote_path
        }
        
        self.network_manager.send_with_length(sock, json.dumps(request).encode())
        
        # Wait for ready signal
        response_data = self.network_manager.recv_with_length(sock)
        if not response_data:
            return False
            
        response = json.loads(response_data.decode())
        if response.get('status') != 'ready':
            if self.status_callback:
                self.status_callback(f"File transfer cancelled by remote")
            return False
        
        # Send file data
        sent = 0
        with open(filepath, 'rb') as f:
            while sent < filesize:
                chunk = f.read(8192)
                if not chunk:
                    break
                    
                sock.sendall(chunk)
                sent += len(chunk)
                
                # Update progress
                if self.status_callback:
                    progress = (sent / filesize) * 100
                    self.status_callback(f"Sending {filename}: {progress:.1f}%")
                
                if self.transfer_progress_callback:
                    self.transfer_progress_callback(filename, sent, filesize)
        
        # Get confirmation
        response_data = self.network_manager.recv_with_length(sock)
        if response_data:
            response = json.loads(response_data.decode())
            if response.get('status') == 'success':
                if self.status_callback:
                    self.status_callback(f"File sent successfully: {filename}")
                return True
                
        return False
    
    def stop(self):
        """Stop file transfer manager"""
        self.running = False

class FileBrowserPane(ttk.Frame):
    """File browser pane for local or remote files"""
    
    def __init__(self, parent, title, is_local=True):
        super().__init__(parent)
        self.is_local = is_local
        self.current_path = Path.home() if is_local else Path('/')
        self._item_paths = {}  # Initialize the paths dict
        
        # Title
        ttk.Label(self, text=title, font=('Arial', 10, 'bold')).pack(pady=5)
        
        # Current path display
        path_frame = ttk.Frame(self)
        path_frame.pack(fill=tk.X, padx=5)
        
        self.path_var = tk.StringVar(value=str(self.current_path))
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var, state='readonly')
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(path_frame, text="↑", width=3, 
                  command=self.go_up).pack(side=tk.RIGHT, padx=2)
        ttk.Button(path_frame, text="⌂", width=3,
                  command=self.go_home).pack(side=tk.RIGHT)
        
        # File list
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Treeview with scrollbars
        tree_scroll_y = ttk.Scrollbar(list_frame)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree_scroll_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.tree = ttk.Treeview(list_frame, 
                                columns=('Size', 'Type'),
                                yscrollcommand=tree_scroll_y.set,
                                xscrollcommand=tree_scroll_x.set)
        
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)
        
        # Configure columns
        self.tree.heading('#0', text='Name')
        self.tree.heading('Size', text='Size')
        self.tree.heading('Type', text='Type')
        
        self.tree.column('#0', width=250)
        self.tree.column('Size', width=100)
        self.tree.column('Type', width=100)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind double-click
        self.tree.bind('<Double-1>', self.on_double_click)
        
        # Initial load
        if is_local:
            self.refresh_local()
    
    def format_size(self, size):
        """Format file size for display"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def refresh_local(self):
        """Refresh local file listing"""
        self.tree.delete(*self.tree.get_children())
        self._item_paths = {}
        
        if self.current_path.parent != self.current_path:
            item_id = self.tree.insert('', 'end', text='..', values=('', 'Directory'))
            self._item_paths[item_id] = str(self.current_path.parent)
        
        try:
            for item in sorted(self.current_path.iterdir()):
                try:
                    if item.is_dir():
                        item_id = self.tree.insert('', 'end', text=item.name, 
                                       values=('', 'Directory'),
                                       tags=('directory',))
                    else:
                        size = self.format_size(item.stat().st_size)
                        item_id = self.tree.insert('', 'end', text=item.name,
                                       values=(size, 'File'),
                                       tags=('file',))
                    # Store the full path for both local and remote
                    self._item_paths[item_id] = str(item)
                except:
                    continue
        except Exception as e:
            messagebox.showerror("Error", f"Cannot read directory: {e}")
    
    def refresh_remote(self, items, current_path):
        """Refresh remote file listing"""
        self.tree.delete(*self.tree.get_children())
        self._item_paths = {}
        self.current_path = Path(current_path)
        self.path_var.set(current_path)
        
        for item in items:
            if item['is_dir']:
                item_id = self.tree.insert('', 'end', text=item['name'],
                            values=('', 'Directory'),
                            tags=('directory',))
            else:
                size = self.format_size(item['size'])
                item_id = self.tree.insert('', 'end', text=item['name'],
                            values=(size, 'File'),
                            tags=('file',))
            
            # Store full path
            if item_id:
                self._item_paths[item_id] = item['path']

    def on_double_click(self, event):
        """Handle double-click on item"""
        selection = self.tree.selection()
        if not selection:
            return
            
        item_id = selection[0]
        item = self.tree.item(item_id)
        name = item['text']
        
        if name == '..':
            if self.current_path.parent != self.current_path:
                self.current_path = self.current_path.parent
                self.path_var.set(str(self.current_path))
                if self.is_local:
                    self.refresh_local()
                return True  # Signal refresh needed for remote
        elif 'directory' in item.get('tags', []):
            # Use stored path if available
            stored_path = self._item_paths.get(item_id)
            if stored_path:
                self.current_path = Path(stored_path)
            else:
                self.current_path = self.current_path / name
                
            self.path_var.set(str(self.current_path))
            if self.is_local:
                self.refresh_local()
            return True  # Signal refresh needed
        return False
    
    def go_up(self):
        """Navigate to parent directory"""
        if self.current_path.parent != self.current_path:
            self.current_path = self.current_path.parent
            self.path_var.set(str(self.current_path))
            if self.is_local:
                self.refresh_local()
            return True  # Signal refresh needed
        return False

    def go_home(self):
        """Navigate to home directory"""
        if self.is_local:
            self.current_path = Path.home()
        else:
            self.current_path = Path('/')  # Or request remote home
        
        self.path_var.set(str(self.current_path))
        if self.is_local:
            self.refresh_local()
        return True  # Signal refresh needed
    
    def get_selected_files(self):
        """Get list of selected files with full paths"""
        files = []
        for item_id in self.tree.selection():
            item = self.tree.item(item_id)
            if 'file' in item.get('tags', []):
                stored_path = self._item_paths.get(item_id)
                if stored_path:
                    files.append(stored_path)
                else:
                    # Fallback to constructing the path
                    filepath = self.current_path / item['text']
                    files.append(str(filepath))
        return files

class FileTransferWindow:
    """Enhanced file transfer window with dual-pane browser"""
    
    def __init__(self, parent, file_manager, file_socket):
        self.parent = parent
        self.file_manager = file_manager
        self.file_socket = file_socket
        self._closing = False  # Flag to track if window is closing
        self._refresh_thread = None  # Track refresh thread
        
        self.window = tk.Toplevel(parent)
        self.window.title("File Transfer")
        self.window.geometry("900x600")
        
        # Set up window close handler
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Set progress callback
        self.file_manager.transfer_progress_callback = self.update_progress
        
        self.setup_gui()
        self.remote_browser.current_path = Path('/')
        self.refresh_remote_browser()

    def on_closing(self):
        """Handle window closing event"""
        self._closing = True
        
        # Cancel any pending after callbacks safely
        try:
            # Get list of after callbacks
            after_info = self.window.tk.call('after', 'info')
            for after_id in after_info:
                try:
                    self.window.after_cancel(after_id)
                except:
                    pass
        except:
            pass  # Window might already be partially destroyed so pass
        
        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=0.5)
        
        if self.file_manager:
            self.file_manager.transfer_progress_callback = None

        try:
            self.window.destroy()
        except:
            pass  # Ignore if already destroyed
    
    def setup_gui(self):
        """Setup the enhanced file transfer GUI"""
        # Main container
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Top frame
        browser_frame = ttk.Frame(main_frame)
        browser_frame.pack(fill=tk.BOTH, expand=True)
        
        # Local browser (left)
        self.local_browser = FileBrowserPane(browser_frame, "Local Computer", is_local=True)
        self.local_browser.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2))
        
        # Transfer buttons (mid)
        button_frame = ttk.Frame(browser_frame)
        button_frame.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(button_frame, text="Send →", width=10,
                  command=self.send_files).pack(pady=5)
        ttk.Button(button_frame, text="← Receive", width=10,
                  command=self.receive_files).pack(pady=5)
        ttk.Button(button_frame, text="Refresh", width=10,
                  command=self.refresh_remote_browser).pack(pady=20)
        
        # Remote browser (right)
        self.remote_browser = FileBrowserPane(browser_frame, "Remote Computer", is_local=False)
        self.remote_browser.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))
        
        self.remote_browser.tree.unbind('<Double-1>')
        self.remote_browser.tree.bind('<Double-1>', self.on_remote_double_click)

        for child in self.remote_browser.winfo_children():
            if isinstance(child, ttk.Frame):
                for widget in child.winfo_children():
                    if isinstance(widget, ttk.Button):
                        text = widget['text']
                        if text == '↑':
                            widget.config(command=self.remote_go_up)
                        elif text == '⌂':
                            widget.config(command=self.remote_go_home)
        
        # Bottom frame for transfer status
        status_frame = ttk.LabelFrame(main_frame, text="Transfer Status")
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Current transfer label
        self.transfer_label = ttk.Label(status_frame, text="No active transfers")
        self.transfer_label.pack(pady=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(status_frame, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        
        # Transfer details
        self.details_label = ttk.Label(status_frame, text="")
        self.details_label.pack(pady=5)

    def on_remote_double_click(self, event):
        """Handle double-click in remote browser"""
        selection = self.remote_browser.tree.selection()
        if not selection:
            return
            
        item_id = selection[0]
        item = self.remote_browser.tree.item(item_id)
        name = item['text']
        
        if name == '..' or 'directory' in item.get('tags', []):
            # Handle directory navigation
            if name == '..':
                if self.remote_browser.current_path.parent != self.remote_browser.current_path:
                    self.remote_browser.current_path = self.remote_browser.current_path.parent
            else:
                # Get the stored path if available
                if hasattr(self.remote_browser, '_item_paths'):
                    stored_path = self.remote_browser._item_paths.get(item_id)
                    if stored_path:
                        self.remote_browser.current_path = Path(stored_path)
                    else:
                        self.remote_browser.current_path = self.remote_browser.current_path / name
                else:
                    self.remote_browser.current_path = self.remote_browser.current_path / name
            
            # Update path display and refresh
            self.remote_browser.path_var.set(str(self.remote_browser.current_path))
            self.refresh_remote_browser()
    
    def remote_go_up(self):
        """Navigate up in remote browser"""
        if self.remote_browser.current_path.parent != self.remote_browser.current_path:
            self.remote_browser.current_path = self.remote_browser.current_path.parent
            self.remote_browser.path_var.set(str(self.remote_browser.current_path))
            self.refresh_remote_browser()
    
    def remote_go_home(self):
        """Navigate to home in remote browser"""
        self.remote_browser.current_path = Path('/')
        self.remote_browser.path_var.set(str(self.remote_browser.current_path))
        self.refresh_remote_browser()
    
    def refresh_remote_browser(self):
        """Refresh remote file browser"""
        if self._closing:
            return
            
        def do_refresh():
            if self._closing:
                return
                
            try:
                result = self.file_manager.request_directory_listing(
                    self.file_socket,
                    str(self.remote_browser.current_path)
                )
                
                if not self._closing and result and result.get('status') == 'success':
                    try:
                        self.window.after(0, lambda: self.remote_browser.refresh_remote(
                            result.get('items', []),
                            result.get('current_path', '')
                        ) if not self._closing else None)
                    except:
                        pass  # Window might be closing
            except Exception as e:
                if not self._closing:
                    try:
                        self.window.after(0, lambda: messagebox.showerror("Error", f"Failed to refresh remote: {e}"))
                    except:
                        pass  # Window might be closing
        
        self._refresh_thread = threading.Thread(target=do_refresh, daemon=True)
        self._refresh_thread.start()
    
    def send_files(self):
        """Send selected files to remote"""
        files = self.local_browser.get_selected_files()
        if not files:
            messagebox.showwarning("No Selection", "Please select files to send")
            return
        
        remote_path = str(self.remote_browser.current_path)
        
        def do_transfer():
            for filepath in files:
                if self._closing:
                    break
                    
                filename = os.path.basename(filepath)
                remote_file = str(Path(remote_path) / filename)
                
                if not self._closing:
                    self.window.after(0, lambda f=filename: self.transfer_label.config(
                        text=f"Sending: {f}") if not self._closing else None)
                
                success = self.file_manager.send_file(self.file_socket, filepath, remote_file)
                
                if success and not self._closing:
                    self.window.after(0, lambda: self.refresh_remote_browser())
        
        threading.Thread(target=do_transfer, daemon=True).start()
    
    def receive_files(self):
        """Receive selected files from remote"""
        messagebox.showinfo("Info", "Receive functionality to be implemented")
    
    def update_progress(self, filename, current, total):
        """Update transfer progress"""
        if self._closing:
            return
            
        progress = (current / total) * 100 if total > 0 else 0
        
        try:
            if not self._closing:
                self.window.after(0, lambda: [
                    self.progress.config(value=progress),
                    self.details_label.config(text=f"{current:,} / {total:,} bytes ({progress:.1f}%)")
                ] if not self._closing else None)
            
            if current >= total and not self._closing:
                self.window.after(1000, lambda: [
                    self.transfer_label.config(text="No active transfers"),
                    self.progress.config(value=0),
                    self.details_label.config(text="")
                ] if not self._closing else None)
        except:
            pass  # Window might be closing