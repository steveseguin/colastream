#!/usr/bin/env python3
"""
ColaStream Signaling Bridge (Python + aiortc)

Uses VDO.Ninja for WebRTC signaling, proxies WHIP/WHEP to local MediaMTX.
No tunnels needed - VDO.Ninja handles NAT traversal.
"""

import asyncio
import json
import random
import string
import sys
import functools
import aiohttp
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel
from aiortc.contrib.signaling import object_to_string, object_from_string

# Force unbuffered output
print = functools.partial(print, flush=True)


class SignalingBridge:
    def __init__(self, room_id=None, media_server_url='http://localhost:8889'):
        self.room_id = room_id or 'colastream-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.media_server_url = media_server_url
        self.ws = None
        self.my_uuid = None
        self.ice_servers = None
        self.peer_connections = {}  # uuid -> RTCPeerConnection
        self.data_channels = {}  # uuid -> RTCDataChannel

    async def fetch_turn_servers(self):
        """Fetch TURN servers from VDO.Ninja"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://turnservers.vdo.ninja/', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    servers = data.get('servers', [])
                    self.ice_servers = []
                    for s in servers:
                        urls = s.get('urls', [])
                        if isinstance(urls, str):
                            urls = [urls]
                        for url in urls:
                            server = {'urls': url}
                            if s.get('username'):
                                server['username'] = s['username']
                            if s.get('credential'):
                                server['credential'] = s['credential']
                            self.ice_servers.append(server)
                    print(f"Fetched {len(self.ice_servers)} ICE servers")
        except Exception as e:
            print(f"Using default STUN server ({e})")
            self.ice_servers = [{'urls': 'stun:stun.l.google.com:19302'}]

    async def connect(self):
        """Connect to VDO.Ninja signaling server"""
        uri = 'wss://wss.vdo.ninja'

        try:
            self.ws = await websockets.connect(uri)
            print("Connected to VDO.Ninja signaling")
        except Exception as e:
            raise Exception(f"Failed to connect: {e}")

    async def join_room(self):
        """Join room and announce presence"""
        # Join room
        await self.ws.send(json.dumps({
            'request': 'joinroom',
            'roomid': self.room_id
        }))

        # Seed our stream
        await self.ws.send(json.dumps({
            'request': 'seed',
            'streamID': 'colastream-server'
        }))

        print(f"Joined room: {self.room_id}")

    async def create_peer_connection(self, peer_uuid):
        """Create a new WebRTC peer connection"""
        config = {'iceServers': self.ice_servers} if self.ice_servers else {}
        pc = RTCPeerConnection(configuration=config)
        self.peer_connections[peer_uuid] = pc

        # Create data channel for WHIP/WHEP messaging
        dc = pc.createDataChannel('colastream', ordered=True)
        self.data_channels[peer_uuid] = dc

        @dc.on('open')
        def on_open():
            print(f"[{peer_uuid[:8]}] Data channel open")

        @dc.on('message')
        def on_message(message):
            asyncio.create_task(self.handle_data_message(message, peer_uuid))

        @pc.on('icecandidate')
        async def on_ice(candidate):
            if candidate:
                await self.ws.send(json.dumps({
                    'UUID': peer_uuid,
                    'candidate': candidate.to_json() if hasattr(candidate, 'to_json') else str(candidate)
                }))

        @pc.on('datachannel')
        def on_datachannel(channel):
            self.data_channels[peer_uuid] = channel

            @channel.on('message')
            def on_msg(msg):
                asyncio.create_task(self.handle_data_message(msg, peer_uuid))

        return pc

    async def handle_message(self, msg_str):
        """Handle incoming signaling messages"""
        try:
            msg = json.loads(msg_str)
        except:
            return

        request = msg.get('request')
        sender = msg.get('UUID')

        # Debug: log all messages
        if request:
            print(f"[Signal] request={request} from={sender[:8] if sender else 'server'}")
        elif msg.get('sdp'):
            print(f"[Signal] SDP type={msg.get('type')} from={sender[:8] if sender else '?'}")
        elif msg.get('candidate'):
            print(f"[Signal] ICE candidate from={sender[:8] if sender else '?'}")

        if request == 'offerSDP':
            # Peer wants us to send them an offer
            print(f"[{sender[:8] if sender else '?'}] Requesting connection...")
            await self.send_offer(sender)

        elif request == 'listing':
            members = msg.get('list', [])
            print(f"Room has {len(members)} members")

        elif msg.get('sdp'):
            # Received SDP answer
            await self.handle_sdp(msg, sender)

        elif msg.get('candidate'):
            # ICE candidate
            await self.handle_ice_candidate(msg, sender)

    async def send_offer(self, peer_uuid):
        """Send WebRTC offer to peer"""
        pc = await self.create_peer_connection(peer_uuid)

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        await self.ws.send(json.dumps({
            'UUID': peer_uuid,
            'sdp': pc.localDescription.sdp,
            'type': pc.localDescription.type
        }))

    async def handle_sdp(self, msg, sender):
        """Handle incoming SDP"""
        sdp_type = msg.get('type', 'answer')
        sdp = msg.get('sdp')

        if sender not in self.peer_connections:
            # Create PC for incoming offer
            pc = await self.create_peer_connection(sender)
        else:
            pc = self.peer_connections[sender]

        desc = RTCSessionDescription(sdp=sdp, type=sdp_type)
        await pc.setRemoteDescription(desc)

        if sdp_type == 'offer':
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await self.ws.send(json.dumps({
                'UUID': sender,
                'sdp': pc.localDescription.sdp,
                'type': pc.localDescription.type
            }))

    async def handle_ice_candidate(self, msg, sender):
        """Handle ICE candidate"""
        if sender in self.peer_connections:
            # aiortc handles candidates automatically via trickle ICE
            pass

    async def handle_data_message(self, data, peer_uuid):
        """Handle data channel messages (WHIP/WHEP requests)"""
        try:
            if isinstance(data, bytes):
                data = data.decode()
            msg = json.loads(data)
        except:
            return

        msg_type = msg.get('type')
        short = peer_uuid[:8] if peer_uuid else '?'

        if msg_type in ('whip', 'whep'):
            await self.proxy_to_mediamtx(msg, peer_uuid)
        elif msg_type == 'ping':
            await self.send_data(peer_uuid, {'type': 'pong'})
        else:
            print(f"[{short}] Unknown: {msg_type}")

    async def proxy_to_mediamtx(self, msg, peer_uuid):
        """Proxy WHIP/WHEP to local MediaMTX"""
        msg_type = msg.get('type')
        stream_path = msg.get('streamPath', 'live')
        sdp = msg.get('sdp')
        request_id = msg.get('requestId')

        endpoint = 'whip' if msg_type == 'whip' else 'whep'
        url = f"{self.media_server_url}/{stream_path}/{endpoint}"
        short = peer_uuid[:8] if peer_uuid else '?'

        print(f"[{short}] {msg_type.upper()} /{stream_path}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers={'Content-Type': 'application/sdp'}, data=sdp) as resp:
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        raise Exception(f"MediaMTX {resp.status}: {text[:100]}")
                    answer_sdp = await resp.text()

            await self.send_data(peer_uuid, {
                'type': f'{msg_type}-answer',
                'requestId': request_id,
                'sdp': answer_sdp,
                'iceServers': self.ice_servers
            })
            print(f"[{short}] {msg_type.upper()} answer sent")

        except Exception as e:
            print(f"[{short}] Error: {e}")
            await self.send_data(peer_uuid, {
                'type': 'error',
                'requestId': request_id,
                'error': str(e)
            })

    async def send_data(self, peer_uuid, data):
        """Send data to peer via data channel"""
        if peer_uuid in self.data_channels:
            dc = self.data_channels[peer_uuid]
            if dc.readyState == 'open':
                dc.send(json.dumps(data))

    async def run(self):
        """Main loop"""
        print('=' * 60)
        print('ColaStream Signaling Bridge')
        print('=' * 60)
        print(f'Room ID: {self.room_id}')
        print(f'MediaMTX: {self.media_server_url}')
        print('')

        await self.fetch_turn_servers()
        await self.connect()
        await self.join_room()

        print('')
        print('=' * 60)
        print('BRIDGE READY')
        print('=' * 60)
        print('')
        print('Publish URL:')
        print(f'  https://steveseguin.github.io/colastream/publish.html?room={self.room_id}')
        print('')
        print('View URL:')
        print(f'  https://steveseguin.github.io/colastream/view.html?room={self.room_id}')
        print('')
        print('Waiting for connections...')
        print('=' * 60)

        try:
            async for message in self.ws:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")

    async def stop(self):
        """Cleanup"""
        for pc in self.peer_connections.values():
            await pc.close()
        if self.ws:
            await self.ws.close()
        print("Bridge stopped")


async def main():
    room_id = sys.argv[1] if len(sys.argv) > 1 else None
    bridge = SignalingBridge(room_id=room_id)

    try:
        await bridge.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await bridge.stop()
    except Exception as e:
        print(f"Bridge failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
