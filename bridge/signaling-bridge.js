/**
 * VDO.Ninja to MediaMTX Signaling Bridge
 *
 * Runs on Google Colab to bridge VDO.Ninja signaling to local MediaMTX.
 * Browsers connect via VDO.Ninja SDK, send WHIP/WHEP requests over data channel,
 * and this bridge proxies them to MediaMTX.
 *
 * No HTTP tunnel required!
 */

const { VDONinjaSDK } = require('./vdoninja-sdk-node.js');

class SignalingBridge {
    constructor(options = {}) {
        this.roomId = options.room || 'colastream-' + Math.random().toString(36).substring(2, 8);
        this.mediaServerUrl = options.mediaServerUrl || 'http://localhost:8889';
        this.sdk = null;
        this.clients = new Map(); // Track connected clients
    }

    async start() {
        console.log('Starting VDO.Ninja Signaling Bridge...');
        console.log(`Room ID: ${this.roomId}`);
        console.log(`MediaMTX URL: ${this.mediaServerUrl}`);

        this.sdk = new VDONinjaSDK({
            room: this.roomId,
            streamID: 'colastream-server',
            debug: false
        });

        // Handle incoming data channel messages
        this.sdk.addEventListener('dataReceived', async (event) => {
            const { data, UUID } = event.detail;
            await this.handleMessage(data, UUID);
        });

        // Track peer connections
        this.sdk.addEventListener('peerConnected', (event) => {
            const { UUID } = event.detail;
            console.log(`Client connected: ${UUID}`);
            this.clients.set(UUID, { connected: true });
        });

        this.sdk.addEventListener('peerDisconnected', (event) => {
            const { UUID } = event.detail;
            console.log(`Client disconnected: ${UUID}`);
            this.clients.delete(UUID);
        });

        // Connect and announce
        await this.sdk.connect();
        await this.sdk.announce({ streamID: 'colastream-server' });

        console.log('\n========================================');
        console.log('BRIDGE READY');
        console.log('========================================');
        console.log(`Room ID for clients: ${this.roomId}`);
        console.log('Waiting for browser connections...');
        console.log('========================================\n');

        return this.roomId;
    }

    async handleMessage(data, clientUUID) {
        try {
            const message = typeof data === 'string' ? JSON.parse(data) : data;

            if (message.type === 'whip' || message.type === 'whep') {
                await this.handleSignaling(message, clientUUID);
            } else if (message.type === 'ping') {
                this.sdk.sendData(JSON.stringify({ type: 'pong' }), clientUUID);
            }
        } catch (e) {
            console.error('Error handling message:', e);
            this.sdk.sendData(JSON.stringify({
                type: 'error',
                error: e.message
            }), clientUUID);
        }
    }

    async handleSignaling(message, clientUUID) {
        const { type, streamPath, sdp, requestId } = message;
        const endpoint = type === 'whip' ? 'whip' : 'whep';
        const url = `${this.mediaServerUrl}/${streamPath}/${endpoint}`;

        console.log(`[${clientUUID.substring(0, 8)}] ${type.toUpperCase()} request for /${streamPath}`);

        try {
            // Proxy the SDP to MediaMTX
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/sdp' },
                body: sdp
            });

            if (!response.ok) {
                throw new Error(`MediaMTX error: ${response.status}`);
            }

            const answerSdp = await response.text();

            // Send answer back to client
            this.sdk.sendData(JSON.stringify({
                type: `${type}-answer`,
                requestId,
                sdp: answerSdp,
                iceServers: await this.getIceServers()
            }), clientUUID);

            console.log(`[${clientUUID.substring(0, 8)}] ${type.toUpperCase()} answer sent`);

        } catch (e) {
            console.error(`[${clientUUID.substring(0, 8)}] Error:`, e.message);
            this.sdk.sendData(JSON.stringify({
                type: 'error',
                requestId,
                error: e.message
            }), clientUUID);
        }
    }

    async getIceServers() {
        // Fetch VDO.Ninja TURN servers for clients to use
        try {
            const response = await fetch('https://turnservers.vdo.ninja/');
            const data = await response.json();
            return data.servers.map(s => ({
                urls: s.urls,
                username: s.username,
                credential: s.credential
            }));
        } catch (e) {
            return [{ urls: 'stun:stun.l.google.com:19302' }];
        }
    }

    getStats() {
        return {
            room: this.roomId,
            connectedClients: this.clients.size,
            clients: Array.from(this.clients.keys())
        };
    }

    async stop() {
        if (this.sdk) {
            this.sdk.disconnect();
        }
    }
}

module.exports = { SignalingBridge };

// Run if executed directly
if (require.main === module) {
    const bridge = new SignalingBridge({
        room: process.argv[2] || undefined
    });

    bridge.start().catch(console.error);

    // Handle shutdown
    process.on('SIGINT', () => {
        console.log('\nShutting down bridge...');
        bridge.stop();
        process.exit(0);
    });
}
