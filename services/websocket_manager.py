import asyncio
import json
import websockets
from typing import Dict, Callable, Any, Optional, List, Union
from datetime import datetime

from utils.logger import get_logger
from utils.helpers import AsyncEventEmitter

class WebSocketManager:
    """
    Manages WebSocket connections for real-time data streams
    Converts callback-based WebSocket patterns to async event-driven architecture
    """
    
    def __init__(self, base_url: str = "wss://stream.binance.com:9443/ws/"):
        self.base_url = base_url
        self.logger = get_logger(__name__)
        self.connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.event_emitter = AsyncEventEmitter()
        self.running = False
        self._connection_tasks: Dict[str, asyncio.Task] = {}
        self._reconnect_delays = {}
        self.max_reconnect_delay = 60
        self.initial_reconnect_delay = 1
    
    async def start(self):
        """Start WebSocket manager"""
        self.running = True
        self.logger.info("WebSocket manager started")
    
    async def stop(self):
        """Stop WebSocket manager and close all connections"""
        self.running = False
        
        # Cancel all connection tasks
        for stream, task in self._connection_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        tasks = []
        for stream in list(self.connections.keys()):
            tasks.append(self._close_connection(stream))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.connections.clear()
        self._connection_tasks.clear()
        self._reconnect_delays.clear()
        
        self.logger.info("WebSocket manager stopped")
    
    # ==================== SUBSCRIPTION METHODS ====================
    
    async def subscribe_ticker(self, symbol: str, callback: Optional[Callable] = None) -> str:
        """
        Subscribe to ticker updates
        Returns event name for manual event handling if callback not provided
        """
        stream = f"{symbol.lower()}@ticker"
        event_name = f"ticker_{symbol.lower()}"
        
        if callback:
            await self.event_emitter.on(event_name, callback)
        
        await self._ensure_connection(stream)
        return event_name
    
    async def subscribe_kline(self, symbol: str, interval: str, callback: Optional[Callable] = None) -> str:
        """Subscribe to kline/candlestick updates"""
        stream = f"{symbol.lower()}@kline_{interval}"
        event_name = f"kline_{symbol.lower()}_{interval}"
        
        if callback:
            await self.event_emitter.on(event_name, callback)
        
        await self._ensure_connection(stream)
        return event_name
    
    async def subscribe_depth(self, symbol: str, level: Optional[int] = None, callback: Optional[Callable] = None) -> str:
        """Subscribe to order book depth updates"""
        if level:
            stream = f"{symbol.lower()}@depth{level}"
        else:
            stream = f"{symbol.lower()}@depth"
        
        event_name = f"depth_{symbol.lower()}"
        
        if callback:
            await self.event_emitter.on(event_name, callback)
        
        await self._ensure_connection(stream)
        return event_name
    
    async def subscribe_trade(self, symbol: str, callback: Optional[Callable] = None) -> str:
        """Subscribe to trade updates"""
        stream = f"{symbol.lower()}@trade"
        event_name = f"trade_{symbol.lower()}"
        
        if callback:
            await self.event_emitter.on(event_name, callback)
        
        await self._ensure_connection(stream)
        return event_name
    
    async def subscribe_user_data(self, listen_key: str, callback: Optional[Callable] = None) -> str:
        """Subscribe to user data stream (account updates, order updates)"""
        stream = listen_key
        event_name = "user_data"
        
        if callback:
            await self.event_emitter.on(event_name, callback)
        
        await self._ensure_connection(stream, is_user_stream=True)
        return event_name
    
    # ==================== EVENT HANDLING ====================
    
    async def on(self, event: str, callback: Callable):
        """Register event listener"""
        await self.event_emitter.on(event, callback)
    
    async def off(self, event: str, callback: Callable):
        """Remove event listener"""
        await self.event_emitter.remove_listener(event, callback)
    
    async def emit(self, event: str, *args, **kwargs):
        """Emit event (for testing purposes)"""
        await self.event_emitter.emit(event, *args, **kwargs)
    
    # ==================== CONNECTION MANAGEMENT ====================
    
    async def _ensure_connection(self, stream: str, is_user_stream: bool = False):
        """Ensure WebSocket connection exists for stream"""
        if stream not in self._connection_tasks:
            task = asyncio.create_task(self._maintain_connection(stream, is_user_stream))
            self._connection_tasks[stream] = task
    
    async def _maintain_connection(self, stream: str, is_user_stream: bool = False):
        """Maintain WebSocket connection with auto-reconnect"""
        reconnect_delay = self.initial_reconnect_delay
        
        while self.running:
            try:
                await self._create_connection(stream, is_user_stream)
                reconnect_delay = self.initial_reconnect_delay
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Connection failed for {stream}: {e}")
                
                if self.running:
                    self.logger.info(f"Reconnecting to {stream} in {reconnect_delay}s")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, self.max_reconnect_delay)
    
    async def _create_connection(self, stream: str, is_user_stream: bool = False):
        """Create WebSocket connection"""
        if is_user_stream:
            url = f"wss://stream.binance.com:9443/ws/{stream}"
        else:
            url = f"{self.base_url}{stream}"
        
        self.logger.info(f"Connecting to WebSocket: {stream}")
        
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as websocket:
                self.connections[stream] = websocket
                self.logger.info(f"Connected to WebSocket: {stream}")
                await self._listen(stream, websocket)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning(f"WebSocket connection closed: {stream}")
        except Exception as e:
            self.logger.error(f"WebSocket error for {stream}: {e}")
            raise
        finally:
            if stream in self.connections:
                del self.connections[stream]
    
    async def _listen(self, stream: str, websocket):
        """Listen for messages on WebSocket connection"""
        try:
            async for message in websocket:
                if not self.running:
                    break
                
                try:
                    data = json.loads(message)
                    await self._process_message(stream, data)
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse WebSocket message for {stream}: {e}")
                except Exception as e:
                    self.logger.error(f"Error processing WebSocket message for {stream}: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning(f"WebSocket connection closed during listen: {stream}")
        except Exception as e:
            self.logger.error(f"Error in WebSocket listener for {stream}: {e}")
    
    async def _process_message(self, stream: str, data: Dict[str, Any]):
        """Process incoming WebSocket message and emit appropriate events"""
        try:
            event_name = self._get_event_name(stream, data)
            
            if event_name:
                data['_stream'] = stream
                data['_timestamp'] = datetime.now()
                await self.event_emitter.emit(event_name, data)
                
        except Exception as e:
            self.logger.error(f"Error processing message for {stream}: {e}")
    
    def _get_event_name(self, stream: str, data: Dict[str, Any]) -> Optional[str]:
        """Determine event name based on stream and message data"""
        try:
            if '@ticker' in stream:
                symbol = data.get('s', '').lower()
                return f"ticker_{symbol}"
            elif '@kline' in stream:
                symbol = data.get('s', '').lower()
                interval = data.get('k', {}).get('i', '')
                return f"kline_{symbol}_{interval}"
            elif '@depth' in stream:
                symbol = stream.split('@')[0]
                return f"depth_{symbol}"
            elif '@trade' in stream:
                symbol = data.get('s', '').lower()
                return f"trade_{symbol}"
            elif len(stream) == 60:  # User data stream
                return "user_data"
            else:
                return f"unknown_{stream}"
                
        except Exception as e:
            self.logger.error(f"Error determining event name for {stream}: {e}")
            return None
    
    async def _close_connection(self, stream: str):
        """Close a specific WebSocket connection"""
        try:
            if stream in self.connections:
                await self.connections[stream].close()
                del self.connections[stream]
                self.logger.info(f"Closed WebSocket connection: {stream}")
                
            if stream in self._connection_tasks:
                self._connection_tasks[stream].cancel()
                del self._connection_tasks[stream]
                
        except Exception as e:
            self.logger.error(f"Error closing WebSocket connection {stream}: {e}")
    
    async def unsubscribe(self, stream: str):
        """Unsubscribe from a stream"""
        await self._close_connection(stream)
        self.logger.info(f"Unsubscribed from {stream}")
    
    async def get_active_connections(self) -> List[str]:
        """Get list of active WebSocket connections"""
        return list(self.connections.keys())
    
    async def is_connected(self, stream: str) -> bool:
        """Check if stream is connected"""
        return stream in self.connections
