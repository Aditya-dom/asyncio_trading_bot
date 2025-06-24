#!/usr/bin/env python3
"""
Simple Async Wrapper for Binance API
Demonstrates converting sync/callback broker APIs to async patterns
"""

import asyncio
import aiohttp
import hashlib
import hmac
import json
import time
from typing import Dict, Any, Optional
from urllib.parse import urlencode
from dataclasses import dataclass
from datetime import datetime


API_KEY = "EKAwb7t9AvEOvDktLKJEKKrl730v2x4mLmosZcdBt8kHTAyZfBa4kK5yc48SO7XF"
API_SECRET = "UJglFrlvEX76hFpsFpP1qZ5yqYo02nKuCWrotdHMC61TmlEyDsSYzAdXnEuIAVlD"
BASE_URL = "https://testnet.binance.vision"  

@dataclass
class Price:
    symbol: str
    price: float
    timestamp: datetime

class AsyncBinanceWrapper:
    """
    Simple async wrapper for Binance API
    Converts sync/blocking API calls to async/await patterns
    """
    
    def __init__(self, api_key: str, api_secret: str, base_url: str = BASE_URL):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0
        self.rate_limit_delay = 0.1  # 100ms between requests
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def connect(self):
        """Initialize HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'X-MBX-APIKEY': self.api_key}
            )
            print("Connected to Binance API")
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            print("Disconnected from Binance API")
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for authenticated requests"""
        query_string = urlencode(params, True)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _rate_limit(self):
        """Simple rate limiting to avoid API bans"""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    async def _request(self, method: str, endpoint: str, signed: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Core async HTTP request method
        This is where the sync-to-async magic happens!
        """
        await self._rate_limit()
        
        if not self.session:
            await self.connect()
        
        url = f"{self.base_url}{endpoint}"
        params = kwargs.get('params', {})
        
        # Add signature for authenticated requests
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
        
        try:
            # This converts blocking HTTP call to async
            async with self.session.request(method, url, params=params) as response:
                data = await response.json()
                
                if response.status == 200:
                    return data
                else:
                    error_msg = data.get('msg', f'HTTP {response.status}')
                    raise Exception(f"API Error: {error_msg}")
                    
        except Exception as e:
            print(f"Request failed: {e}")
            raise
    
    # ==================== PUBLIC API METHODS ====================
    
    async def ping(self) -> bool:
        """Test API connectivity"""
        try:
            await self._request('GET', '/api/v3/ping')
            return True
        except:
            return False
    
    async def get_server_time(self) -> int:
        """Get server time"""
        data = await self._request('GET', '/api/v3/time')
        return data['serverTime']
    
    async def get_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        data = await self._request('GET', '/api/v3/ticker/price', params={'symbol': symbol})
        return float(data['price'])
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get 24hr ticker statistics"""
        data = await self._request('GET', '/api/v3/ticker/24hr', params={'symbol': symbol})
        return {
            'symbol': data['symbol'],
            'price': float(data['lastPrice']),
            'change_percent': float(data['priceChangePercent']),
            'volume': float(data['volume']),
            'high': float(data['highPrice']),
            'low': float(data['lowPrice'])
        }
    
    # ==================== ACCOUNT API METHODS ====================
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information (requires authentication)"""
        return await self._request('GET', '/api/v3/account', signed=True)
    
    async def get_balances(self) -> Dict[str, float]:
        """Get account balances"""
        account_info = await self.get_account_info()
        balances = {}
        
        for balance in account_info['balances']:
            free_balance = float(balance['free'])
            if free_balance > 0:
                balances[balance['asset']] = free_balance
        
        return balances
    
    # ==================== TRADING API METHODS ====================
    
    async def place_market_buy_order(self, symbol: str, quote_amount: float) -> Dict[str, Any]:
        """Place a market buy order using quote currency amount"""
        params = {
            'symbol': symbol,
            'side': 'BUY',
            'type': 'MARKET',
            'quoteOrderQty': quote_amount
        }
        return await self._request('POST', '/api/v3/order', signed=True, params=params)
    
    async def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict[str, Any]:
        """Place a limit order"""
        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': 'LIMIT',
            'timeInForce': 'GTC',
            'quantity': quantity,
            'price': price
        }
        return await self._request('POST', '/api/v3/order', signed=True, params=params)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get open orders"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return await self._request('GET', '/api/v3/openOrders', signed=True, params=params)
    
    async def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an order"""
        params = {'symbol': symbol, 'orderId': order_id}
        return await self._request('DELETE', '/api/v3/order', signed=True, params=params)

# ==================== USAGE EXAMPLES ====================

async def example_basic_usage():
    """Basic async API usage example"""
    print("Basic Async API Usage")
    print("-" * 30)
    
    async with AsyncBinanceWrapper(API_KEY, API_SECRET) as client:
        # Test connection
        if await client.ping():
            print("API connection successful")
        else:
            print("API connection failed")
            return
        
        # Get server time
        server_time = await client.get_server_time()
        print(f"Server time: {server_time}")
        
        # Get current prices
        btc_price = await client.get_price("BTCUSDT")
        print(f"BTC Price: ${btc_price:,.2f}")
        
        eth_price = await client.get_price("ETHUSDT")
        print(f"ETH Price: ${eth_price:,.2f}")
        
        # Get detailed ticker
        ticker = await client.get_ticker("BTCUSDT")
        print(f"BTC 24h change: {ticker['change_percent']:+.2f}%")
        print(f"24h high: ${ticker['high']:,.2f}")
        print(f"24h low: ${ticker['low']:,.2f}")
        
        # Get account balances
        try:
            balances = await client.get_balances()
            print(f"Account balances: {len(balances)} assets")
            for asset, balance in list(balances.items())[:5]:  # Show first 5
                print(f"   {asset}: {balance:.6f}")
        except Exception as e:
            print(f"Could not get balances: {e}")

async def example_concurrent_prices():
    """Demonstrate concurrent API calls"""
    print("\nConcurrent Price Fetching")
    print("-" * 30)
    
    async with AsyncBinanceWrapper(API_KEY, API_SECRET) as client:
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]
        
        print(f"Fetching {len(symbols)} prices concurrently...")
        start_time = time.time()
        
        # This is the magic of async - all requests happen concurrently!
        tasks = [client.get_price(symbol) for symbol in symbols]
        prices = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start_time
        
        print("Results:")
        for symbol, price in zip(symbols, prices):
            print(f"   {symbol}: ${price:,.2f}")
        
        print(f"Completed in {elapsed:.2f} seconds")
        print(f"That's {len(symbols)/elapsed:.1f} requests per second!")

