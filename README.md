# ColaStream - WebRTC SFU for Google Colab

Stream your webcam to Google Colab for AI processing - **no tunnels required!**

## How It Works

```
┌─────────────┐      VDO.Ninja       ┌─────────────────────────┐
│   Browser   │◄────signaling────────►│     Google Colab        │
│  (publish)  │                       │                         │
└──────┬──────┘                       │  ┌─────────────────┐    │
       │                              │  │ Signaling Bridge│    │
       │     WebRTC media             │  │  (Node.js)      │    │
       └─────────(via TURN)───────────┼──►       │         │    │
                                      │  │       ▼ WHIP    │    │
┌─────────────┐                       │  │  ┌─────────┐   │    │
│   Browser   │◄────(via TURN)────────┼──┼──│MediaMTX │   │    │
│   (view)    │     WebRTC media      │  │  │  (SFU)  │───┼────┼──► AI Processing
└─────────────┘                       │  │  └─────────┘   │    │    (RTSP/OpenCV)
                                      │  └─────────────────┘    │
                                      └─────────────────────────┘
```

### Why This Architecture?

| Challenge | Solution |
|-----------|----------|
| Colab has no public IP | VDO.Ninja SDK for signaling (WebSocket) |
| NAT/firewall blocks UDP | VDO.Ninja TURN servers relay media |
| Need scalable streaming | MediaMTX SFU (1 publisher → many viewers) |
| Want RTSP for AI pipelines | MediaMTX provides local RTSP endpoint |

**Key insight**: VDO.Ninja SDK handles **signaling only** (SDP exchange via data channels). VDO.Ninja's TURN servers handle NAT traversal for the actual WebRTC media. MediaMTX runs locally on Colab as the SFU. **No ngrok/cloudflared HTTP tunnels needed!**

## Quick Start

### 1. Open Colab Notebook

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/steveseguin/colastream/blob/main/notebooks/mediamtx_sfu.ipynb)

Run the cells to:
1. Install MediaMTX (SFU server)
2. Configure with VDO.Ninja TURN servers
3. Run the signaling bridge
4. Get your **Room ID**

### 2. Publish from Browser

Open: **https://steveseguin.github.io/colastream/publish.html**

1. Enter the Room ID from Colab
2. Select your camera
3. Click "Start Broadcasting"

Your webcam stream flows: Browser → VDO.Ninja TURN → MediaMTX on Colab

### 3. Process with AI

In Colab, the stream is available at `rtsp://localhost:8554/live`:

```python
import cv2

cap = cv2.VideoCapture("rtsp://localhost:8554/live")
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Your AI processing here
    # e.g., YOLO, pose detection, etc.
```

## Files

```
colastream/
├── docs/                    # GitHub Pages
│   ├── index.html          # Landing page
│   ├── publish.html        # WebRTC publisher
│   └── view.html           # WebRTC viewer
├── bridge/
│   └── signaling-bridge.js # VDO.Ninja → MediaMTX bridge
├── notebooks/
│   └── mediamtx_sfu.ipynb  # Main Colab notebook
└── configs/
    └── mediamtx.yml        # MediaMTX configuration
```

## Advanced: Local Development

```bash
# Install MediaMTX
wget https://github.com/bluenviron/mediamtx/releases/download/v1.9.3/mediamtx_v1.9.3_linux_amd64.tar.gz
tar -xzf mediamtx_v1.9.3_linux_amd64.tar.gz

# Run MediaMTX
./mediamtx configs/mediamtx.yml

# Run signaling bridge (requires Node.js)
cd bridge
npm install
node signaling-bridge.js
```

## Related Projects

- [VDO.Ninja](https://vdo.ninja) - WebRTC signaling infrastructure
- [MediaMTX](https://github.com/bluenviron/mediamtx) - Media server
- [VDO.Ninja SDK](https://github.com/steveseguin/ninjasdk) - JavaScript SDK

## License

MIT
