#!/usr/bin/env python3
import asyncio
from simple_binance_async import AsyncBinanceWrapper, API_KEY, API_SECRET

async def test_limit_order():
    print("Testing Limit Orders on Binance Testnet")
    print("=" * 50)
    
    async with AsyncBinanceWrapper(API_KEY, API_SECRET) as client:
        try:
            # 1. Get current market price
            current_price = await client.get_price("BTCUSDT")
            print(f"\nCurrent BTC price: ${current_price:,.2f}")
            
            # 2. Check your balance
            balances = await client.get_balances()
            usdt_balance = balances.get('USDT', 0)
            print(f"Your USDT balance: {usdt_balance:.2f}")
            
            # 3. Place a limit buy order 1% below current price
            # Round price to 2 decimal places for BTCUSDT
            buy_price = round(current_price * 0.99, 2)
            print(f"\nPlacing limit buy order at ${buy_price:,.2f}")
            buy_order = await client.place_limit_order(
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.001,  # 0.001 BTC
                price=buy_price
            )
            print("Buy Order placed:")
            print(f"Order ID: {buy_order['orderId']}")
            print(f"Status: {buy_order['status']}")
            print(f"Price: ${float(buy_order['price']):,.2f}")
            print(f"Quantity: {buy_order['origQty']} BTC")
            
            # 4. Place a limit sell order 1% above current price
            sell_price = round(current_price * 1.01, 2)
            print(f"\nPlacing limit sell order at ${sell_price:,.2f}")
            sell_order = await client.place_limit_order(
                symbol="BTCUSDT",
                side="SELL",
                quantity=0.001,  # 0.001 BTC
                price=sell_price
            )
            print("Sell Order placed:")
            print(f"Order ID: {sell_order['orderId']}")
            print(f"Status: {sell_order['status']}")
            print(f"Price: ${float(sell_order['price']):,.2f}")
            print(f"Quantity: {sell_order['origQty']} BTC")
            
            # 5. Check open orders
            print("\nChecking open orders...")
            open_orders = await client.get_open_orders("BTCUSDT")
            print(f"Total open orders: {len(open_orders)}")
            for order in open_orders:
                print(f"\nOrder ID: {order['orderId']}")
                print(f"Side: {order['side']}")
                print(f"Price: ${float(order['price']):,.2f}")
                print(f"Quantity: {order['origQty']} BTC")
                print(f"Status: {order['status']}")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_limit_order())
    except KeyboardInterrupt:
        print("\nTest stopped by user")
    except Exception as e:
        print(f"Error: {e}") 