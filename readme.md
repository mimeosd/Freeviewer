# FreeViewer - Open Source Remote Desktop Solution

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey.svg)](https://github.com/yourusername/freeviewer)

A free, open-source remote desktop application built with Python that aims to provide TeamViewer-like functionality without requiring paid servers or subscriptions.

## 🎯 Project Vision

FreeViewer was created to provide a completely free alternative to commercial remote desktop solutions. The goal is to enable anyone to remotely access and control computers without:
- Monthly subscriptions
- Time limits
- Commercial restrictions
- Privacy concerns from third-party servers

## ✨ Features

### Currently Working (in LAN mode!)
- ✅ **Remote Screen Viewing** - See the remote computer's screen in real-time
- ✅ **Remote Control** - Full mouse and keyboard control
- ✅ **File Transfer** - Dual-pane file browser for easy file exchange
- ✅ **Adjustable Quality** - Configure screen quality and FPS
- ✅ **Multiple Scaling Modes** - 25%, 50%, 75%, 100%, or Fit to window
- ✅ **Password Protection** - Secure connections with optional passwords
- ✅ **Connection Status** - Real-time FPS and connection monitoring

### Network Modes
- ✅ **LAN Mode** - Works perfectly on local networks
- ✅ **Direct IP Connection** - Connect via public IP with port forwarding
- ⚠️ **P2P Mode** - Experimental (see Known Issues)

## 📋 Requirements

- Python 3.8 or higher
- Windows
- For remote control: `pynput` library
- For screen capture: `Pillow` library
- For networking: `requests` library

## 🚀 Quick Start

### Installation

1. Clone the repository:
```bash
git clone https://github.com/mimeosd/freeviewer.git
cd freeviewer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python main.py
```

### Usage

#### LAN Connection (Easiest)
1. **Host**: Click "Host Session"
2. Note your local IP address (e.g., 192.168.1.5)
3. Share this IP with the person who wants to connect
4. **Client**: Enter the host's IP and click "Connect"

#### Internet Connection (Requires Port Forwarding)
1. **Host**: 
   - Forward ports 5000-5005 in your router
   - Click "Host Session"
   - Share your public IP (from whatismyip.com)
2. **Client**: Enter the public IP and click "Connect"

## 📁 Project Structure

```
freeviewer/
├── main.py              # Main application entry point
├── file_transfer.py     # File transfer and browser functionality
├── p2p_connector.py     # P2P connection handling (experimental)
├── requirements.txt     # Python dependencies
├── README.md           # This file
└── LICENSE             # MIT License
```

## ⚠️ Known Issues & Limitations

### Current Challenges

1. **NAT Traversal Problem**
   - The biggest challenge faced during development was establishing connections between computers on different networks
   - Both computers behind NATs cannot directly connect without port forwarding
   - Attempted solutions included STUN servers and UDP hole punching, but these require complex implementation so no good.

2. **P2P Connection Issues**
   - Session code sharing through paste services (dpaste, hastebin) was implemented but faces reliability issues
   - The fundamental problem is that true P2P requires at least one peer to be directly accessible
   - Without relay servers, connections are limited to LAN or port-forwarded setups

3. **Platform-Specific Considerations**
   - Remote control requires `pynput` which may need additional permissions on macOS
   - Screen capture performance varies by platform
   - File transfer paths are OS-specific


## 🤝 Contributing

This project is open source and welcomes contributions! Areas where help is particularly needed:

### High Priority
1. **NAT Traversal Solution** - Implement reliable P2P connections without relay servers
2. **TURN Server Integration** - Add fallback relay mechanism for restrictive NATs
3. **Connection Stability** - Improve reconnection handling
4. **Cross-Platform Testing** - Test and fix issues on Linux and macOS

### Medium Priority
- Audio streaming support
- Multi-monitor support
- Clipboard synchronization
- Chat functionality
- Session recording

### How to Contribute
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/YourFeature`)
3. Commit your changes (`git commit -m 'Add some YourFeature'`)
4. Push to the branch (`git push origin feature/YourFeature`)
5. Open a Pull Request

## 📝 Development Notes

### Why Not Use Relay Servers?
The goal of this project is to provide a completely free, serverless solution. Running relay servers would require:
- Server hosting costs
- Ongoing maintenance
- Potential privacy concerns
- Scalability challenges
- That is why I wanted to try and implement p2p solution (torrent-like connection) to avoid anyone having to pay for relay server or maintating one.

### Alternative Approaches Tried
1. **STUN Servers** - Can discover external IP but can't traverse symmetric NATs
2. **UDP Hole Punching** - Requires precise timing and doesn't work with all NAT types
3. **Paste Services** - Implemented for session sharing but adds complexity

### The Real Solution?
The community's help is needed to solve the NAT traversal problem without servers. Possible approaches:
- WebRTC implementation (complex but proven)
- Distributed relay network (volunteers run small relay nodes)
- Better TURN server integration with free public TURN servers

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with Python and Tkinter
- Uses Pillow for image processing
- pynput for input control
- Inspired by the need for free, open remote desktop solutions

## 📞 Support

- **Issues**: Please report bugs and request features through GitHub Issues
- **Discussions**: Use GitHub Discussions for questions and ideas

## 🔮 Future Goals

- Truly serverless P2P connections
- Mobile app support (Android/iOS)
- Browser-based client
- End-to-end encryption
- Multi-language support
- One-click executable builds

## ⚡ Performance Tips

- Lower SCREEN_QUALITY for faster streaming over slow connections
- Reduce SCREEN_FPS for bandwidth-limited scenarios
- Use LAN whenever possible for best performance
- Close unnecessary applications on the host machine

## 🛡️ Security Notes

- Always use passwords when hosting sessions
- Only share connection details with trusted individuals
- The connection is not encrypted by default - use VPN for sensitive data
- Future versions will implement end-to-end encryption

---

**Star this project if you find it useful! Your support helps attract contributors to solve the remaining challenges.**

**Built with ❤️ for the open-source community**