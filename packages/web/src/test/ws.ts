import type { WsEventHandler, WsInboundMessage } from '@/lib/api/websocket';

export class FakeWebSocket {
  private listeners = new Map<string, Set<WsEventHandler>>();
  private _connected = false;

  on(type: string, handler: WsEventHandler): () => void {
    let handlers = this.listeners.get(type);
    if (!handlers) {
      handlers = new Set();
      this.listeners.set(type, handlers);
    }
    handlers.add(handler);
    return () => {
      handlers.delete(handler);
    };
  }

  isConnected(): boolean {
    return this._connected;
  }

  setConnected(connected: boolean): void {
    this._connected = connected;
  }

  _emit(type: string, data: Partial<WsInboundMessage> = {}): void {
    const msg = { t: type, ...data } as WsInboundMessage;
    const handlers = this.listeners.get(type);
    if (handlers) {
      for (const handler of handlers) {
        handler(msg);
      }
    }
  }

  connect(): void {
    this._connected = true;
  }

  disconnect(): void {
    this._connected = false;
  }

  configure(): void {}
  subscribeToBoardUpdates(): void {}
  send(): void {}
  startRun(): void {}
  cancelRun(): void {}
  subscribeToChatSession(): void {}
  sendChatMessage(): void {}
}
