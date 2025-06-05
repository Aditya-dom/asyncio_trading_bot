import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

from core.client import AsyncBinanceClient
from core.models import Order, OrderSide, OrderType, Balance
from core.exceptions import InsufficientBalanceError, OrderError
from utils.logger import get_logger
from utils.helpers import retry_async, calculate_quantity, calculate_stop_loss, calculate_take_profit

class TradingService:
    """
    Service for handling trading operations with async patterns
    Converts sync trading operations to async with proper error handling
    """
    
    def __init__(self, client: AsyncBinanceClient):
        self.client = client
        self.logger = get_logger(__name__)
        self.active_orders: Dict[int, Order] = {}
        self.position_tracker: Dict[str, Dict] = {}
        self._order_lock = asyncio.Lock()
    
    async def start(self):
        """Start trading service"""
        self.logger.info("Trading service started")
    
    async def stop(self):
        """Stop trading service"""
        self.logger.info("Trading service stopped")
    
    # ==================== ORDER PLACEMENT ====================
    
    @retry_async(max_retries=3)
    async def place_market_order(self, symbol: str, side: OrderSide, quote_quantity: float) -> Order:
        """
        Place a market order with quote quantity
        Converts sync order placement to async with proper error handling
        """
        async with self._order_lock:
            try:
                self.logger.info(f"Placing market order: {side.value} {symbol} with ${quote_quantity}")
                
                # Validate balance before placing order
                if not await self._validate_balance(symbol, side, quote_quantity=quote_quantity):
                    raise InsufficientBalanceError(f"Insufficient balance for {side.value} order")
                
                if side == OrderSide.BUY:
                    order = await self.client.place_market_buy(symbol, quote_quantity)
                else:
                    # For sell orders, we need to calculate quantity
                    current_price = await self.client.get_price(symbol)
                    quantity = quote_quantity / current_price
                    order = await self.client.place_market_sell(symbol, quantity)
                
                # Track the order
                self.active_orders[order.order_id] = order
                await self._update_position_tracker(symbol, order)
                
                self.logger.info(f"Market order placed successfully: {order.order_id}")
                return order
                
            except Exception as e:
                self.logger.error(f"Failed to place market order: {e}")
                raise OrderError(f"Market order failed: {e}")
    
    @retry_async(max_retries=3)
    async def place_limit_order(self, symbol: str, side: OrderSide, quantity: float, price: float) -> Order:
        """Place a limit order"""
        async with self._order_lock:
            try:
                self.logger.info(f"Placing limit order: {side.value} {quantity} {symbol} @ ${price}")
                
                # Validate balance
                if not await self._validate_balance(symbol, side, quantity=quantity, price=price):
                    raise InsufficientBalanceError(f"Insufficient balance for {side.value} order")
                
                order = await self.client.place_limit_order(symbol, side, quantity, price)
                
                # Track the order
                self.active_orders[order.order_id] = order
                
                self.logger.info(f"Limit order placed successfully: {order.order_id}")
                return order
                
            except Exception as e:
                self.logger.error(f"Failed to place limit order: {e}")
                raise OrderError(f"Limit order failed: {e}")
    
    @retry_async(max_retries=3)
    async def place_stop_loss_order(self, symbol: str, side: OrderSide, quantity: float, stop_price: float) -> Order:
        """Place a stop loss order"""
        try:
            self.logger.info(f"Placing stop loss: {side.value} {quantity} {symbol} @ ${stop_price}")
            
            order = await self.client.place_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.STOP_LOSS,
                quantity=quantity,
                stopPrice=stop_price
            )
            
            self.active_orders[order.order_id] = order
            self.logger.info(f"Stop loss order placed: {order.order_id}")
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to place stop loss order: {e}")
            raise OrderError(f"Stop loss order failed: {e}")
    
    # ==================== ORDER MANAGEMENT ====================
    
    async def cancel_order(self, symbol: str, order_id: int) -> bool:
        """Cancel an order"""
        try:
            await self.client.cancel_order(symbol, order_id)
            
            if order_id in self.active_orders:
                del self.active_orders[order_id]
            
            self.logger.info(f"Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol"""
        try:
            cancelled_orders = await self.client.cancel_all_orders(symbol)
            cancelled_count = len(cancelled_orders)
            
            # Remove from active orders
            for order in cancelled_orders:
                if order.order_id in self.active_orders:
                    del self.active_orders[order.order_id]
            
            self.logger.info(f"Cancelled {cancelled_count} orders for {symbol}")
            return cancelled_count
            
        except Exception as e:
            self.logger.error(f"Failed to cancel orders for {symbol}: {e}")
            return 0
    
    async def get_order_status(self, symbol: str, order_id: int) -> Order:
        """Get current order status"""
        return await self.client.get_order(symbol, order_id)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders"""
        return await self.client.get_open_orders(symbol)
    
    # ==================== ADVANCED TRADING STRATEGIES ====================
    
    async def execute_strategy_order(self, symbol: str, side: OrderSide, risk_amount: float, 
                                   current_price: float, stop_loss_pct: float, 
                                   take_profit_pct: float) -> Dict[str, Any]:
        """
        Execute a complete strategy order with stop loss and take profit
        This is the core async pattern for complex trading operations
        """
        try:
            self.logger.info(f"Executing strategy order: {side.value} {symbol} risk=${risk_amount}")
            
            # Calculate quantities and prices
            quantity = risk_amount / current_price
            stop_loss_price = calculate_stop_loss(current_price, stop_loss_pct, side)
            take_profit_price = calculate_take_profit(current_price, take_profit_pct, side)
            
            # Check balance
            if not await self._validate_balance(symbol, side, quote_quantity=risk_amount):
                raise InsufficientBalanceError("Insufficient balance for strategy order")
            
            # Place main order
            main_order = await self.place_market_order(symbol, side, risk_amount)
            executed_quantity = main_order.executed_quantity
            
            # Place stop loss and take profit orders (opposite side)
            opposite_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
            
            # Place orders concurrently for better performance
            stop_task = asyncio.create_task(
                self.place_stop_loss_order(symbol, opposite_side, executed_quantity, stop_loss_price)
            )
            
            profit_task = asyncio.create_task(
                self.place_limit_order(symbol, opposite_side, executed_quantity, take_profit_price)
            )
            
            # Wait for both orders to complete
            stop_order, take_profit_order = await asyncio.gather(stop_task, profit_task)
            
            result = {
                'main_order': main_order,
                'stop_loss_order': stop_order,
                'take_profit_order': take_profit_order,
                'entry_price': current_price,
                'stop_loss_price': stop_loss_price,
                'take_profit_price': take_profit_price,
                'executed_quantity': executed_quantity,
                'risk_amount': risk_amount
            }
            
            self.logger.info(f"Strategy order executed successfully: {main_order.order_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to execute strategy order: {e}")
            raise OrderError(f"Strategy order failed: {e}")
    
    async def execute_dca_order(self, symbol: str, side: OrderSide, total_amount: float, 
                              num_orders: int, time_interval: float) -> List[Order]:
        """
        Execute Dollar Cost Averaging (DCA) strategy
        Places multiple orders over time to average entry price
        """
        orders = []
        order_amount = total_amount / num_orders
        
        self.logger.info(f"Starting DCA: {num_orders} orders of ${order_amount} every {time_interval}s")
        
        for i in range(num_orders):
            try:
                if i > 0:  # Don't wait before first order
                    await asyncio.sleep(time_interval)
                
                order = await self.place_market_order(symbol, side, order_amount)
                orders.append(order)
                
                self.logger.info(f"DCA order {i+1}/{num_orders} placed: {order.order_id}")
                
            except Exception as e:
                self.logger.error(f"DCA order {i+1} failed: {e}")
                break
        
        return orders
    
    # ==================== PORTFOLIO MANAGEMENT ====================
    
    async def get_portfolio_balance(self) -> Dict[str, Balance]:
        """Get portfolio balances"""
        balances = await self.client.get_balances()
        return {balance.asset: balance for balance in balances}
    
    async def get_portfolio_value_usd(self) -> float:
        """Calculate total portfolio value in USD"""
        balances = await self.get_portfolio_balance()
        total_value = 0.0
        
        # Get prices for all assets concurrently
        price_tasks = []
        symbols_to_check = []
        
        for asset, balance in balances.items():
            if balance.total > 0 and asset != 'USDT':
                symbol = f"{asset}USDT"
                symbols_to_check.append((symbol, balance.total))
                price_tasks.append(self.client.get_price(symbol))
        
        if price_tasks:
            prices = await asyncio.gather(*price_tasks, return_exceptions=True)
            
            for (symbol, quantity), price in zip(symbols_to_check, prices):
                if isinstance(price, Exception):
                    self.logger.warning(f"Could not get price for {symbol}: {price}")
                else:
                    total_value += quantity * price
        
        # Add USDT balance directly
        if 'USDT' in balances:
            total_value += balances['USDT'].total
        
        return total_value
    
    async def get_position_size(self, symbol: str, side: OrderSide) -> float:
        """Get current position size for a symbol"""
        base_asset = symbol.replace('USDT', '').replace('BUSD', '')
        quote_asset = 'USDT' if 'USDT' in symbol else 'BUSD'
        
        if side == OrderSide.BUY:
            balance = await self.client.get_balance(quote_asset)
            return balance.free if balance else 0.0
        else:
            balance = await self.client.get_balance(base_asset)
            return balance.free if balance else 0.0
    
    # ==================== PRIVATE HELPER METHODS ====================
    
    async def _validate_balance(self, symbol: str, side: OrderSide, quantity: Optional[float] = None, 
                              price: Optional[float] = None, quote_quantity: Optional[float] = None) -> bool:
        """Validate if balance is sufficient for the order"""
        try:
            base_asset = symbol.replace('USDT', '').replace('BUSD', '')
            quote_asset = 'USDT' if 'USDT' in symbol else 'BUSD'
            
            if side == OrderSide.BUY:
                balance = await self.client.get_balance(quote_asset)
                if not balance:
                    return False
                
                if quote_quantity:
                    required = quote_quantity
                elif quantity and price:
                    required = quantity * price
                else:
                    return False
                
                return balance.free >= required
            else:
                balance = await self.client.get_balance(base_asset)
                if not balance:
                    return False
                
                if quantity:
                    required = quantity
                elif quote_quantity and price:
                    required = quote_quantity / price
                else:
                    return False
                
                return balance.free >= required
                
        except Exception as e:
            self.logger.error(f"Error validating balance: {e}")
            return False
    
    async def _update_position_tracker(self, symbol: str, order: Order):
        """Update internal position tracking"""
        if symbol not in self.position_tracker:
            self.position_tracker[symbol] = {
                'total_quantity': 0.0,
                'total_cost': 0.0,
                'average_price': 0.0,
                'orders': []
            }
        
        position = self.position_tracker[symbol]
        position['orders'].append(order)
        
        if order.side == OrderSide.BUY:
            position['total_quantity'] += order.executed_quantity
            position['total_cost'] += order.quote_quantity
        else:
            position['total_quantity'] -= order.executed_quantity
            position['total_cost'] -= order.quote_quantity
        
        if position['total_quantity'] > 0:
            position['average_price'] = position['total_cost'] / position['total_quantity']
    
    async def get_position_info(self, symbol: str) -> Dict[str, Any]:
        """Get position information for a symbol"""
        if symbol not in self.position_tracker:
            return {
                'symbol': symbol,
                'quantity': 0.0,
                'average_price': 0.0,
                'total_cost': 0.0,
                'unrealized_pnl': 0.0,
                'realized_pnl': 0.0
            }
        
        position = self.position_tracker[symbol]
        current_price = await self.client.get_price(symbol)
        
        unrealized_pnl = 0.0
        if position['total_quantity'] > 0:
            current_value = position['total_quantity'] * current_price
            unrealized_pnl = current_value - position['total_cost']
        
        return {
            'symbol': symbol,
            'quantity': position['total_quantity'],
            'average_price': position['average_price'],
            'total_cost': position['total_cost'],
            'current_price': current_price,
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_percent': (unrealized_pnl / position['total_cost'] * 100) if position['total_cost'] > 0 else 0.0
        }
    
    # ==================== RISK MANAGEMENT ====================
    
    async def calculate_position_risk(self, symbol: str, entry_price: float, stop_loss_price: float, 
                                    quantity: float) -> Dict[str, float]:
        """Calculate position risk metrics"""
        risk_per_unit = abs(entry_price - stop_loss_price)
        total_risk = risk_per_unit * quantity
        
        # Get current portfolio value for risk percentage
        portfolio_value = await self.get_portfolio_value_usd()
        risk_percentage = (total_risk / portfolio_value * 100) if portfolio_value > 0 else 0.0
        
        return {
            'risk_per_unit': risk_per_unit,
            'total_risk': total_risk,
            'risk_percentage': risk_percentage,
            'reward_risk_ratio': 0.0  # Can be calculated if take profit is provided
        }
    
    async def check_position_limits(self, symbol: str, side: OrderSide, quantity: float, 
                                  max_position_size: float) -> bool:
        """Check if position would exceed limits"""
        current_position = await self.get_position_info(symbol)
        
        if side == OrderSide.BUY:
            new_quantity = current_position['quantity'] + quantity
        else:
            new_quantity = current_position['quantity'] - quantity
        
        return abs(new_quantity) <= max_position_size
