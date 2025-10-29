"""
Configuration management for the Polymarket trading bot.
"""
import os
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class PolymarketConfig(BaseModel):
    """Polymarket API configuration."""
    api_key: Optional[str] = Field(None, description="Polymarket API key (optional)")
    base_url: str = Field(default="https://gamma-api.polymarket.com", description="Polymarket API base URL")
    use_mainnet: bool = Field(default=True, description="Use mainnet (True) or testnet (False)")
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if v and v == "your_polymarket_api_key_here":
            return None  # Optional API key
        return v

class OctagonConfig(BaseModel):
    """Octagon Deep Research API configuration."""
    api_key: str = Field(..., description="Octagon API key")
    base_url: str = Field(default="https://api.octagon.ai", description="Octagon API base URL")
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or v == "your_octagon_api_key_here":
            raise ValueError("OCTAGON_API_KEY is required. Please set it in your .env file.")
        return v

class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""
    api_key: str = Field(..., description="OpenAI API key")
    model: str = Field(default="gpt-4o", description="OpenAI model to use")
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or v == "your_openai_api_key_here":
            raise ValueError("OPENAI_API_KEY is required. Please set it in your .env file.")
        return v

def _clean_env_value(value: str) -> str:
    """Clean environment variable value by removing inline comments."""
    return value.split('#')[0].strip()

class PolymarketBotConfig(BaseSettings):
    """Main Polymarket bot configuration."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra='allow')
    
    # API configurations
    polymarket: PolymarketConfig = Field(..., description="Polymarket configuration")
    octagon: OctagonConfig = Field(..., description="Octagon configuration")
    openai: OpenAIConfig = Field(..., description="OpenAI configuration")
    
    # Bot settings
    dry_run: bool = Field(default=True, description="Run in dry-run mode (overridden by CLI)")
    max_bet_amount: float = Field(default=100.0, description="Maximum bet amount per market")
    max_markets_to_analyze: int = Field(default=50, description="Number of top markets to analyze by volume")
    research_batch_size: int = Field(default=10, description="Number of parallel deep research requests")
    research_timeout_seconds: int = Field(default=900, description="Per-market research timeout in seconds")
    skip_existing_positions: bool = Field(default=True, description="Skip betting on markets where we already have positions")
    minimum_liquidity: float = Field(default=1000.0, description="Minimum liquidity required for a market")
    
    # Risk management parameters
    z_threshold: float = Field(default=1.5, description="Minimum R-score (z-score) threshold for placing bets")
    enable_kelly_sizing: bool = Field(default=True, description="Use Kelly criterion for position sizing")
    kelly_fraction: float = Field(default=0.5, ge=0.1, le=1.0, description="Fraction of Kelly to use (0.5 = half-Kelly)")
    max_kelly_bet_fraction: float = Field(default=0.1, ge=0.01, le=0.5, description="Maximum fraction of bankroll per bet")
    bankroll: float = Field(default=1000.0, description="Total bankroll for Kelly sizing calculations")
    
    # Portfolio management
    max_portfolio_positions: int = Field(default=10, description="Maximum number of positions to hold simultaneously")
    portfolio_selection_method: str = Field(default="top_r_scores", description="Method for portfolio selection")
    
    # Hedging settings
    enable_hedging: bool = Field(default=True, description="Enable hedging to minimize risk")
    hedge_ratio: float = Field(default=0.25, ge=0, le=0.5, description="Default hedge ratio")
    min_confidence_for_hedging: float = Field(default=0.6, ge=0, le=1, description="Only hedge bets with confidence below this threshold")
    max_hedge_amount: float = Field(default=50.0, description="Maximum hedge amount per bet")
    
    def __init__(self, **data):
        # Build nested configs from environment variables
        polymarket_config = PolymarketConfig(
            api_key=os.getenv("POLYMARKET_API_KEY", ""),
            base_url=os.getenv("POLYMARKET_BASE_URL", "https://gamma-api.polymarket.com"),
            use_mainnet=os.getenv("POLYMARKET_USE_MAINNET", "true").lower() == "true"
        )
        
        octagon_config = OctagonConfig(
            api_key=os.getenv("OCTAGON_API_KEY", ""),
            base_url=os.getenv("OCTAGON_BASE_URL", "https://api.octagon.ai")
        )
        
        openai_config = OpenAIConfig(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", "gpt-4o")
        )
        
        data.update({
            "polymarket": polymarket_config,
            "octagon": octagon_config,
            "openai": openai_config,
            "dry_run": True,  # Default to dry run, overridden by CLI
            "max_bet_amount": float(_clean_env_value(os.getenv("MAX_BET_AMOUNT", "100.0"))),
            "max_markets_to_analyze": int(_clean_env_value(os.getenv("MAX_MARKETS_TO_ANALYZE", "50"))),
            "research_batch_size": int(_clean_env_value(os.getenv("RESEARCH_BATCH_SIZE", "10"))),
            "research_timeout_seconds": int(_clean_env_value(os.getenv("RESEARCH_TIMEOUT_SECONDS", "900"))),
            "skip_existing_positions": _clean_env_value(os.getenv("SKIP_EXISTING_POSITIONS", "true")).lower() == "true",
            "minimum_liquidity": float(_clean_env_value(os.getenv("MINIMUM_LIQUIDITY", "1000.0"))),
            "z_threshold": float(_clean_env_value(os.getenv("Z_THRESHOLD", "1.5"))),
            "enable_kelly_sizing": _clean_env_value(os.getenv("ENABLE_KELLY_SIZING", "true")).lower() == "true",
            "kelly_fraction": float(_clean_env_value(os.getenv("KELLY_FRACTION", "0.5"))),
            "max_kelly_bet_fraction": float(_clean_env_value(os.getenv("MAX_KELLY_BET_FRACTION", "0.1"))),
            "bankroll": float(_clean_env_value(os.getenv("BANKROLL", "1000.0"))),
            "max_portfolio_positions": int(_clean_env_value(os.getenv("MAX_PORTFOLIO_POSITIONS", "10"))),
            "portfolio_selection_method": os.getenv("PORTFOLIO_SELECTION_METHOD", "top_r_scores"),
            "enable_hedging": _clean_env_value(os.getenv("ENABLE_HEDGING", "true")).lower() == "true",
            "hedge_ratio": float(_clean_env_value(os.getenv("HEDGE_RATIO", "0.25"))),
            "min_confidence_for_hedging": float(_clean_env_value(os.getenv("MIN_CONFIDENCE_FOR_HEDGING", "0.6"))),
            "max_hedge_amount": float(_clean_env_value(os.getenv("MAX_HEDGE_AMOUNT", "50.0")))
        })
        
        super().__init__(**data)

def load_config() -> PolymarketBotConfig:
    """Load and validate configuration."""
    return PolymarketBotConfig()
