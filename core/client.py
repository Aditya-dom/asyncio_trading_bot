import asyncio
import aiohttp
import hashlib
import hmac
import json
import time
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode
from datetime import datetime

from config.settings import BinanceConfig
from utils.logger import get_logger
from core.exceptions import *
from core.models import *

class AsyncBinanceClient:
    """
    Async wrapper for Binance API that converts synchronous/callback-based
    operations into asyncio-compatible coroutines.
    """
    
    def __init__(self, config: BinanceConfig):
        self.config = config
        self.logger = get_logger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0
        self._request_lock = asyncio.Lock()
        
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        """Initialize the HTTP session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    'X-MBX-APIKEY': self.config.api_key,
                    'Content-Type': 'application/json'
                }
            )
            self.logger.info(f"Connected to Binance API: {self.config.base_url}")
    
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            self.logger.info("Disconnected from Binance API")
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for authenticated requests"""
        query_string = urlencode(params, True)
        return hmac.new(
            self.config.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _rate_limit(self):
        """Implement rate limiting to prevent API bans"""
        async with self._request_lock:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            if time_since_last < self.config.rate_limit_delay:
                await asyncio.sleep(self.config.rate_limit_delay - time_since_last)
            self._last_request_time = time.time()
    
    async def _request(self, method: str, endpoint: str, signed: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Make async HTTP request to Binance API with retry logic
        Converts sync/callback patterns to async/await
        """
        await self._rate_limit()
        
        if not self.session:
            await self.connect()
        
        url = f"{self.config.base_url}{endpoint}"
        params = kwargs.get('params', {})
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
        
        for attempt in range(self.config.max_retries):
            try:
                self.logger.debug(f"Making request: {method} {url} (attempt {attempt + 1})")
                
                async with self.session.request(method, url, params=params) as response:
                    response_text = await response.text()
                    
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        data = {'msg': response_text}
                    
                    if response.status == 200:
                        return data
                    elif response.status == 429:
                        self.logger.warning(f"Rate limit hit, attempt {attempt + 1}")
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        raise RateLimitError("Rate limit exceeded")
                    elif response.status == 401:
                        raise AuthenticationError("Invalid API credentials")
                    else:
                        error_msg = data.get('msg', f'HTTP {response.status}')
                        error_code = data.get('code')
                        self.logger.error(f"API Error: {error_msg} (Code: {error_code})")
                        raise BinanceAPIError(error_msg, error_code)
                        
            except aiohttp.ClientError as e:
                self.logger.error(f"Connection error: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ConnectionError(f"Connection failed: {e}")
        
        raise BinanceAPIError("Max retries exceeded")
    
    # ==================== PUBLIC API METHODS ====================
    
    async def ping(self) -> bool:
        """Test connectivity to the Rest API"""
        try:
            await self._request('GET', '/api/v3/ping')
            return True
        except Exception:
            return False
    
    async def get_server_time(self) -> int:
        """Get server time"""
        data = await self._request('GET', '/api/v3/time')
        return data['serverTime']
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        """Get exchange information"""
        return await self._request('GET', '/api/v3/exchangeInfo')
    
    async def get_ticker(self, symbol: str) -> Ticker:
        """Get 24hr ticker price change statistics"""
        data = await self._request('GET', '/api/v3/ticker/24hr', params={'symbol': symbol})
        return Ticker(
            symbol=data['symbol'],
            price=float(data['lastPrice']),
            change_percent=float(data['priceChangePercent']),
            volume=float(data['volume']),
            timestamp=datetime.fromtimestamp(data['closeTime'] / 1000)
        )
    
    async def get_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        data = await self._request('GET', '/api/v3/ticker/price', params={'symbol': symbol})
        return float(data['price'])
    
    async def get_orderbook(self, symbol: str, limit: int = 100) -> OrderBook:
        """Get order book depth"""
        data = await self._request('GET', '/api/v3/depth', params={'symbol': symbol, 'limit': limit})
        return OrderBook(
            symbol=symbol,
            bids=data['bids'],
            asks=data['asks'],
            last_update_id=data['lastUpdateId'],
            timestamp=datetime.now()
        )
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 500) -> List[Kline]:
        """Get candlestick/kline data"""
        data = await self._request('GET', '/api/v3/klines', params={
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        })
        
        klines = []
        for item in data:
            klines.append(Kline(
                symbol=symbol,
                open_time=datetime.fromtimestamp(item[0] / 1000),
                close_time=datetime.fromtimestamp(item[6] / 1000),
                open_price=float(item[1]),
                high_price=float(item[2]),
                low_price=float(item[3]),
                close_price=float(item[4]),
                volume=float(item[5]),
                number_of_trades=item[8]
            ))
        return klines
    
    # ==================== ACCOUNT API METHODS ====================
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        return await self._request('GET', '/api/v3/account', signed=True)
    
    async def get_balances(self) -> List[Balance]:
        """Get account balances"""
        account_info = await self.get_account_info()
        balances = []
        for balance in account_info['balances']:
            free_balance = float(balance['free'])
            locked_balance = float(balance['locked'])
            if free_balance > 0 or locked_balance > 0:
                balances.append(Balance(
                    asset=balance['asset'],
                    free=free_balance,
                    locked=locked_balance
                ))
        return balances
    
    async def get_balance(self, asset: str) -> Optional[Balance]:
        """Get balance for specific asset"""
        balances = await self.get_balances()
        for balance in balances:
            if balance.asset == asset:
                return balance
        return None
    
    # ==================== TRADING API METHODS ====================
    
    async def place_order(self, symbol: str, side: OrderSide, order_type: OrderType, 
                         quantity: Optional[float] = None, price: Optional[float] = None, 
                         **kwargs) -> Order:
        """Place a new order"""
        params = {
            'symbol': symbol,
            'side': side.value,
            'type': order_type.value,
            **kwargs
        }
        
        if quantity is not None:
            params['quantity'] = quantity
        if price is not None:
            params['price'] = price
        
        # Add required parameters for limit orders
        if order_type == OrderType.LIMIT and 'timeInForce' not in params:
            params['timeInForce'] = 'GTC'
        
        data = await self._request('POST', '/api/v3/order', signed=True, params=params)
        return self._parse_order(data)
    
    async def place_market_buy(self, symbol: str, quote_order_qty: float) -> Order:
        """Place market buy order with quote quantity"""
        return await self.place_order(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quoteOrderQty=quote_order_qty
        )
    
    async def place_market_sell(self, symbol: str, quantity: float) -> Order:
        """Place market sell order"""
        return await self.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity
        )
    
    async def place_limit_order(self, symbol: str, side: OrderSide, quantity: float, price: float) -> Order:
        """Place limit order"""
        return await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price
        )
    
    async def cancel_order(self, symbol: str, order_id: int) -> Order:
        """Cancel an active order"""
        data = await self._request('DELETE', '/api/v3/order', signed=True, params={
            'symbol': symbol,
            'orderId': order_id
        })
        return self._parse_order(data)
    
    async def cancel_all_orders(self, symbol: str) -> List[Order]:
        """Cancel all open orders for a symbol"""
        data = await self._request('DELETE', '/api/v3/openOrders', signed=True, params={
            'symbol': symbol
        })
        return [self._parse_order(order) for order in data]
    
    async def get_order(self, symbol: str, order_id: int) -> Order:
        """Get order information"""
        data = await self._request('GET', '/api/v3/order', signed=True, params={
            'symbol': symbol,
            'orderId': order_id
        })
        return self._parse_order(data)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders"""
        params = {}
        if symbol:
            params['symbol'] = symbol
            
        data = await self._request('GET', '/api/v3/openOrders', signed=True, params=params)
        return [self._parse_order(order) for order in data]
    
    async def get_order_history(self, symbol: str, limit: int = 500) -> List[Order]:
        """Get order history"""
        data = await self._request('GET', '/api/v3/allOrders', signed=True, params={
            'symbol': symbol,
            'limit': limit
        })
        return [self._parse_order(order) for order in data]
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse order data from API response"""
        return Order(
            symbol=data['symbol'],
            order_id=data['orderId'],
            client_order_id=data['clientOrderId'],
            side=OrderSide(data['side']),
            type=OrderType(data['type']),
            status=OrderStatus(data['status']),
            quantity=float(data['origQty']),
            price=float(data['price']) if data['price'] != '0.00000000' else None,
            executed_quantity=float(data['executedQty']),
            quote_quantity=float(data['cummulativeQuoteQty']),
            timestamp=datetime.fromtimestamp(data['time'] / 1000),
            raw_data=data
        )
