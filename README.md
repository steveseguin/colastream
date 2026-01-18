# ColaStream - WebRTC SFU on Google Colab

Run a WebRTC SFU (Selective Forwarding Unit) server on Google Colab for AI-powered live streaming projects.

## Overview

This project deploys [MediaMTX](https://github.com/bluenviron/mediamtx) as a WebRTC SFU on Google Colab, enabling real-time video streaming for AI processing pipelines.

## Feasibility

### Why This Works

| Challenge | Solution |
|-----------|----------|
| Colab has no public IP | ngrok/cloudflared tunnels expose endpoints |
| UDP ports blocked | TURN servers relay media over TCP |
| NAT traversal | WHIP/WHEP protocols use HTTP for signaling |
| Session timeouts | Designed for development/testing cycles |

### Architecture

```
┌─────────────────┐     HTTPS/WSS      ┌──────────────────┐
│  Browser/OBS    │◄──────────────────►│  ngrok tunnel    │
│  (WHIP client)  │                    │                  │
└─────────────────┘                    └────────┬─────────┘
                                                │
                                                ▼
┌─────────────────┐                    ┌──────────────────┐
│  Browser        │◄──────────────────►│  Google Colab    │
│  (WHEP viewer)  │     via TURN       │  MediaMTX SFU    │
└─────────────────┘                    │  + AI Pipeline   │
                                       └──────────────────┘
```

## Quick Start

### Option 1: Open in Colab (Recommended)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/steveseguin/colastream/blob/main/notebooks/mediamtx_sfu.ipynb)

### Option 2: Local Testing

```bash
# Download MediaMTX
wget https://github.com/bluenviron/mediamtx/releases/download/v1.9.3/mediamtx_v1.9.3_linux_amd64.tar.gz
tar -xzf mediamtx_v1.9.3_linux_amd64.tar.gz

# Run with our config
./mediamtx mediamtx.yml
```

## Features

- **WHIP Ingest**: Publish streams via WebRTC (OBS 30+, browser, etc.)
- **WHEP Playback**: Watch streams with ultra-low latency
- **SFU Mode**: One publisher, multiple viewers
- **AI Ready**: Process frames with Python/OpenCV/PyTorch
- **Free GPU**: Leverage Colab's free GPU tier

## Use Cases

1. **AI Video Processing**: Real-time object detection, pose estimation
2. **Live Transcription**: Speech-to-text on live streams
3. **Interactive Demos**: Low-latency AI demos without infrastructure costs
4. **Prototyping**: Test WebRTC pipelines before production deployment

## Protocols Supported

| Protocol | Port | Use Case |
|----------|------|----------|
| WHIP | 8889 | WebRTC publish (ingest) |
| WHEP | 8889 | WebRTC subscribe (playback) |
| RTSP | 8554 | Traditional streaming |
| HLS | 8888 | Fallback playback |

## Limitations

- **Session Duration**: Colab sessions timeout after ~12 hours (or less on free tier)
- **Latency**: TURN relay adds ~50-200ms vs direct WebRTC
- **Bandwidth**: Colab network may throttle high bitrate streams
- **Not for Production**: Use for development and testing only

## Files

```
colastream/
├── notebooks/
│   └── mediamtx_sfu.ipynb    # Main Colab notebook
├── web/
│   └── client.html           # Test client for WHIP/WHEP
├── configs/
│   └── mediamtx.yml          # MediaMTX configuration
└── README.md
```

## Related Projects

- [MediaMTX](https://github.com/bluenviron/mediamtx) - The SFU server
- [VDO.Ninja](https://github.com/steveseguin/vdo.ninja) - P2P WebRTC
- [OBS Studio](https://obsproject.com/) - WHIP-capable streaming software

## License

MIT License - See LICENSE file