async def example_price_monitoring():
    """Simple price monitoring with async polling"""
    print("\nPrice Monitoring (10 seconds)")
    print("-" * 30)
    
    async with AsyncBinanceWrapper(API_KEY, API_SECRET) as client:
        symbol = "BTCUSDT"
        last_price = None
        
        for i in range(10):  # Monitor for 10 iterations
            try:
                current_price = await client.get_price(symbol)
                
                if last_price:
                    change = current_price - last_price
                    change_pct = (change / last_price) * 100
                    arrow = "UP" if change > 0 else "DOWN" if change < 0 else "SAME"
                    print(f"   {arrow} {symbol}: ${current_price:,.2f} ({change_pct:+.3f}%)")
                else:
                    print(f"   {symbol}: ${current_price:,.2f}")
                
                last_price = current_price
                await asyncio.sleep(1)  # Wait 1 second between updates
                
            except Exception as e:
                print(f"   Error: {e}")
                await asyncio.sleep(1)

async def example_simple_trading():
    """Simple trading example (testnet only!)"""
    print("\nSimple Trading Example")
    print("-" * 30)
    print("This will place REAL orders on TESTNET")
    
    async with AsyncBinanceWrapper(API_KEY, API_SECRET) as client:
        try:
            # Get current BTC price
            btc_price = await client.get_price("BTCUSDT")
            print(f"Current BTC price: ${btc_price:,.2f}")
            
            # Check balances
            balances = await client.get_balances()
            usdt_balance = balances.get('USDT', 0)
            print(f"USDT balance: {usdt_balance:.2f}")
            
            if usdt_balance < 10:
                print("Insufficient USDT balance for demo trade")
                return
            
            # Place a small market buy order (testnet only!)
            print("Placing small market buy order...")
            order = await client.place_market_buy_order("BTCUSDT", 10.0)  # $10 worth
            print(f"Order placed! ID: {order['orderId']}")
            print(f"   Status: {order['status']}")
            print(f"   Executed: {order['executedQty']} BTC")
            
            # Check open orders
            open_orders = await client.get_open_orders("BTCUSDT")
            print(f"Open orders: {len(open_orders)}")
            
        except Exception as e:
            print(f"Trading error: {e}")

# ==================== MAIN FUNCTION ====================

async def main():
    """Main function demonstrating all examples"""
    print("Simple Binance Async Wrapper Demo")
    print("=" * 50)
    
    # Basic usage
    await example_basic_usage()
    
    # Concurrent operations
    await example_concurrent_prices()
    
    # Price monitoring
    await example_price_monitoring()
    
    # Simple trading (uncomment if you want to test trading)
    # await example_simple_trading()
    
    print("\nAll examples completed!")
    print("This demonstrates the core async wrapper pattern:")
    print("   • Converting sync API calls to async/await")
    print("   • Concurrent operations for better performance")
    print("   • Real-time data processing with async loops")
    print("   • Clean resource management with context managers")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDemo stopped by user")
    except Exception as e:
        print(f"Error: {e}")
