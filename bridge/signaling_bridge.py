#!/usr/bin/env python3
"""
ColaStream Signaling Bridge (Python)

Bridges VDO.Ninja signaling to local MediaMTX.
Browsers connect via VDO.Ninja, this bridge proxies WHIP/WHEP to MediaMTX.
"""

import asyncio
import json
import random
import string
import sys
import aiohttp
import websockets

class SignalingBridge:
    def __init__(self, room_id=None, media_server_url='http://localhost:8889'):
        self.room_id = room_id or 'colastream-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.media_server_url = media_server_url
        self.ws = None
        self.my_uuid = None
        self.ice_servers = None
        self.connected_peers = set()
        self.data_channels = {}  # peer_uuid -> list of pending messages

    async def fetch_turn_servers(self):
        """Fetch TURN servers from VDO.Ninja"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://turnservers.vdo.ninja/', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    self.ice_servers = [
                        {'urls': s.get('urls', []), 'username': s.get('username', ''), 'credential': s.get('credential', '')}
                        for s in data.get('servers', [])
                    ]
                    print(f"Fetched {len(self.ice_servers)} TURN servers")
        except Exception as e:
            print(f"Using default STUN server ({e})")
            self.ice_servers = [{'urls': ['stun:stun.l.google.com:19302']}]

    async def connect(self):
        """Connect to VDO.Ninja signaling server"""
        uri = 'wss://wss.vdo.ninja'

        try:
            self.ws = await websockets.connect(
                uri,
                additional_headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Origin': 'https://vdo.ninja'
                }
            )
            print("Connected to VDO.Ninja signaling")
        except Exception as e:
            raise Exception(f"Failed to connect to signaling server: {e}")

    async def join_room(self):
        """Join the room and announce our presence"""
        # Join room
        await self.ws.send(json.dumps({
            'request': 'joinroom',
            'roomid': self.room_id
        }))

        # Wait for response
        response = await self.ws.recv()
        msg = json.loads(response)

        if msg.get('UUID'):
            self.my_uuid = msg.get('UUID')

        # Announce as server
        await self.ws.send(json.dumps({
            'request': 'seed',
            'streamID': 'colastream-server'
        }))

        print(f"Joined room: {self.room_id}")

    async def handle_message(self, msg):
        """Handle incoming signaling messages"""
        try:
            data = json.loads(msg) if isinstance(msg, str) else msg
        except:
            return

        request = data.get('request')
        sender_uuid = data.get('UUID')

        if request == 'offerSDP':
            # Someone wants to connect to us
            print(f"[+] Peer requesting connection: {sender_uuid[:8] if sender_uuid else 'unknown'}...")
            self.connected_peers.add(sender_uuid)

        elif request == 'listing':
            # Room member list
            members = data.get('list', [])
            print(f"Room has {len(members)} members")

        elif data.get('datachannel'):
            # Data channel message - this is where WHIP/WHEP requests come
            await self.handle_data_message(data, sender_uuid)

        elif data.get('sdp'):
            # SDP from peer - could be offer or answer
            pass  # We handle this in data channel messages

    async def handle_data_message(self, data, sender_uuid):
        """Handle data channel messages (WHIP/WHEP requests)"""
        try:
            payload = data.get('datachannel', {})
            if isinstance(payload, str):
                payload = json.loads(payload)

            msg_type = payload.get('type')

            if msg_type in ('whip', 'whep'):
                await self.handle_signaling(payload, sender_uuid)
            elif msg_type == 'ping':
                await self.send_to_peer(sender_uuid, {'type': 'pong'})

        except Exception as e:
            print(f"Error handling data message: {e}")

    async def handle_signaling(self, message, client_uuid):
        """Proxy WHIP/WHEP to local MediaMTX"""
        msg_type = message.get('type')
        stream_path = message.get('streamPath', 'live')
        sdp = message.get('sdp')
        request_id = message.get('requestId')

        endpoint = 'whip' if msg_type == 'whip' else 'whep'
        url = f"{self.media_server_url}/{stream_path}/{endpoint}"

        short_uuid = client_uuid[:8] if client_uuid else 'unknown'
        print(f"[{short_uuid}] {msg_type.upper()} /{stream_path}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={'Content-Type': 'application/sdp'},
                    data=sdp
                ) as resp:
                    if resp.status != 200 and resp.status != 201:
                        text = await resp.text()
                        raise Exception(f"MediaMTX {resp.status}: {text[:100]}")

                    answer_sdp = await resp.text()

            # Send answer back
            await self.send_to_peer(client_uuid, {
                'type': f'{msg_type}-answer',
                'requestId': request_id,
                'sdp': answer_sdp,
                'iceServers': self.ice_servers
            })

            print(f"[{short_uuid}] {msg_type.upper()} answer sent")

        except Exception as e:
            print(f"[{short_uuid}] Error: {e}")
            await self.send_to_peer(client_uuid, {
                'type': 'error',
                'requestId': request_id,
                'error': str(e)
            })

    async def send_to_peer(self, peer_uuid, data):
        """Send data to a peer via signaling"""
        if self.ws:
            await self.ws.send(json.dumps({
                'UUID': peer_uuid,
                'datachannel': json.dumps(data)
            }))

    async def run(self):
        """Main loop"""
        print('=' * 60)
        print('ColaStream Signaling Bridge (Python)')
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

        # Message loop
        try:
            async for message in self.ws:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
        except Exception as e:
            print(f"Error: {e}")

    async def stop(self):
        """Stop the bridge"""
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
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
