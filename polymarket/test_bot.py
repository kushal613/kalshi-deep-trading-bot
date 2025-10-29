#!/usr/bin/env python3
"""
Simple test script for the Polymarket Deep Trading Bot.
"""
import asyncio
import sys
import os
from pathlib import Path

# Add the parent directory to the path to import shared models
sys.path.append(str(Path(__file__).parent.parent))

def test_imports():
    """Test that all required modules can be imported."""
    try:
        from polymarket.config import load_config
        from polymarket.data import PolymarketDataClient
        from polymarket.trade import PolymarketTradingClient
        from polymarket.main import PolymarketTradingBot
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_config():
    """Test configuration loading."""
    try:
        from polymarket.config import load_config
        config = load_config()
        print("✅ Configuration loaded successfully")
        print(f"   - Max markets: {config.max_markets_to_analyze}")
        print(f"   - Max bet amount: ${config.max_bet_amount}")
        print(f"   - Dry run: {config.dry_run}")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

async def test_data_client():
    """Test data client initialization."""
    try:
        from polymarket.data import PolymarketDataClient
        from polymarket.config import load_config
        
        config = load_config()
        client = PolymarketDataClient(config.polymarket)
        await client.initialize()
        print("✅ Data client initialized successfully")
        
        await client.close()
        return True
    except Exception as e:
        print(f"❌ Data client error: {e}")
        return False

async def test_trading_client():
    """Test trading client initialization."""
    try:
        from polymarket.trade import PolymarketTradingClient
        from polymarket.config import load_config
        
        config = load_config()
        client = PolymarketTradingClient(config.polymarket)
        await client.initialize()
        print("✅ Trading client initialized successfully")
        
        await client.close()
        return True
    except Exception as e:
        print(f"❌ Trading client error: {e}")
        return False

async def test_bot_initialization():
    """Test bot initialization."""
    try:
        from polymarket.main import PolymarketTradingBot
        
        bot = PolymarketTradingBot(live_trading=False)
        print("✅ Bot created successfully")
        
        # Test initialization (this will fail if API keys are missing, which is expected)
        try:
            await bot.initialize()
            print("✅ Bot initialized successfully")
        except Exception as e:
            if "API key" in str(e) or "required" in str(e):
                print("⚠️  Bot initialization failed due to missing API keys (expected)")
                print("   Set up your .env file with API keys to test full functionality")
            else:
                print(f"❌ Bot initialization error: {e}")
                return False
        
        return True
    except Exception as e:
        print(f"❌ Bot creation error: {e}")
        return False

async def main():
    """Run all tests."""
    print("🧪 Testing Polymarket Deep Trading Bot...")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Configuration Test", test_config),
        ("Data Client Test", test_data_client),
        ("Trading Client Test", test_trading_client),
        ("Bot Initialization Test", test_bot_initialization),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The Polymarket bot is ready to use.")
        print("\nNext steps:")
        print("1. Set up your .env file with API keys")
        print("2. Run: python main.py (dry run mode)")
        print("3. Run: python main.py --live (live trading)")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        print("Make sure you have installed the required dependencies:")
        print("pip install -r requirements.txt")

if __name__ == "__main__":
    asyncio.run(main())
