"""
Polymarket Deep Trading Bot - Main execution module.
"""
import asyncio
import argparse
import json
import csv
import datetime
import math
import os
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import time
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from loguru import logger
import re

from data import PolymarketDataClient
from trade import PolymarketTradingClient
from config import load_config
import openai

# Import shared models from parent directory
sys.path.append('..')
from betting_models import BettingDecision, MarketAnalysis, ProbabilityExtraction


class PolymarketTradingBot:
    """Main Polymarket trading bot that follows the same workflow as Kalshi bot."""
    
    def __init__(self, live_trading: bool = False, private_key: Optional[str] = None):
        self.config = load_config()
        self.config.dry_run = not live_trading
        self.console = Console()
        self.data_client = None
        self.trading_client = None
        self.openai_client = None
        self.market_data = {}  # Store market data for CSV generation
        self.private_key = private_key
        
    async def initialize(self):
        """Initialize all clients."""
        self.console.print("[bold blue]Initializing Polymarket trading bot...[/bold blue]")
        
        # Initialize clients
        self.data_client = PolymarketDataClient(self.config.polymarket)
        self.trading_client = PolymarketTradingClient(self.config.polymarket, self.private_key)
        self.openai_client = openai.AsyncOpenAI(api_key=self.config.openai.api_key)
        
        # Initialize connections
        await self.data_client.initialize()
        await self.trading_client.initialize()
        
        # Test connections
        self.console.print("[green]✓ Polymarket data client connected[/green]")
        self.console.print("[green]✓ Polymarket trading client ready[/green]")
        self.console.print("[green]✓ OpenAI API ready[/green]")
        
        # Show environment info
        env_name = "MAINNET" if self.config.polymarket.use_mainnet else "TESTNET"
        mode = "DRY RUN" if self.config.dry_run else "LIVE TRADING"
        
        self.console.print(f"\n[blue]Environment: {env_name}[/blue]")
        self.console.print(f"[blue]Mode: {mode}[/blue]")
        self.console.print(f"[blue]Max markets to analyze: {self.config.max_markets_to_analyze}[/blue]")
        self.console.print(f"[blue]Research batch size: {self.config.research_batch_size}[/blue]")
        self.console.print(f"[blue]Skip existing positions: {self.config.skip_existing_positions}[/blue]")
        self.console.print(f"[blue]Minimum liquidity: ${self.config.minimum_liquidity}[/blue]")
        self.console.print(f"[blue]Max bet amount: ${self.config.max_bet_amount}[/blue]")
        
        hedging_status = "Enabled" if self.config.enable_hedging else "Disabled"
        self.console.print(f"[blue]Risk hedging: {hedging_status} (ratio: {self.config.hedge_ratio}, min confidence: {self.config.min_confidence_for_hedging})[/blue]")
        
        # Show risk-adjusted trading settings
        self.console.print(f"[blue]R-score filtering: Enabled (z-threshold: {self.config.z_threshold})[/blue]")
        if self.config.enable_kelly_sizing:
            self.console.print(f"[blue]Kelly sizing: Enabled (fraction: {self.config.kelly_fraction}, bankroll: ${self.config.bankroll})[/blue]")
        self.console.print(f"[blue]Portfolio selection: {self.config.portfolio_selection_method} (max positions: {self.config.max_portfolio_positions})[/blue]\n")
    
    def calculate_risk_adjusted_metrics(self, research_prob: float, market_price: float, action: str) -> dict:
        """Calculate hedge-fund style risk-adjusted metrics."""
        try:
            # Adjust probabilities based on action
            if action == "buy_yes":
                p = research_prob
                y = market_price
            elif action == "buy_no":
                p = 1 - research_prob
                y = market_price
            else:
                return {"expected_return": 0.0, "r_score": 0.0, "kelly_fraction": 0.0}
            
            # Prevent division by zero and invalid probabilities
            if y <= 0 or y >= 1 or p <= 0 or p >= 1:
                return {"expected_return": 0.0, "r_score": 0.0, "kelly_fraction": 0.0}
            
            # Expected return on capital: E[R] = (p-y)/y
            expected_return = (p - y) / y
            
            # Risk-Adjusted Edge (R-score): (p-y)/sqrt(p*(1-p))
            variance = p * (1 - p)
            if variance <= 0:
                return {"expected_return": expected_return, "r_score": 0.0, "kelly_fraction": 0.0}
            
            r_score = (p - y) / math.sqrt(variance)
            
            # Kelly fraction: f_kelly = (p-y)/(1-y)
            if y >= 1:
                kelly_fraction = 0.0
            else:
                kelly_fraction = (p - y) / (1 - y)
                kelly_fraction = max(0.0, min(1.0, kelly_fraction))
            
            return {
                "expected_return": expected_return,
                "r_score": r_score,
                "kelly_fraction": kelly_fraction
            }
            
        except Exception as e:
            logger.warning(f"Error calculating risk metrics: {e}")
            return {"expected_return": 0.0, "r_score": 0.0, "kelly_fraction": 0.0}
    
    def calculate_kelly_position_size(self, kelly_fraction: float) -> float:
        """Calculate position size using fractional Kelly criterion."""
        if not self.config.enable_kelly_sizing or kelly_fraction <= 0:
            return self.config.max_bet_amount
        
        # Apply fractional Kelly
        adjusted_kelly = kelly_fraction * self.config.kelly_fraction
        
        # Calculate position size as fraction of bankroll
        kelly_bet_size = self.config.bankroll * adjusted_kelly
        
        # Apply maximum bet fraction constraint
        max_allowed = self.config.bankroll * self.config.max_kelly_bet_fraction
        kelly_bet_size = min(kelly_bet_size, max_allowed)
        
        # Apply absolute maximum bet limit
        kelly_bet_size = min(kelly_bet_size, self.config.max_bet_amount)
        
        # Ensure minimum bet size
        kelly_bet_size = max(kelly_bet_size, 1.0)
        
        return kelly_bet_size
    
    async def get_top_markets(self) -> List[Dict[str, Any]]:
        """Get top Polymarket markets sorted by volume."""
        self.console.print("[bold]Step 1: Fetching top Polymarket markets...[/bold]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True,
        ) as progress:
            task = progress.add_task("Fetching markets...", total=None)
            
            try:
                markets = await self.data_client.get_markets(limit=self.config.max_markets_to_analyze)
                
                # Filter by minimum liquidity
                filtered_markets = [
                    market for market in markets 
                    if market.get("liquidity", 0) >= self.config.minimum_liquidity
                ]
                
                self.console.print(f"[blue]• Fetched {len(markets)} markets, {len(filtered_markets)} meet liquidity requirements[/blue]")
                self.console.print(f"[green]✓ Found {len(filtered_markets)} markets[/green]")
                
                # Show top 10 markets
                table = Table(title="Top 10 Polymarket Markets by Volume")
                table.add_column("Market ID", style="cyan")
                table.add_column("Question", style="yellow")
                table.add_column("Volume", style="magenta", justify="right")
                table.add_column("Liquidity", style="green", justify="right")
                table.add_column("End Date", style="blue")
                
                for market in filtered_markets[:10]:
                    end_date = market.get('end_date', 'No date set')
                    if end_date and end_date != 'No date set':
                        try:
                            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                            time_str = end_dt.strftime("%Y-%m-%d")
                        except:
                            time_str = end_date
                    else:
                        time_str = "No date set"
                    
                    table.add_row(
                        market.get('market_id', 'N/A')[:20] + "...",
                        market.get('question', 'N/A')[:40] + ("..." if len(market.get('question', '')) > 40 else ""),
                        f"{market.get('volume', 0):,}",
                        f"{market.get('liquidity', 0):,}",
                        time_str
                    )
                
                self.console.print(table)
                
                # Store market data for CSV generation
                for market in filtered_markets:
                    self.market_data[market.get('market_id', '')] = market
                
                return filtered_markets
                
            except Exception as e:
                self.console.print(f"[red]Error fetching markets: {e}[/red]")
                return []
    
    async def research_markets(self, markets: List[Dict[str, Any]]) -> Dict[str, str]:
        """Research each market using Octagon Deep Research."""
        self.console.print(f"\n[bold]Step 2: Researching {len(markets)} markets...[/bold]")
        
        research_results = {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("Researching markets...", total=len(markets))
            
            # Research markets in batches
            batch_size = self.config.research_batch_size
            market_items = list(enumerate(markets))
            
            for i in range(0, len(market_items), batch_size):
                batch = market_items[i:i + batch_size]
                self.console.print(f"[blue]Processing research batch {i//batch_size + 1} with {len(batch)} markets[/blue]")
                
                # Research batch in parallel
                tasks = []
                for idx, market in batch:
                    coro = self._research_single_market(market)
                    tasks.append(asyncio.wait_for(coro, timeout=self.config.research_timeout_seconds))
                
                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for (idx, market), result in zip(batch, results):
                        market_id = market.get('market_id', f'market_{idx}')
                        if not isinstance(result, Exception) and result:
                            research_results[market_id] = result
                            progress.update(task, advance=1)
                            self.console.print(f"[green]✓ Researched {market_id}[/green]")
                        else:
                            err = result
                            if isinstance(result, asyncio.TimeoutError):
                                err = f"Timeout after {self.config.research_timeout_seconds}s"
                            self.console.print(f"[red]✗ Failed to research {market_id}: {err}[/red]")
                            progress.update(task, advance=1)
                
                except Exception as e:
                    self.console.print(f"[red]Batch research error: {e}[/red]")
                    progress.update(task, advance=len(batch))
                
                # Brief pause between batches
                await asyncio.sleep(1)
        
        self.console.print(f"[green]✓ Completed research on {len(research_results)} markets[/green]")
        return research_results
    
    async def _research_single_market(self, market: Dict[str, Any]) -> str:
        """Research a single market using Octagon Deep Research."""
        try:
            market_id = market.get('market_id', '')
            question = market.get('question', '')
            description = market.get('description', '')
            outcomes = market.get('outcomes', [])
            
            # Format market information for analysis
            market_info = f"""
            Market: {question}
            Description: {description}
            Outcomes: {', '.join([outcome.get('name', '') for outcome in outcomes])}
            """
            
            prompt = f"""
            You are a prediction market expert. Research this Polymarket event and predict the probability for each outcome.
            
            {market_info}
            
            Please provide:
            1. Overall market analysis and key factors
            2. Current sentiment and news analysis
            3. For each outcome, predict the probability (0-100%)
            4. Confidence level for each prediction (1-10)
            5. Key risks and catalysts that could affect outcomes
            6. Trading recommendations
            
            Focus on:
            - Independent analysis of each outcome's probability
            - Provide actionable insights for trading decisions
            - Be specific about probability estimates
            
            IMPORTANT: When providing probability predictions, include both the outcome name AND the probability percentage.
            Example format: "YES: 65%" or "NO: 35%"
            
            Format your response clearly with outcome names and probability predictions.
            """
            
            logger.info(f"Starting deep research for market {market_id}...")
            
            # Use OpenAI for research (fallback when Octagon is not available)
            response = await self.openai_client.chat.completions.create(
                model=self.config.openai.model,
                messages=[
                    {"role": "system", "content": "You are a professional prediction market analyst."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            content = response.choices[0].message.content
            logger.info(f"Completed research for market {market_id}")
            
            return content
            
        except Exception as e:
            logger.error(f"Error researching market {market.get('market_id', '')}: {e}")
            return f"Error researching market: {str(e)}"
    
    async def extract_probabilities(self, research_results: Dict[str, str], 
                                  markets: List[Dict[str, Any]]) -> Dict[str, ProbabilityExtraction]:
        """Extract structured probabilities from research results."""
        self.console.print(f"\n[bold]Step 3: Extracting probabilities from research...[/bold]")
        
        probability_extractions = {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("Extracting probabilities...", total=len(research_results))
            
            # Create tasks for all markets to run in parallel
            tasks = []
            for market_id, research_text in research_results.items():
                # Find the market data
                market_data = None
                for market in markets:
                    if market.get('market_id') == market_id:
                        market_data = market
                        break
                
                if market_data:
                    task_coroutine = self._extract_probabilities_for_market(market_id, research_text, market_data)
                    tasks.append(task_coroutine)
            
            # Run all probability extractions in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Exception in probability extraction: {result}")
                    progress.update(task, advance=1)
                    continue
                    
                market_id, extraction = result
                if extraction is not None:
                    probability_extractions[market_id] = extraction
                    self.console.print(f"[green]✓ Extracted probabilities for {market_id}[/green]")
                    
                    # Display extracted probabilities
                    self.console.print(f"[blue]Extracted probabilities for {market_id}:[/blue]")
                    for market_prob in extraction.markets:
                        self.console.print(f"  {market_prob.ticker}: {market_prob.research_probability:.1f}%")
                else:
                    self.console.print(f"[red]✗ Failed to extract probabilities for {market_id}[/red]")
                
                progress.update(task, advance=1)
        
        self.console.print(f"[green]✓ Extracted probabilities for {len(probability_extractions)} markets[/green]")
        return probability_extractions
    
    async def _extract_probabilities_for_market(self, market_id: str, research_text: str, 
                                              market_data: Dict[str, Any]) -> Tuple[str, Optional[ProbabilityExtraction]]:
        """Extract probabilities for a single market."""
        try:
            outcomes = market_data.get('outcomes', [])
            
            # Prepare market information for the prompt
            market_info = []
            for outcome in outcomes:
                market_info.append({
                    'ticker': outcome.get('name', ''),
                    'title': outcome.get('name', ''),
                    'price': outcome.get('price', 0)
                })
            
            # Create prompt for probability extraction
            prompt = f"""
            Based on the following deep research, extract the probability estimates for each outcome.
            
            Market: {market_data.get('question', market_id)}
            
            Outcomes:
            {json.dumps(market_info, indent=2)}
            
            Research Results:
            {research_text}
            
            For each outcome, provide:
            1. The research-based probability estimate (0-100%)
            2. Clear reasoning for that probability
            3. Confidence level in the estimate (0-1)
            
            Focus on extracting concrete probability estimates from the research, not market prices.
            If the research doesn't provide a clear probability for an outcome, make your best estimate based on the available information.
            """
            
            # Use OpenAI for structured output
            response = await self.openai_client.chat.completions.create(
                model=self.config.openai.model,
                messages=[
                    {"role": "system", "content": "You are a professional prediction market analyst. Extract probability estimates from research with structured output."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.1
            )
            
            # Parse the response to extract probabilities
            content = response.choices[0].message.content
            
            # Build a single per-market YES probability (0-100)
            overall_summary = content
            yes_prob = None
            no_prob = None

            for outcome in outcomes:
                outcome_name = outcome.get('name', '')
                pattern = rf"{re.escape(outcome_name)}[:\s]*(\d+\.?\d*)%"
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    try:
                        p = float(matches[0])
                        if outcome_name.lower() in ('yes', 'up'):
                            yes_prob = p
                        elif outcome_name.lower() in ('no', 'down'):
                            no_prob = p
                    except ValueError:
                        pass

            if yes_prob is None and no_prob is None:
                any_pcts = re.findall(r'(\d+\.?\d*)%', content)
                if any_pcts:
                    try:
                        yes_prob = float(any_pcts[0])
                    except ValueError:
                        pass

            if yes_prob is None and no_prob is not None:
                yes_prob = 100.0 - float(no_prob)

            if yes_prob is not None:
                yes_prob = max(0.0, min(100.0, float(yes_prob)))
                extraction = ProbabilityExtraction(
                    markets=[
                        {
                            'ticker': market_id,
                            'title': market_data.get('question', market_id),
                            'research_probability': yes_prob,
                            'reasoning': 'Extracted YES probability from research analysis',
                            'confidence': 0.8
                        }
                    ],
                    overall_summary=overall_summary
                )
                return market_id, extraction
            else:
                return market_id, None
            
        except Exception as e:
            logger.error(f"Error extracting probabilities for {market_id}: {e}")
            return market_id, None
    
    async def get_betting_decisions(self, markets: List[Dict[str, Any]], 
                                   probability_extractions: Dict[str, ProbabilityExtraction]) -> MarketAnalysis:
        """Generate betting decisions using AI analysis."""
        self.console.print(f"\n[bold]Step 4: Generating betting decisions...[/bold]")
        
        all_decisions = []
        total_recommended_bet = 0.0
        high_confidence_bets = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("Generating betting decisions...", total=len(markets))
            
            for market in markets:
                market_id = market.get('market_id', '')
                
                if market_id not in probability_extractions:
                    progress.update(task, advance=1)
                    continue
                
                try:
                    # Generate decisions for this market
                    decisions = await self._get_market_betting_decisions(market, probability_extractions[market_id])
                    
                    # Apply risk filtering
                    filtered_decisions = self._apply_risk_filtering(decisions, market, probability_extractions[market_id])
                    
                    # Display decisions
                    self._display_market_decisions(market_id, filtered_decisions)
                    
                    # Aggregate results
                    all_decisions.extend(filtered_decisions)
                    total_recommended_bet += sum(d.amount for d in filtered_decisions if d.action != "skip")
                    high_confidence_bets += len([d for d in filtered_decisions if d.action != "skip" and d.confidence > 0.7])
                    
                    self.console.print(f"[green]✓ Generated {len(filtered_decisions)} decisions for {market_id}[/green]")
                    
                except Exception as e:
                    logger.error(f"Error generating decisions for {market_id}: {e}")
                
                progress.update(task, advance=1)
        
        # Create analysis
        analysis = MarketAnalysis(
            decisions=all_decisions,
            total_recommended_bet=total_recommended_bet,
            high_confidence_bets=high_confidence_bets,
            summary=f"Analyzed {len(markets)} Polymarket markets"
        )
        
        # Show summary
        actionable_decisions = [d for d in analysis.decisions if d.action != "skip"]
        self.console.print(f"\n[green]✓ Generated {len(analysis.decisions)} total decisions ({len(actionable_decisions)} actionable)[/green]")
        
        if actionable_decisions:
            table = Table(title="📊 All Betting Decisions Summary", show_lines=True)
            table.add_column("Market", style="bright_blue", width=30)
            table.add_column("Outcome", style="cyan", width=20)
            table.add_column("Action", style="yellow", justify="center", width=10)
            table.add_column("Confidence", style="magenta", justify="right", width=10)
            table.add_column("Amount", style="green", justify="right", width=10)
            table.add_column("Reasoning", style="blue", width=50)
            
            for decision in actionable_decisions:
                table.add_row(
                    decision.ticker[:30],
                    decision.market_name or "N/A",
                    decision.action.upper().replace('_', ' '),
                    f"{decision.confidence:.2f}",
                    f"${decision.amount:.2f}",
                    decision.reasoning[:50] + ("..." if len(decision.reasoning) > 50 else "")
                )
            
            self.console.print(table)
        
        self.console.print(f"\n[blue]Total recommended bet: ${analysis.total_recommended_bet:.2f}[/blue]")
        self.console.print(f"[blue]High confidence bets: {analysis.high_confidence_bets}[/blue]")
        
        return analysis
    
    async def _get_market_betting_decisions(self, market: Dict[str, Any], 
                                          probability_extraction: ProbabilityExtraction) -> List[BettingDecision]:
        """Get betting decisions for a single market."""
        decisions = []
        market_id = market.get('market_id', '')
        question = market.get('question', '')
        outcomes = market.get('outcomes', [])
        
        # Prefer mid-prices if available, otherwise fallback to outcome prices
        market_yes_price = 0.5  # Default
        market_no_price = 0.5   # Default
        md = getattr(self, 'market_data', {}).get(market_id, {})
        yes_mid = md.get('yes_mid_price')
        no_mid = md.get('no_mid_price')
        if isinstance(yes_mid, (int, float)) and 0 < yes_mid < 1:
            market_yes_price = float(yes_mid)
        if isinstance(no_mid, (int, float)) and 0 < no_mid < 1:
            market_no_price = float(no_mid)
        if yes_mid is None or no_mid is None:
            for outcome in outcomes:
                if outcome.get('name') == 'YES' or outcome.get('name') == 'Up':
                    market_yes_price = float(outcome.get('price', market_yes_price))
                elif outcome.get('name') == 'NO' or outcome.get('name') == 'Down':
                    market_no_price = float(outcome.get('price', market_no_price))
        
        # Get research probability for this market
        research_prob_yes = 0.5  # Default
        research_prob_no = 0.5   # Default
        
        for mp in probability_extraction.markets:
            # Per-market YES probability stored in 0-100; convert to 0-1
            if mp.ticker == market_id:
                rp_yes = float(mp.research_probability) / 100.0
                rp_yes = max(0.0, min(1.0, rp_yes))
                research_prob_yes = rp_yes
                research_prob_no = 1.0 - rp_yes
                break
        
        # Calculate expected returns and R-scores
        yes_edge = research_prob_yes - market_yes_price
        no_edge = research_prob_no - market_no_price
        
        yes_expected_return = yes_edge / market_yes_price if market_yes_price > 0 else 0
        no_expected_return = no_edge / market_no_price if market_no_price > 0 else 0
        
        yes_r_score = yes_edge / math.sqrt(research_prob_yes * (1 - research_prob_yes)) if research_prob_yes > 0 and research_prob_yes < 1 else 0
        no_r_score = no_edge / math.sqrt(research_prob_no * (1 - research_prob_no)) if research_prob_no > 0 and research_prob_no < 1 else 0
        
        # Create prompt for betting decisions
        prompt = f"""
        You are a professional prediction market trader. Based on the research provided for this Polymarket event AND the current market prices, 
        make a SINGLE betting decision for this market.
        
        Market: {question}
        Market ID: {market_id}
        
        Current Market Prices:
        - YES/Up: {market_yes_price:.3f} ({market_yes_price*100:.1f}%)
        - NO/Down: {market_no_price:.3f} ({market_no_price*100:.1f}%)
        
        Research Probabilities:
        - YES/Up: {research_prob_yes:.3f} ({research_prob_yes*100:.1f}%)
        - NO/Down: {research_prob_no:.3f} ({research_prob_no*100:.1f}%)
        
        Calculated Edges:
        - YES edge: {yes_edge:.3f} ({yes_edge*100:.1f} percentage points)
        - NO edge: {no_edge:.3f} ({no_edge*100:.1f} percentage points)
        
        Expected Returns:
        - YES expected return: {yes_expected_return:.3f} ({yes_expected_return*100:.1f}%)
        - NO expected return: {no_expected_return:.3f} ({no_expected_return*100:.1f}%)
        
        R-scores (statistical edge):
        - YES R-score: {yes_r_score:.3f}
        - NO R-score: {no_r_score:.3f}
        
        Research Summary:
        {probability_extraction.overall_summary}
        
        Max bet amount: ${self.config.max_bet_amount}
        
        DECISION CRITERIA:
        - Only bet if R-score >= {self.config.z_threshold}
        - Only bet if confidence >= 0.75
        - Only bet if expected return > 0.05 (5%)
        - Choose the side with the HIGHEST R-score and positive expected return
        
        Return your decision in this EXACT format:
        ACTION: [buy_yes|buy_no|skip]
        CONFIDENCE: [0.0-1.0]
        AMOUNT: [0-{self.config.max_bet_amount}]
        REASONING: [Brief explanation of why you chose this action]
        """
        
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.config.openai.model,
                messages=[
                    {"role": "system", "content": "You are a professional prediction market trader."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            
            # Parse the response to extract decisions
            decisions = self._parse_betting_decisions(content, market_id, question, outcomes)
            
            # Set the research probability for each decision
            for decision in decisions:
                if decision.action == 'buy_yes':
                    decision.research_probability = research_prob_yes
                elif decision.action == 'buy_no':
                    decision.research_probability = research_prob_no
                else:
                    decision.research_probability = research_prob_yes  # Default to YES probability
            
            return decisions
            
        except Exception as e:
            logger.error(f"Error generating decisions for {market_id}: {e}")
            return []
    
    def _parse_betting_decisions(self, content: str, market_id: str, question: str, 
                                outcomes: List[Dict[str, Any]]) -> List[BettingDecision]:
        """Parse betting decisions from AI response."""
        decisions = []
        
        try:
            # Parse the structured format: ACTION: buy_yes, CONFIDENCE: 0.8, etc.
            action = "skip"
            confidence = 0.0
            amount = 0.0
            reasoning = "No clear decision found"
            
            # Look for ACTION: pattern
            action_match = re.search(r"ACTION:\s*(buy_yes|buy_no|skip)", content, re.IGNORECASE)
            if action_match:
                action = action_match.group(1).lower()
            
            # Look for CONFIDENCE: pattern
            confidence_match = re.search(r"CONFIDENCE:\s*(\d+\.?\d*)", content, re.IGNORECASE)
            if confidence_match:
                confidence = float(confidence_match.group(1))
            
            # Look for AMOUNT: pattern
            amount_match = re.search(r"AMOUNT:\s*(\d+\.?\d*)", content, re.IGNORECASE)
            if amount_match:
                amount = float(amount_match.group(1))
            
            # Look for REASONING: pattern
            reasoning_match = re.search(r"REASONING:\s*([^\n]+)", content, re.IGNORECASE)
            if reasoning_match:
                reasoning = reasoning_match.group(1).strip()
            
            # Create the decision with proper research probability
            research_prob = 0.5  # Default, will be set by the calling function
            
            decision = BettingDecision(
                ticker=market_id,
                action=action,
                confidence=confidence,
                amount=amount,
                reasoning=reasoning,
                event_name=question,
                market_name="YES" if action == "buy_yes" else "NO" if action == "buy_no" else "NONE",
                research_probability=research_prob
            )
            
            decisions.append(decision)
        
        except Exception as e:
            logger.error(f"Error parsing decisions for {market_id}: {e}")
            return []
        
        return decisions
    
    def _apply_risk_filtering(self, decisions: List[BettingDecision], market: Dict[str, Any], 
                             probability_extraction: ProbabilityExtraction) -> List[BettingDecision]:
        """Apply risk-adjusted filtering to decisions."""
        filtered_decisions = []
        
        for decision in decisions:
            if decision.action == "skip":
                filtered_decisions.append(decision)
                continue
            
            # Find the corresponding probability - use market_id instead of market_name
            market_prob = None
            for mp in probability_extraction.markets:
                if mp.ticker == decision.ticker:  # Use ticker (market_id) instead of market_name
                    market_prob = mp.research_probability
                    break
            
            if market_prob is None:
                # Skip if no probability data - don't create new decisions
                decision.action = "skip"
                decision.amount = 0.0
                decision.reasoning = "Skipped due to missing probability data"
                filtered_decisions.append(decision)
                continue
            
            # Get market price (0-1). Prefer mid-prices captured earlier.
            md = getattr(self, 'market_data', {}).get(decision.ticker, {})
            if decision.market_name == 'YES' or decision.action == 'buy_yes':
                market_price = md.get('yes_mid_price') or md.get('prices', {}).get('YES') or md.get('prices', {}).get('Up') or 0
            else:
                market_price = md.get('no_mid_price') or md.get('prices', {}).get('NO') or md.get('prices', {}).get('Down') or 0
            
            if market_price == 0:
                # Skip if no market price
                skip_decision = BettingDecision(
                    ticker=decision.ticker,
                    action="skip",
                    confidence=decision.confidence,
                    amount=0.0,
                    reasoning="Skipped due to missing market price",
                    event_name=decision.event_name,
                    market_name=decision.market_name
                )
                filtered_decisions.append(skip_decision)
                continue
            
            # Calculate risk metrics
            research_prob = market_prob / 100.0
            risk_metrics = self.calculate_risk_adjusted_metrics(
                research_prob, market_price, decision.action
            )
            
            # Apply R-score filtering
            if risk_metrics["r_score"] >= self.config.z_threshold:
                # Calculate Kelly position size
                if self.config.enable_kelly_sizing:
                    kelly_size = self.calculate_kelly_position_size(risk_metrics["kelly_fraction"])
                    decision.amount = kelly_size
                
                # Enrich decision with risk metrics
                decision.expected_return = risk_metrics["expected_return"]
                decision.r_score = risk_metrics["r_score"]
                decision.kelly_fraction = risk_metrics["kelly_fraction"]
                decision.market_price = market_price
                decision.research_probability = research_prob
                
                filtered_decisions.append(decision)
            else:
                # Convert to skip if threshold not met
                skip_decision = BettingDecision(
                    ticker=decision.ticker,
                    action="skip",
                    confidence=decision.confidence,
                    amount=0.0,
                    reasoning=f"Skipped: R-score {risk_metrics['r_score']:.2f} below threshold {self.config.z_threshold:.2f}",
                    event_name=decision.event_name,
                    market_name=decision.market_name,
                    expected_return=risk_metrics["expected_return"],
                    r_score=risk_metrics["r_score"],
                    kelly_fraction=risk_metrics["kelly_fraction"],
                    market_price=market_price,
                    research_probability=research_prob
                )
                filtered_decisions.append(skip_decision)
        
        return filtered_decisions
    
    def _display_market_decisions(self, market_id: str, decisions: List[BettingDecision]):
        """Display betting decisions for a market."""
        actionable_decisions = [d for d in decisions if d.action != "skip"]
        
        if not actionable_decisions:
            return
        
        # Create market-specific table
        table = Table(title=f"Betting Decisions for {market_id[:30]}...", show_lines=True)
        table.add_column("Outcome", style="cyan", width=20)
        table.add_column("Action", style="yellow", justify="center", width=10)
        table.add_column("Confidence", style="magenta", justify="right", width=10)
        table.add_column("Amount", style="green", justify="right", width=10)
        table.add_column("Reasoning", style="blue", width=50)
        
        for decision in actionable_decisions:
            table.add_row(
                decision.market_name or "N/A",
                decision.action.upper().replace('_', ' '),
                f"{decision.confidence:.2f}",
                f"${decision.amount:.2f}",
                decision.reasoning[:50] + ("..." if len(decision.reasoning) > 50 else "")
            )
        
        self.console.print(table)
    
    async def place_bets(self, analysis: MarketAnalysis):
        """Place bets based on the analysis."""
        self.console.print(f"\n[bold]Step 5: Placing bets...[/bold]")
        
        if not analysis.decisions:
            self.console.print("[yellow]No betting decisions to execute[/yellow]")
            return
        
        actionable_decisions = [d for d in analysis.decisions if d.action != "skip"]
        
        if not actionable_decisions:
            self.console.print("[yellow]No actionable betting decisions to execute[/yellow]")
            return
        
        self.console.print(f"Found {len(actionable_decisions)} actionable decisions")
        
        for decision in actionable_decisions:
            if self.config.dry_run:
                self.console.print(f"[blue]DRY RUN: Would place {decision.action} bet of ${decision.amount} on {decision.ticker} ({decision.market_name})[/blue]")
            else:
                # Convert action to Polymarket format
                side = "buy" if decision.action == "buy_yes" else "sell"
                outcome = decision.market_name or "YES"
                
                result = await self.trading_client.place_order(
                    market_id=decision.ticker,
                    outcome=outcome,
                    side=side,
                    amount=decision.amount
                )
                
                if result.get("success"):
                    self.console.print(f"[green]✓ Placed {decision.action} bet of ${decision.amount} on {decision.ticker}[/green]")
                else:
                    self.console.print(f"[red]✗ Failed to place bet on {decision.ticker}: {result.get('error', 'Unknown error')}[/red]")
        
        if self.config.dry_run:
            self.console.print("\n[yellow]DRY RUN MODE: No actual bets were placed[/yellow]")
        else:
            self.console.print(f"\n[green]✓ Completed bet placement[/green]")
    
    async def save_betting_decisions_to_csv(self, decisions: List[BettingDecision], 
                                          filename: Optional[str] = None) -> str:
        """Save betting decisions to CSV file with detailed Polymarket data."""
        if not decisions:
            logger.warning("No betting decisions to save")
            return ""
        
        # Create betting_decisions directory if it doesn't exist
        decisions_dir = Path("betting_decisions")
        decisions_dir.mkdir(exist_ok=True)
        
        # Generate filename with timestamp
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"polymarket_betting_decisions_{timestamp}.csv"
        
        filepath = decisions_dir / filename
        
        # Write CSV with comprehensive columns (matching Kalshi format)
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'timestamp', 'event_id', 'event_title', 'market_id', 'market_title', 
                'action', 'bet_amount', 'confidence', 'reasoning', 'research_probability', 
                'research_reasoning', 'market_yes_price', 'market_no_price', 'expected_return', 
                'r_score', 'kelly_fraction', 'calc_market_prob', 'calc_research_prob',
                'is_hedge', 'hedge_for', 'research_summary', 'raw_research',
                'market_title_full', 'market_subtitle', 'market_yes_sub_title', 'market_no_sub_title',
                'market_event_id', 'market_type', 'market_start_time', 'market_end_time', 
                'market_expiration_time', 'market_status', 'market_volume', 'market_liquidity',
                'market_active', 'market_closed', 'market_archived', 'market_restricted',
                'market_volume_24h', 'market_volume_1wk', 'market_volume_1mo', 'market_volume_1yr',
                'market_liquidity_amm', 'market_liquidity_clob', 'market_accepting_orders',
                'market_best_bid', 'market_best_ask', 'market_last_trade_price', 'market_spread',
                'market_series_id', 'market_series_title', 'market_series_slug', 'market_series_type',
                'market_tags', 'market_resolution_source', 'market_outcomes', 'market_tokens'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for decision in decisions:
                # Get additional market data for this decision
                market_data = getattr(self, 'market_data', {}).get(decision.ticker, {})
                
                # Prefer mid-prices from data client if available; else fallback to outcome prices
                market_yes_price = market_data.get('yes_mid_price', 0.5)
                market_no_price = market_data.get('no_mid_price', 0.5)
                if not isinstance(market_yes_price, (int, float)) or not (0 < float(market_yes_price) < 1):
                    market_yes_price = 0.5
                if not isinstance(market_no_price, (int, float)) or not (0 < float(market_no_price) < 1):
                    market_no_price = 0.5
                if ('outcomes' in market_data) and (market_yes_price == 0.5 and market_no_price == 0.5):
                    for outcome in market_data['outcomes']:
                        if outcome.get('name') == 'YES' or outcome.get('name') == 'Up':
                            market_yes_price = float(outcome.get('price', market_yes_price))
                        elif outcome.get('name') == 'NO' or outcome.get('name') == 'Down':
                            market_no_price = float(outcome.get('price', market_no_price))
                
                # Get research probability from the decision or calculate it
                research_prob = getattr(decision, 'research_probability', 0.5)
                if research_prob == 0.5:  # Default value, try to calculate from market data
                    # This should be set during decision generation
                    research_prob = 0.5
                
                # Calculate market probability based on action
                if decision.action == 'buy_yes':
                    market_prob = market_yes_price
                    research_prob_opposite = 1.0 - research_prob
                elif decision.action == 'buy_no':
                    market_prob = market_no_price
                    research_prob_opposite = 1.0 - research_prob
                else:
                    market_prob = 0.5
                    research_prob_opposite = 0.5
                
                # Calculate expected return: E[R] = (p - y) / y where p=research_prob, y=market_prob
                expected_return = (research_prob - market_prob) / market_prob if market_prob > 0 else 0
                
                # Calculate R-score (z-score): (p - y) / sqrt(p * (1-p))
                r_score = (research_prob - market_prob) / math.sqrt(research_prob * (1 - research_prob)) if research_prob > 0 and research_prob < 1 else 0
                
                # Calculate Kelly fraction: f = (bp - q) / b where b=odds, p=prob, q=1-p
                odds = (1 - market_prob) / market_prob if market_prob > 0 else 1
                kelly_fraction = (odds * research_prob - (1 - research_prob)) / odds if odds > 0 else 0
                kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
                
                writer.writerow({
                    'timestamp': datetime.now().isoformat(),
                    'event_id': market_data.get('event_id', ''),
                    'event_title': market_data.get('event_title', market_data.get('title', '')),
                    'market_id': decision.ticker,
                    'market_title': market_data.get('question', ''),
                    'action': decision.action,
                    'bet_amount': decision.amount,
                    'confidence': decision.confidence,
                    'reasoning': decision.reasoning,
                    'research_probability': research_prob,
                    'research_reasoning': decision.reasoning,
                    'market_yes_price': market_yes_price,
                    'market_no_price': market_no_price,
                    'expected_return': expected_return,
                    'r_score': r_score,
                    'kelly_fraction': kelly_fraction,
                    'calc_market_prob': market_prob,
                    'calc_research_prob': research_prob,
                    'is_hedge': getattr(decision, 'is_hedge', False),
                    'hedge_for': getattr(decision, 'hedge_for', ''),
                    'research_summary': decision.reasoning,
                    'raw_research': decision.reasoning,
                    'market_title_full': market_data.get('title', ''),
                    'market_subtitle': market_data.get('description', ''),
                    'market_yes_sub_title': 'YES',
                    'market_no_sub_title': 'NO',
                    'market_event_id': market_data.get('event_id', ''),
                    'market_type': market_data.get('series_type', 'single'),
                    'market_start_time': market_data.get('startDate', ''),
                    'market_end_time': market_data.get('endDate', ''),
                    'market_expiration_time': market_data.get('endDate', ''),
                    'market_status': 'active' if market_data.get('active', True) else 'inactive',
                    'market_volume': market_data.get('volume', 0),
                    'market_liquidity': market_data.get('liquidity', 0),
                    'market_active': market_data.get('active', True),
                    'market_closed': market_data.get('closed', False),
                    'market_archived': market_data.get('archived', False),
                    'market_restricted': market_data.get('restricted', False),
                    'market_volume_24h': market_data.get('volume24hr', market_data.get('volume_24h', 0)),
                    'market_volume_1wk': market_data.get('volume1wk', market_data.get('volume_1wk', 0)),
                    'market_volume_1mo': market_data.get('volume1mo', market_data.get('volume_1mo', 0)),
                    'market_volume_1yr': market_data.get('volume1yr', market_data.get('volume_1yr', 0)),
                    'market_liquidity_amm': market_data.get('liquidityAmm', market_data.get('liquidity_amm', market_data.get('liquidity', 0))),
                    'market_liquidity_clob': market_data.get('liquidityClob', market_data.get('liquidity_clob', 0)),
                    'market_accepting_orders': market_data.get('acceptingOrders', market_data.get('accepting_orders', False)),
                    'market_best_bid': (market_data.get('bestBid', None) if market_data.get('bestBid', None) not in (None, 0) else market_yes_price),
                    'market_best_ask': (market_data.get('bestAsk', None) if market_data.get('bestAsk', None) not in (None, 0) else market_yes_price),
                    'market_last_trade_price': (market_data.get('lastTradePrice', None) if market_data.get('lastTradePrice', None) not in (None, 0) else market_yes_price),
                    'market_spread': (market_data.get('spread', None) if market_data.get('spread', None) not in (None,) else max(0.0, (market_data.get('bestAsk', market_yes_price) - market_data.get('bestBid', market_yes_price)) if isinstance(market_data.get('bestAsk', None), (int, float)) and isinstance(market_data.get('bestBid', None), (int, float)) else 0.0)),
                    'market_series_id': market_data.get('series_id', ''),
                    'market_series_title': market_data.get('series_title', ''),
                    'market_series_slug': market_data.get('series_slug', ''),
                    'market_series_type': market_data.get('series_type', ''),
                    'market_tags': json.dumps(market_data.get('tags', [])),
                    'market_resolution_source': market_data.get('resolutionSource', ''),
                    'market_outcomes': json.dumps(market_data.get('outcomes', [])),
                    'market_tokens': json.dumps(market_data.get('tokens', []))
                })
        
        logger.info(f"Saved {len(decisions)} betting decisions to {filepath}")
        return str(filepath)
    
    async def run(self):
        """Main bot execution."""
        try:
            await self.initialize()
            
            # Execute the main workflow
            markets = await self.get_top_markets()
            if not markets:
                self.console.print("[red]No markets found. Exiting.[/red]")
                return
            
            research_results = await self.research_markets(markets)
            if not research_results:
                self.console.print("[red]No research results. Exiting.[/red]")
                return
            
            probability_extractions = await self.extract_probabilities(research_results, markets)
            if not probability_extractions:
                self.console.print("[red]No probability extractions. Exiting.[/red]")
                return
            
            analysis = await self.get_betting_decisions(markets, probability_extractions)
            
            # Save betting decisions to CSV
            if analysis and hasattr(analysis, 'decisions') and analysis.decisions:
                csv_file = await self.save_betting_decisions_to_csv(analysis.decisions)
                self.console.print(f"[green]✓ Saved betting decisions to {csv_file}[/green]")
            
            await self.place_bets(analysis)
            
            self.console.print("\n[bold green]Polymarket bot execution completed![/bold green]")
            
        except Exception as e:
            self.console.print(f"[red]Bot execution error: {e}[/red]")
            logger.exception("Bot execution failed")
        
        finally:
            # Clean up
            if self.data_client:
                await self.data_client.close()
            if self.trading_client:
                await self.trading_client.close()


async def main(live_trading: bool = False, private_key: Optional[str] = None):
    """Main entry point."""
    bot = PolymarketTradingBot(live_trading=live_trading, private_key=private_key)
    await bot.run()


def cli():
    """Command line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Polymarket Deep Trading Bot with AI research and decision making",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Run bot in dry run mode (default)
  python main.py --live             # Run bot with live trading enabled
  python main.py --help            # Show this help message
  
Configuration:
  Create a .env file with your API keys:
    OCTAGON_API_KEY=your_octagon_api_key
    OPENAI_API_KEY=your_openai_api_key
    POLYMARKET_API_KEY=your_polymarket_api_key (optional)
    POLYMARKET_PRIVATE_KEY=your_private_key (for live trading)
    
  Optional settings:
    POLYMARKET_USE_MAINNET=true    # Use mainnet (default: true)
    MAX_MARKETS_TO_ANALYZE=50      # Max markets to analyze (default: 50)
    MAX_BET_AMOUNT=100.0           # Max bet per market (default: 100.0)
    RESEARCH_BATCH_SIZE=10         # Parallel research requests (default: 10)
    MINIMUM_LIQUIDITY=1000.0       # Minimum liquidity required (default: 1000.0)
    Z_THRESHOLD=1.5                # Minimum R-score for betting (default: 1.5)
    
  Trading modes:
    Default: Dry run mode - shows what trades would be made without placing real bets
    --live: Live trading mode - actually places bets (use with caution!)
        """
    )
    
    parser.add_argument(
        '--live',
        action='store_true',
        help='Enable live trading (default: dry run mode)'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Polymarket Trading Bot 1.0.0'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Try to load config and run bot
    try:
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        asyncio.run(main(live_trading=args.live, private_key=private_key))
    except Exception as e:
        console = Console()
        console.print(f"[red]Error: {e}[/red]")
        console.print("\n[yellow]Please check your .env file configuration.[/yellow]")
        console.print("[yellow]Run with --help for more information.[/yellow]")
        sys.exit(1)


if __name__ == "__main__":
    cli()
