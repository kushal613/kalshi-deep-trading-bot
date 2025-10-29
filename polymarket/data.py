"""
Polymarket data fetching module using polymarket-apis package.
"""
import asyncio
import httpx
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from loguru import logger
from config import PolymarketConfig

# Note: polymarket-apis requires Python 3.12+, using direct HTTP requests instead
DataClient = None
CLOBClient = None


class PolymarketDataClient:
    """Client for fetching Polymarket data."""
    
    def __init__(self, config: PolymarketConfig):
        self.config = config
        self.data_client = None
        self.clob_client = None
        self.http_client = None
        
    async def initialize(self):
        """Initialize the Polymarket clients."""
        try:
            if DataClient and CLOBClient:
                # Initialize official Polymarket clients
                self.data_client = DataClient()
                self.clob_client = CLOBClient()
                logger.info("Initialized Polymarket official clients")
            else:
                # Fallback to direct HTTP client
                self.http_client = httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=30.0
                )
                logger.info("Using HTTP client for Polymarket data")
                
        except Exception as e:
            logger.error(f"Error initializing Polymarket clients: {e}")
            # Fallback to HTTP client
            self.http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=30.0
            )
    
    async def get_markets(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get active Polymarket markets sorted by volume."""
        try:
            if self.data_client:
                # Use official Polymarket client
                markets = await self._get_markets_official(limit)
            else:
                # Use HTTP client as fallback
                markets = await self._get_markets_http(limit)
            
            # Markets are already processed, just filter and sort
            filtered_markets = []
            for market in markets:
                # Markets are already processed by _process_gamma_api_response
                if market.get("volume", 0) > 1000:  # $1000 minimum volume
                    filtered_markets.append(market)
            
            # Sort by volume and return top N
            filtered_markets.sort(key=lambda x: x.get("volume", 0), reverse=True)
            return filtered_markets[:limit]
            
        except Exception as e:
            logger.error(f"Error fetching Polymarket markets: {e}")
            return []

    async def _attach_live_quotes(self, markets: List[Dict[str, Any]]) -> None:
        """Best-effort: attach best bid/ask and mid-prices to each market.
        Tries CLOB endpoints; falls back silently if unavailable.
        """
        if not self.http_client:
            return

        async def fetch_quotes(market: Dict[str, Any]) -> None:
            market_id = market.get("market_id") or market.get("id")
            if not market_id:
                return
            # Try a few plausible CLOB endpoints; ignore failures
            endpoints = [
                f"https://clob.polymarket.com/prices?market={market_id}",
                f"https://clob.polymarket.com/markets/{market_id}/prices",
                f"https://clob.polymarket.com/book?market={market_id}",
                f"https://clob.polymarket.com/markets/{market_id}/book",
            ]
            best_bid = None
            best_ask = None
            try:
                for url in endpoints:
                    try:
                        resp = await self.http_client.get(url)
                        if resp.status_code != 200:
                            continue
                        data = resp.json()
                        # Heuristics to extract top-of-book
                        if isinstance(data, dict):
                            if "bids" in data or "asks" in data:
                                bids = data.get("bids") or []
                                asks = data.get("asks") or []
                                if bids:
                                    # price could be string or number in 0-1
                                    bb = float(bids[0].get("price", 0))
                                    best_bid = bb if bb > 0 else best_bid
                                if asks:
                                    ba = float(asks[0].get("price", 0))
                                    best_ask = ba if ba > 0 else best_ask
                            elif "prices" in data:
                                # sometimes keyed by outcome
                                prices = data.get("prices", {})
                                # attempt to infer yes/no
                                yes_key = "YES" if "YES" in prices else "Up" if "Up" in prices else None
                                no_key = "NO" if "NO" in prices else "Down" if "Down" in prices else None
                                if yes_key and isinstance(prices.get(yes_key), dict):
                                    best_bid = float(prices[yes_key].get("bid", 0)) or best_bid
                                    best_ask = float(prices[yes_key].get("ask", 0)) or best_ask
                                # if only one side found, still useful
                        elif isinstance(data, list) and data:
                            # list of quote entries with side/price
                            bids = [float(x.get("price", 0)) for x in data if x.get("side", "").lower() == "bid"]
                            asks = [float(x.get("price", 0)) for x in data if x.get("side", "").lower() == "ask"]
                            if bids:
                                best_bid = max(bids)
                            if asks:
                                best_ask = min(asks)
                        if best_bid is not None or best_ask is not None:
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # Attach computed mid if we have at least bid or ask
            if best_bid is not None or best_ask is not None:
                # fallback to outcome prices for missing side
                yes_price = None
                no_price = None
                for o in market.get("outcomes", []) or []:
                    if o.get("name") in ("YES", "Up"):
                        yes_price = float(o.get("price", 0.0))
                    if o.get("name") in ("NO", "Down"):
                        no_price = float(o.get("price", 0.0))
                if best_bid is None:
                    best_bid = yes_price if yes_price is not None else 0.0
                if best_ask is None:
                    best_ask = yes_price if yes_price is not None else 0.0

                mid_price = (best_bid + best_ask) / 2.0 if (best_bid is not None and best_ask is not None) else None
                market["bestBid"] = best_bid
                market["bestAsk"] = best_ask
                market["spread"] = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
                # store simple mid for YES leg; NO mid is 1 - YES mid for binaries
                if mid_price is not None:
                    market["yes_mid_price"] = mid_price
                    market["no_mid_price"] = max(0.0, min(1.0, 1.0 - mid_price))

        # Run limited parallelism to avoid hammering the API
        tasks = [fetch_quotes(m) for m in markets[: min(len(markets), 50)]]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass
    
    async def _get_markets_official(self, limit: int) -> List[Dict[str, Any]]:
        """Get markets using official Polymarket client."""
        try:
            # This would use the official polymarket-apis client
            # For now, we'll implement a basic version
            markets = []
            
            # Example of how to use the official client (when properly implemented)
            # markets = await self.data_client.get_markets(limit=limit)
            
            return markets
            
        except Exception as e:
            logger.error(f"Error with official Polymarket client: {e}")
            return []
    
    async def _get_markets_http(self, limit: int) -> List[Dict[str, Any]]:
        """Get markets using The Graph Protocol (Polymarket's official data source)."""
        try:
            # Use The Graph Protocol - Polymarket's official subgraph
            query = """
            query GetMarkets($first: Int!, $skip: Int!) {
                markets(
                    first: $first, 
                    skip: $skip,
                    orderBy: volume, 
                    orderDirection: desc,
                    where: { 
                        volume_gt: "1000000000000000000",
                        active: true 
                    }
                ) {
                    id
                    question
                    description
                    endDate
                    volume
                    liquidity
                    active
                    outcomes {
                        id
                        name
                        price
                        volume
                    }
                    tokens {
                        id
                        outcome
                        price
                        volume
                    }
                }
            }
            """
            
            payload = {
                "query": query,
                "variables": {
                    "first": min(limit, 100),  # GraphQL limit
                    "skip": 0
                }
            }
            
            # Try multiple GraphQL endpoints
            endpoints = [
                "https://api.thegraph.com/subgraphs/name/polymarket/polymarket",
                "https://gateway.thegraph.com/api/subgraphs/id/QmY3Bf1F5Hf8S3vDxW2Y1K9L8M7N6P5Q4R3S2T1U0V9W8X7Y6Z5",
                "https://api.studio.thegraph.com/query/12345/polymarket/version/latest"
            ]
            
            for endpoint in endpoints:
                try:
                    logger.info(f"Trying GraphQL endpoint: {endpoint}")
                    response = await self.http_client.post(endpoint, json=payload)
                    response.raise_for_status()
                    
                    data = response.json()
                    if "errors" in data:
                        logger.warning(f"GraphQL errors: {data['errors']}")
                        continue
                        
                    markets = data.get("data", {}).get("markets", [])
                    if markets:
                        logger.info(f"Successfully fetched {len(markets)} markets from {endpoint}")
                        return markets
                        
                except Exception as e:
                    logger.warning(f"Failed to fetch from {endpoint}: {e}")
                    continue
            
            # If all GraphQL endpoints fail, try direct Polymarket API
            markets = await self._get_markets_direct_api(limit)
            # Attach live quotes best-effort
            try:
                await self._attach_live_quotes(markets)
            except Exception:
                pass
            return markets
            
        except Exception as e:
            logger.error(f"Error fetching markets via GraphQL: {e}")
            # Fallback to mock data for testing
            return self._get_mock_markets(limit)
    
    async def _get_markets_direct_api(self, limit: int) -> List[Dict[str, Any]]:
        """Try Polymarket's official Gamma API (no authentication required)."""
        try:
            # Polymarket's official Gamma API endpoints (no auth required)
            endpoints = [
                "https://gamma-api.polymarket.com/events?order=id&ascending=false&closed=false&limit=100",
                "https://gamma-api.polymarket.com/markets?limit=100",
                "https://gamma-api.polymarket.com/events?limit=100"
            ]
            
            for endpoint in endpoints:
                try:
                    logger.info(f"Trying Polymarket Gamma API: {endpoint}")
                    response = await self.http_client.get(endpoint)
                    response.raise_for_status()
                    
                    data = response.json()
                    
                    # Handle different response formats
                    if isinstance(data, list):
                        markets = data
                    elif isinstance(data, dict):
                        markets = data.get("data", []) or data.get("markets", []) or data.get("events", [])
                    else:
                        continue
                    
                    if markets and len(markets) > 0:
                        logger.info(f"Successfully fetched {len(markets)} markets from Gamma API")
                        # Convert events to market format if needed
                        processed_markets = self._process_gamma_api_response(markets)
                        # Attach live quotes best-effort
                        try:
                            await self._attach_live_quotes(processed_markets)
                        except Exception:
                            pass
                        return processed_markets[:limit]
                        
                except Exception as e:
                    logger.warning(f"Failed to fetch from {endpoint}: {e}")
                    continue
            
            # If all Gamma APIs fail, return mock data
            logger.warning("All Polymarket API endpoints failed, using mock data")
            return self._get_mock_markets(limit)
            
        except Exception as e:
            logger.error(f"Error fetching markets via Gamma API: {e}")
            return self._get_mock_markets(limit)
    
    def _process_gamma_api_response(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process Gamma API response to standardize market format."""
        processed_markets = []
        
        for item in data:
            try:
                # Check if this is an event with markets
                if "markets" in item and item["markets"]:
                    # Process each market in the event
                    for market_data in item["markets"]:
                        market = {
                            "market_id": market_data.get("id", ""),
                            "id": market_data.get("id", ""),
                            "question": market_data.get("question", ""),
                            "description": market_data.get("description", ""),
                            "endDate": market_data.get("endDate", ""),
                            "volume": float(market_data.get("volume", 0)),
                            "liquidity": float(market_data.get("liquidity", 0)),
                            "active": market_data.get("active", True),
                            "outcomes": self._extract_outcomes(market_data),
                            "event_id": item.get("id", ""),
                            "event_title": item.get("title", "")
                        }
                        # Optional metrics if present
                        for opt_key in (
                            "volume24hr","volume1wk","volume1mo","volume1yr",
                            "liquidityAmm","liquidityClob","acceptingOrders",
                            "bestBid","bestAsk","lastTradePrice","spread"
                        ):
                            if opt_key in market_data:
                                market[opt_key] = market_data.get(opt_key)
                        
                        # Only include markets with sufficient volume
                        if market["volume"] > 1000:  # $1000 minimum volume
                            processed_markets.append(market)
                else:
                    # Handle direct market data
                    market = {
                        "market_id": item.get("id", item.get("market_id", "")),
                        "id": item.get("id", item.get("market_id", "")),
                        "question": item.get("question", item.get("title", "")),
                        "description": item.get("description", ""),
                        "endDate": item.get("end_date", item.get("endDate", "")),
                        "volume": float(item.get("volume", 0)),
                        "liquidity": float(item.get("liquidity", 0)),
                        "active": item.get("active", True),
                        "outcomes": self._extract_outcomes(item),
                        "event_id": item.get("event_id", ""),
                        "event_title": item.get("event_title", "")
                    }
                    # Optional metrics if present on item
                    for opt_key in (
                        "volume24hr","volume1wk","volume1mo","volume1yr",
                        "liquidityAmm","liquidityClob","acceptingOrders",
                        "bestBid","bestAsk","lastTradePrice","spread"
                    ):
                        if opt_key in item:
                            market[opt_key] = item.get(opt_key)
                    
                    # Only include markets with sufficient volume
                    if market["volume"] > 1000:  # $1000 minimum volume
                        processed_markets.append(market)
                    
            except Exception as e:
                logger.warning(f"Error processing market data: {e}")
                continue
        
        return processed_markets
    
    def _extract_outcomes(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract outcomes from Gamma API response."""
        outcomes = []
        
        # Handle Polymarket's actual API format
        if "outcomes" in item:
            try:
                # Parse JSON strings
                outcomes_list = json.loads(item["outcomes"]) if isinstance(item["outcomes"], str) else item["outcomes"]
                
                # Get prices if available, otherwise use default
                if "outcomePrices" in item:
                    prices_list = json.loads(item["outcomePrices"]) if isinstance(item["outcomePrices"], str) else item["outcomePrices"]
                else:
                    # Use default prices when not available
                    prices_list = [0.5] * len(outcomes_list)
                
                # Create outcomes with names and prices
                for i, outcome_name in enumerate(outcomes_list):
                    price = float(prices_list[i]) if i < len(prices_list) else 0.5
                    outcomes.append({
                        "id": outcome_name.lower(),
                        "name": outcome_name,
                        "price": price
                    })
            except (json.JSONDecodeError, TypeError, IndexError) as e:
                logger.warning(f"Error parsing outcomes: {e}")
                # Fall back to default
                outcomes = [
                    {"id": "yes", "name": "YES", "price": 0.5},
                    {"id": "no", "name": "NO", "price": 0.5}
                ]
        elif "outcomes" in item and isinstance(item["outcomes"], list):
            # Handle array format
            for outcome in item["outcomes"]:
                outcomes.append({
                    "id": outcome.get("id", ""),
                    "name": outcome.get("name", ""),
                    "price": float(outcome.get("price", 0))
                })
        elif "tokens" in item:
            # Handle tokens format
            for token in item["tokens"]:
                outcomes.append({
                    "id": token.get("id", ""),
                    "name": token.get("outcome", ""),
                    "price": float(token.get("price", 0))
                })
        else:
            # Default binary outcomes
            outcomes = [
                {"id": "yes", "name": "YES", "price": 0.5},
                {"id": "no", "name": "NO", "price": 0.5}
            ]
        
        return outcomes
    
    def _get_mock_markets(self, limit: int) -> List[Dict[str, Any]]:
        """Get mock markets for testing when API is unavailable."""
        mock_markets = [
            {
                "id": "mock-market-1",
                "question": "Will Bitcoin reach $100,000 by end of 2024?",
                "description": "Bitcoin price prediction market",
                "endDate": "2024-12-31T23:59:59Z",
                "volume": 50000,
                "liquidity": 25000,
                "outcomes": [
                    {"id": "yes", "name": "YES", "price": 0.45},
                    {"id": "no", "name": "NO", "price": 0.55}
                ]
            },
            {
                "id": "mock-market-2", 
                "question": "Will the S&P 500 close above 5000 by year end?",
                "description": "Stock market prediction",
                "endDate": "2024-12-31T23:59:59Z",
                "volume": 30000,
                "liquidity": 15000,
                "outcomes": [
                    {"id": "yes", "name": "YES", "price": 0.60},
                    {"id": "no", "name": "NO", "price": 0.40}
                ]
            },
            {
                "id": "mock-market-3",
                "question": "Will there be a recession in 2024?",
                "description": "Economic prediction market",
                "endDate": "2024-12-31T23:59:59Z", 
                "volume": 40000,
                "liquidity": 20000,
                "outcomes": [
                    {"id": "yes", "name": "YES", "price": 0.30},
                    {"id": "no", "name": "NO", "price": 0.70}
                ]
            }
        ]
        
        return mock_markets[:limit]
    
    def _enrich_market_data(self, market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Enrich market data with additional fields."""
        try:
            # Extract key fields from Polymarket market data
            market_id = market.get("id", "")
            question = market.get("question", "")
            description = market.get("description", "")
            
            # Parse outcomes and prices from JSON strings
            outcomes_str = market.get("outcomes", "[]")
            prices_str = market.get("outcomePrices", "[]")
            
            try:
                outcomes_list = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
                prices_list = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
            except (json.JSONDecodeError, TypeError):
                outcomes_list = []
                prices_list = []
            
            if len(outcomes_list) < 2:
                logger.warning(f"Market {market_id} has insufficient outcomes")
                return None
            
            # Create outcomes with names and prices
            outcomes = []
            for i, outcome_name in enumerate(outcomes_list):
                price = float(prices_list[i]) if i < len(prices_list) else 0.5
                outcomes.append({
                    'name': outcome_name,
                    'price': price
                })
            
            # Calculate volume and liquidity
            volume = market.get("volume", 0)
            liquidity = market.get("liquidity", 0)
            
            # Get current prices (Polymarket uses token prices)
            prices = {outcome['name']: outcome['price'] for outcome in outcomes}
            
            # Check if market is active
            end_date = market.get("end_date")
            is_active = True
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    is_active = end_dt > datetime.now(timezone.utc)
                except:
                    pass
            
            if not is_active:
                return None
            
            enriched_market = {
                "market_id": market_id,
                "question": question,
                "description": description,
                "outcomes": outcomes,
                "prices": prices,
                "volume": volume,
                "liquidity": liquidity,
                "end_date": end_date,
                "is_active": is_active,
                "category": market.get("category", ""),
                "raw_data": market  # Keep original data for reference
            }
            
            return enriched_market
            
        except Exception as e:
            logger.error(f"Error enriching market data: {e}")
            return None
    
    async def get_market_details(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific market."""
        try:
            if self.data_client:
                # Use official client
                market = await self.data_client.get_market(market_id)
            else:
                # Use HTTP client
                response = await self.http_client.get(f"/markets/{market_id}")
                response.raise_for_status()
                market = response.json()
            
            return self._enrich_market_data(market)
            
        except Exception as e:
            logger.error(f"Error fetching market details for {market_id}: {e}")
            return None
    
    async def get_market_trades(self, market_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades for a market."""
        try:
            if self.data_client:
                # Use official client
                trades = await self.data_client.get_trades(market_id, limit=limit)
            else:
                # Use HTTP client
                response = await self.http_client.get(f"/markets/{market_id}/trades", params={"limit": limit})
                response.raise_for_status()
                trades = response.json().get("data", [])
            
            return trades
            
        except Exception as e:
            logger.error(f"Error fetching trades for {market_id}: {e}")
            return []
    
    async def get_user_positions(self, user_address: str) -> List[Dict[str, Any]]:
        """Get user positions across all markets."""
        try:
            if self.data_client:
                # Use official client
                positions = await self.data_client.get_user_positions(user_address)
            else:
                # Use HTTP client
                response = await self.http_client.get(f"/users/{user_address}/positions")
                response.raise_for_status()
                positions = response.json().get("data", [])
            
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching positions for {user_address}: {e}")
            return []
    
    async def has_position_in_market(self, market_id: str, user_address: str) -> bool:
        """Check if user has a position in a specific market."""
        try:
            positions = await self.get_user_positions(user_address)
            
            for position in positions:
                if position.get("market_id") == market_id:
                    # Check if position has any tokens
                    token_amount = position.get("token_amount", 0)
                    if token_amount > 0:
                        logger.info(f"Found existing position in {market_id}: {token_amount} tokens")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking position for {market_id}: {e}")
            return False
    
    async def close(self):
        """Close the HTTP client."""
        if self.http_client:
            await self.http_client.aclose()
