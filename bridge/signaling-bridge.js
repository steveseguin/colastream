#!/usr/bin/env node
/**
 * ColaStream Signaling Bridge
 *
 * Bridges VDO.Ninja signaling to local MediaMTX.
 * Browsers connect via VDO.Ninja SDK, this bridge proxies WHIP/WHEP to MediaMTX.
 */

// Polyfill WebSocket for Node.js with proper headers
if (typeof WebSocket === 'undefined') {
    const OriginalWebSocket = require('ws');

    // Wrapper that adds headers VDO.Ninja expects
    global.WebSocket = class WebSocketWrapper extends OriginalWebSocket {
        constructor(url, protocols) {
            super(url, protocols, {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Origin': 'https://vdo.ninja'
                }
            });
        }
    };
}

const VDONinjaSDK = require('./vdoninja-sdk.js');

class SignalingBridge {
    constructor(options = {}) {
        this.roomId = options.room || 'colastream-' + Math.random().toString(36).substring(2, 8);
        this.mediaServerUrl = options.mediaServerUrl || 'http://localhost:8889';
        this.sdk = null;
        this.connectedPeers = new Set();
        this.iceServers = null;
    }

    async start() {
        console.log('='.repeat(60));
        console.log('ColaStream Signaling Bridge');
        console.log('='.repeat(60));
        console.log(`Room ID: ${this.roomId}`);
        console.log(`MediaMTX: ${this.mediaServerUrl}`);
        console.log('');

        // Fetch TURN servers
        await this.fetchTurnServers();

        // Initialize SDK
        this.sdk = new VDONinjaSDK({
            room: this.roomId,
            streamID: 'colastream-server',
            debug: false
        });

        // Handle data channel messages
        this.sdk.on('dataReceived', async (event) => {
            const { data, UUID } = event.detail || event;
            await this.handleMessage(data, UUID);
        });

        // Track peers
        this.sdk.on('peerConnected', (event) => {
            const detail = event.detail || event;
            const uuid = detail.UUID;
            if (uuid) {
                this.connectedPeers.add(uuid);
                console.log('[+] Client connected: ' + uuid.substring(0, 8) + '...');
            }
        });

        this.sdk.on('peerDisconnected', (event) => {
            const detail = event.detail || event;
            const uuid = detail.UUID;
            if (uuid) {
                this.connectedPeers.delete(uuid);
                console.log('[-] Client disconnected: ' + uuid.substring(0, 8) + '...');
            }
        });

        // Connect
        try {
            await this.sdk.connect();
            await this.sdk.announce({ streamID: 'colastream-server' });

            console.log('');
            console.log('='.repeat(60));
            console.log('BRIDGE READY');
            console.log('='.repeat(60));
            console.log('');
            console.log('Publish URL:');
            console.log(`  https://steveseguin.github.io/colastream/publish.html?room=${this.roomId}`);
            console.log('');
            console.log('View URL:');
            console.log(`  https://steveseguin.github.io/colastream/view.html?room=${this.roomId}`);
            console.log('');
            console.log('Waiting for connections...');
            console.log('='.repeat(60));

            return this.roomId;
        } catch (e) {
            console.error('Failed to connect:', e.message);
            throw e;
        }
    }

    async fetchTurnServers() {
        try {
            const fetch = (await import('node-fetch')).default;
            const response = await fetch('https://turnservers.vdo.ninja/', { timeout: 5000 });
            const data = await response.json();
            this.iceServers = data.servers.map(s => ({
                urls: s.urls,
                username: s.username,
                credential: s.credential
            }));
            console.log(`Fetched ${this.iceServers.length} TURN servers`);
        } catch (e) {
            console.log('Using default STUN server');
            this.iceServers = [{ urls: 'stun:stun.l.google.com:19302' }];
        }
    }

    async handleMessage(data, clientUUID) {
        let message;
        try {
            message = typeof data === 'string' ? JSON.parse(data) : data;
        } catch (e) {
            console.error('Invalid JSON:', e.message);
            return;
        }

        const shortUUID = clientUUID ? clientUUID.substring(0, 8) : 'unknown';

        if (message.type === 'whip' || message.type === 'whep') {
            await this.handleSignaling(message, clientUUID, shortUUID);
        } else if (message.type === 'ping') {
            this.sendToClient(clientUUID, { type: 'pong' });
        } else {
            console.log(`[${shortUUID}] Unknown message type: ${message.type}`);
        }
    }

    async handleSignaling(message, clientUUID, shortUUID) {
        const { type, streamPath, sdp, requestId } = message;
        const endpoint = type === 'whip' ? 'whip' : 'whep';
        const url = `${this.mediaServerUrl}/${streamPath || 'live'}/${endpoint}`;

        console.log(`[${shortUUID}] ${type.toUpperCase()} /${streamPath || 'live'}`);

        try {
            const fetch = (await import('node-fetch')).default;
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/sdp' },
                body: sdp
            });

            if (!response.ok) {
                const text = await response.text();
                throw new Error(`MediaMTX ${response.status}: ${text.substring(0, 100)}`);
            }

            const answerSdp = await response.text();

            this.sendToClient(clientUUID, {
                type: `${type}-answer`,
                requestId,
                sdp: answerSdp,
                iceServers: this.iceServers
            });

            console.log(`[${shortUUID}] ${type.toUpperCase()} answer sent`);

        } catch (e) {
            console.error(`[${shortUUID}] Error: ${e.message}`);
            this.sendToClient(clientUUID, {
                type: 'error',
                requestId,
                error: e.message
            });
        }
    }

    sendToClient(clientUUID, data) {
        if (this.sdk) {
            try {
                this.sdk.sendData(JSON.stringify(data), { target: clientUUID });
            } catch (e) {
                console.error('Failed to send:', e.message);
            }
        }
    }

    stop() {
        if (this.sdk) {
            this.sdk.disconnect();
            this.sdk = null;
        }
        console.log('Bridge stopped');
    }
}

// Main
async function main() {
    const roomId = process.argv[2] || undefined;

    const bridge = new SignalingBridge({ room: roomId });

    process.on('SIGINT', () => {
        console.log('\nShutting down...');
        bridge.stop();
        process.exit(0);
    });

    try {
        await bridge.start();
    } catch (e) {
        console.error('Bridge failed to start:', e);
        process.exit(1);
    }
}

main();

module.exports = { SignalingBridge };
