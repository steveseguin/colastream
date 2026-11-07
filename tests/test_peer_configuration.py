"""Offline regressions using the real aiortc peer-connection implementation."""

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
import signaling_bridge


class PeerConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def check_configuration(self, servers):
        bridge = signaling_bridge.SignalingBridge(room_id='offline-test')
        bridge.ice_servers = copy.deepcopy(servers)
        try:
            # Record the constructor argument without replacing aiortc behavior.
            with patch.object(signaling_bridge, 'RTCPeerConnection', wraps=RTCPeerConnection) as constructor:
                pc = await bridge.create_peer_connection('test-peer')

            config = constructor.call_args.kwargs['configuration']
            if servers:
                self.assertIsInstance(config, RTCConfiguration)
                self.assertEqual(len(config.iceServers), len(servers))
                for actual, expected in zip(config.iceServers, servers):
                    self.assertIsInstance(actual, RTCIceServer)
                    self.assertEqual(actual.urls, expected['urls'])
                    self.assertEqual(actual.username, expected.get('username'))
                    self.assertEqual(actual.credential, expected.get('credential'))
            else:
                # Leave aiortc's default configuration in place when unavailable.
                self.assertFalse(config)

            self.assertIs(bridge.peer_connections['test-peer'], pc)
            channel = bridge.data_channels['test-peer']
            self.assertEqual(channel.label, 'colastream')
            self.assertTrue(channel.ordered)
            # Creating an offer exercises real SCTP/DTLS setup without gathering
            # candidates, opening sockets, or contacting STUN/TURN servers.
            offer = await pc.createOffer()
            self.assertEqual(offer.type, 'offer')
            self.assertIn('m=application ', offer.sdp)
            self.assertEqual(bridge.ice_servers, servers)
        finally:
            await bridge.stop()
        self.assertEqual(pc.connectionState, 'closed')

    async def test_fallback_stun_server(self):
        await self.check_configuration([
            {'urls': 'stun:stun.example.invalid:3478'},
        ])

    async def test_turn_credentials_and_multiple_servers(self):
        await self.check_configuration([
            {'urls': 'stun:stun.example.invalid:3478'},
            {'urls': 'turn:turn.example.invalid:3478',
             'username': 'test-user', 'credential': 'test-password'},
        ])

    async def test_server_with_multiple_urls(self):
        await self.check_configuration([
            {'urls': ['turn:turn.example.invalid:3478',
                      'turns:turn.example.invalid:5349'],
             'username': 'test-user', 'credential': 'test-password'},
        ])

    async def test_unset_servers(self):
        await self.check_configuration(None)

    async def test_empty_servers(self):
        await self.check_configuration([])


if __name__ == '__main__':
    unittest.main()
