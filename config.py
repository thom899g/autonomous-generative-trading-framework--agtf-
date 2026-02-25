"""
AGTF Configuration Management
Centralized configuration with environment variables and Firebase integration
"""
import os
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, db
from google.cloud.firestore import Client as FirestoreClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agtf.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ExchangeConfig:
    """Exchange-specific configuration"""
    name: str
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    sandbox: bool = True
    rate_limit: int = 1000
    markets: List[str] = field(default_factory=lambda: ['BTC/USDT', 'ETH/USDT'])
    
    def __post_init__(self):
        if not self.api_key or not self.api_secret:
            logger.warning(f"Exchange {self.name} missing credentials")

@dataclass
class ModelConfig:
    """Generative model configuration"""
    model_type: str = "vae"  # vae, gan, transformer
    hidden_dim: int = 256
    latent_dim: int = 32
    learning_rate: float = 0.001
    batch_size: int = 64
    sequence_length: int = 100
    retrain_interval: int = 3600  # seconds
    
    def validate(self) -> bool:
        """Validate model configuration"""
        valid_types = ["vae", "gan", "transformer"]
        if self.model_type not in valid_types:
            logger.error(f"Invalid model type: {self.model_type}")
            return False
        if self.latent_dim <= 0:
            logger.error("Latent dimension must be positive")
            return False
        return True

@dataclass
class RiskConfig:
    """Risk management configuration"""
    max_position_size: float = 0.1  # 10% of portfolio
    max_daily_loss: float = 0.02   # 2% daily loss limit
    stop_loss_pct: float = 0.01    # 1% stop loss
    take_profit_pct: float = 0.02  # 2% take profit
    max_leverage: float = 3.0
    cooldown_period: int = 300     # seconds after loss
    
    def validate(self) -> bool:
        """Validate risk parameters"""
        if self.max_position_size <= 0 or self.max_position_size > 1:
            logger.error("max_position_size must be between 0 and 1")
            return False
        if self.max_daily_loss <= 0 or self.max_daily_loss > 0.5:
            logger.error("max_daily_loss must be reasonable (0-0.5)")
            return False
        return True

class ConfigManager:
    """Centralized configuration management with Firebase integration"""
    
    def __init__(self, firebase_creds_path: Optional[str] = None):
        self.config = {}
        self.firestore_client: Optional[FirestoreClient] = None
        
        # Initialize Firebase if credentials available
        if firebase_creds_path and os.path.exists(firebase_creds_path):
            try:
                cred = credentials.Certificate(firebase_creds_path)
                firebase_admin.initialize_app(cred, {
                    'projectId': os.getenv('FIREBASE_PROJECT_ID', 'agtf-default')
                })
                self.firestore_client = firestore.client()
                logger.info("Firebase initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Firebase: {e}")
        
        # Load configurations
        self._load_environment_config()
        self._load_local_config()
        
        # Validate configurations
        self._validate_configs()
    
    def _load_environment_config(self):
        """Load configuration from environment variables"""
        self.config['exchange'] = ExchangeConfig(
            name=os.getenv('EXCHANGE_NAME', 'binance'),
            api_key=os.getenv('EXCHANGE_API_KEY', ''),
            api_secret=os.getenv('EXCHANGE_API_SECRET', ''),
            sandbox=os.getenv('EXCHANGE_SANDBOX', 'true').lower() == 'true'
        )
        
        self.config['model'] = ModelConfig(
            model_type=os.getenv('MODEL_TYPE', 'vae'),
            hidden_dim=int(os.getenv('MODEL_HIDDEN_DIM', '256')),
            latent_dim=int(os.getenv('MODEL_LATENT_DIM', '32'))
        )
        
        self.config['risk'] = RiskConfig(
            max_position_size=float(os.getenv('MAX_POSITION_SIZE', '0.1')),
            max_daily_loss=float(os.getenv('MAX_DAILY_LOSS', '0.02'))
        )
    
    def _load_local_config(self):
        """Load configuration from local JSON file if exists"""
        config_path = 'config/local_config.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    local_config = json.load(f)
                    self.config.update(local_config)
                logger.info(f"Loaded local config from {config_path}")
            except Exception as e:
                logger.error