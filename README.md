# ColaStream - WebRTC SFU for Google Colab

Stream your webcam to Google Colab for AI processing - **no tunnels required!**

## How It Works

```
┌─────────────┐      VDO.Ninja       ┌─────────────────────────┐
│   Browser   │◄────signaling────────►│     Google Colab        │
│  (publish)  │                       │                         │
└──────┬──────┘                       │  ┌─────────────────┐    │
       │                              │  │ Signaling Bridge│    │
       │     WebRTC media             │  │  (VDO.Ninja SDK)│    │
       └──────────────────────────────┼──►       │         │    │
                                      │  │       ▼         │    │
┌─────────────┐                       │  │  ┌─────────┐   │    │
│   Browser   │◄──────────────────────┼──┼──│MediaMTX │   │    │
│   (view)    │     WebRTC media      │  │  │  (SFU)  │───┼────┼──► AI Processing
└─────────────┘                       │  │  └─────────┘   │    │
                                      │  └─────────────────┘    │
                                      └─────────────────────────┘
```

**Key insight**: VDO.Ninja SDK handles signaling and provides TURN servers for NAT traversal. MediaMTX runs locally on Colab as the SFU. No ngrok/cloudflared tunnels needed!

## Quick Start

### 1. Open Colab Notebook

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/steveseguin/colastream/blob/main/notebooks/mediamtx_sfu.ipynb)

Run the cells to:
- Install MediaMTX and Node.js
- Start the signaling bridge
- Get your **Room ID**

### 2. Publish from Browser

Open: **https://steveseguin.github.io/colastream/publish.html**

1. Enter the Room ID from Colab
2. Select your camera
3. Click "Start Broadcasting"

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

## Why This Architecture?

| Challenge | Solution |
|-----------|----------|
| Colab has no public IP | VDO.Ninja SDK for signaling |
| NAT/firewall blocks connections | VDO.Ninja TURN servers |
| Need scalable streaming | MediaMTX SFU (1 publisher → many viewers) |
| Want RTSP for AI pipelines | MediaMTX provides local RTSP |

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
