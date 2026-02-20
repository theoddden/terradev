#!/usr/bin/env python3
"""
Warm Pool Manager - Intelligent pre-warming strategies for bursty workloads

Addresses Reddit post pain points:
1. "Scale to zero" is not enough - intelligent warm pool instead
2. Warm pools don't become manual capacity planning - automated management
3. Reduces cold start latency without wasting VRAM
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class WarmStrategy(Enum):
    """Warm pool management strategies"""
    TRAFFIC_BASED = "traffic_based"          # Warm models based on recent traffic
    TIME_BASED = "time_based"                # Warm models during peak hours
    PRIORITY_BASED = "priority_based"        # Always keep high-priority models warm
    COST_OPTIMIZED = "cost_optimized"        # Minimize warm pool size
    LATENCY_OPTIMIZED = "latency_optimized"  # Maximize warm pool for performance


@dataclass
class WarmPoolConfig:
    """Configuration for warm pool management"""
    max_warm_models: int = 10               # Maximum models to keep warm
    min_warm_models: int = 3                # Minimum models to keep warm
    warm_threshold_rph: float = 5.0         # Requests per hour to consider warming
    idle_eviction_minutes: int = 15         # Minutes of idle time before eviction
    peak_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 14, 15, 16, 17, 18])
    strategy: WarmStrategy = WarmStrategy.TRAFFIC_BASED
    enable_predictive_warming: bool = True  # Use traffic patterns to predict warming


@dataclass
class WarmPoolMetrics:
    """Metrics for warm pool performance"""
    total_warm_requests: int = 0
    cold_start_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_warm_latency_ms: float = 0.0
    avg_cold_latency_ms: float = 0.0
    memory_saved_gb: float = 0.0
    cost_saved_usd: float = 0.0


class WarmPoolManager:
    """
    Intelligent warm pool manager for multi-model inference.
    
    Solves the "warm pools become manual capacity planning" problem by:
    1. Automatically managing warm pool size based on traffic patterns
    2. Predictive warming based on historical usage
    3. Cost-aware eviction policies
    4. Performance monitoring and optimization
    """
    
    def __init__(self, config: WarmPoolConfig, config_dir: Optional[Path] = None):
        self.config = config
        self.config_dir = config_dir or Path.home() / '.terradev'
        
        # Warm pool state
        self.warm_models: Set[str] = set()
        self.warming_models: Set[str] = set()
        self.model_priorities: Dict[str, int] = {}
        self.model_traffic: Dict[str, List[datetime]] = {}
        self.model_load_times: Dict[str, float] = {}
        
        # Metrics tracking
        self.metrics = WarmPoolMetrics()
        self.metrics_file = self.config_dir / 'warm_pool_metrics.json'
        self.traffic_file = self.config_dir / 'model_traffic.json'
        
        # Background tasks
        self._warming_task: Optional[asyncio.Task] = None
        self._eviction_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Load historical data
        self._load_metrics()
        self._load_traffic_history()
    
    async def start(self):
        """Start warm pool management background tasks"""
        self._running = True
        self._warming_task = asyncio.create_task(self._warming_manager())
        self._eviction_task = asyncio.create_task(self._eviction_manager())
        logger.info("Warm Pool Manager started")
    
    async def stop(self):
        """Stop warm pool management"""
        self._running = False
        if self._warming_task:
            self._warming_task.cancel()
        if self._eviction_task:
            self._eviction_task.cancel()
        logger.info("Warm Pool Manager stopped")
    
    # ── Model Management ──
    
    def register_model(self, model_id: str, priority: int = 0):
        """Register a model for warm pool management"""
        self.model_priorities[model_id] = priority
        if model_id not in self.model_traffic:
            self.model_traffic[model_id] = []
    
    def record_request(self, model_id: str, latency_ms: float, was_warm: bool):
        """Record an inference request for traffic analysis"""
        now = datetime.now()
        
        # Record traffic
        if model_id not in self.model_traffic:
            self.model_traffic[model_id] = []
        self.model_traffic[model_id].append(now)
        
        # Update metrics
        self.metrics.total_warm_requests += 1
        if was_warm:
            self.metrics.cache_hits += 1
            # Update warm latency average
            self.metrics.avg_warm_latency_ms = (
                (self.metrics.avg_warm_latency_ms * (self.metrics.cache_hits - 1) + latency_ms) 
                / self.metrics.cache_hits
            )
        else:
            self.metrics.cache_misses += 1
            self.metrics.cold_start_requests += 1
            # Update cold latency average
            self.metrics.avg_cold_latency_ms = (
                (self.metrics.avg_cold_latency_ms * (self.metrics.cold_start_requests - 1) + latency_ms) 
                / self.metrics.cold_start_requests
            )
        
        # Clean old traffic data (keep last 7 days)
        cutoff = now - timedelta(days=7)
        self.model_traffic[model_id] = [
            timestamp for timestamp in self.model_traffic[model_id] 
            if timestamp > cutoff
        ]
        
        self._save_metrics()
        self._save_traffic_history()
    
    def should_warm_model(self, model_id: str) -> bool:
        """Determine if a model should be warmed based on strategy"""
        if model_id in self.warm_models or model_id in self.warming_models:
            return True
        
        if len(self.warm_models) >= self.config.max_warm_models:
            return False
        
        now = datetime.now()
        
        if self.config.strategy == WarmStrategy.TRAFFIC_BASED:
            return self._should_warm_traffic_based(model_id, now)
        elif self.config.strategy == WarmStrategy.TIME_BASED:
            return self._should_warm_time_based(model_id, now)
        elif self.config.strategy == WarmStrategy.PRIORITY_BASED:
            return self._should_warm_priority_based(model_id)
        elif self.config.strategy == WarmStrategy.COST_OPTIMIZED:
            return self._should_warm_cost_optimized(model_id, now)
        elif self.config.strategy == WarmStrategy.LATENCY_OPTIMIZED:
            return self._should_warm_latency_optimized(model_id)
        
        return False
    
    def _should_warm_traffic_based(self, model_id: str, now: datetime) -> bool:
        """Traffic-based warming: warm models with recent requests"""
        if model_id not in self.model_traffic:
            return False
        
        # Calculate requests per hour
        recent_requests = [
            timestamp for timestamp in self.model_traffic[model_id]
            if now - timestamp < timedelta(hours=1)
        ]
        
        rph = len(recent_requests)
        return rph >= self.config.warm_threshold_rph
    
    def _should_warm_time_based(self, model_id: str, now: datetime) -> bool:
        """Time-based warming: warm models during peak hours"""
        if now.hour not in self.config.peak_hours:
            return False
        
        # During peak hours, warm models with any recent traffic
        if model_id not in self.model_traffic:
            return False
        
        recent_requests = [
            timestamp for timestamp in self.model_traffic[model_id]
            if now - timestamp < timedelta(hours=2)
        ]
        
        return len(recent_requests) > 0
    
    def _should_warm_priority_based(self, model_id: str) -> bool:
        """Priority-based warming: always keep high-priority models warm"""
        priority = self.model_priorities.get(model_id, 0)
        
        # Always warm models with priority >= 5
        if priority >= 5:
            return True
        
        # For lower priority models, check if we have room
        if len(self.warm_models) < self.config.min_warm_models:
            return priority >= 3
        
        return False
    
    def _should_warm_cost_optimized(self, model_id: str, now: datetime) -> bool:
        """Cost-optimized warming: minimal warm pool"""
        # Only warm models with very high traffic
        if model_id not in self.model_traffic:
            return False
        
        recent_requests = [
            timestamp for timestamp in self.model_traffic[model_id]
            if now - timestamp < timedelta(hours=1)
        ]
        
        rph = len(recent_requests)
        return rph >= self.config.warm_threshold_rph * 2  # Higher threshold
    
    def _should_warm_latency_optimized(self, model_id: str, now: datetime) -> bool:
        """Latency-optimized warming: aggressive warming"""
        # Warm models with any recent traffic
        if model_id not in self.model_traffic:
            return False
        
        recent_requests = [
            timestamp for timestamp in self.model_traffic[model_id]
            if now - timestamp < timedelta(hours=3)
        ]
        
        return len(recent_requests) > 0
    
    def mark_model_warming(self, model_id: str):
        """Mark a model as currently warming"""
        self.warming_models.add(model_id)
    
    def mark_model_warm(self, model_id: str, load_time_s: float):
        """Mark a model as successfully warmed"""
        self.warming_models.discard(model_id)
        self.warm_models.add(model_id)
        self.model_load_times[model_id] = load_time_s
        
        logger.info(f"Model {model_id} warmed in {load_time_s:.1f}s")
    
    def mark_model_evicted(self, model_id: str):
        """Mark a model as evicted from warm pool"""
        self.warm_models.discard(model_id)
        self.warming_models.discard(model_id)
        
        logger.info(f"Model {model_id} evicted from warm pool")
    
    # ── Background Tasks ──
    
    async def _warming_manager(self):
        """Background task to manage model warming"""
        while self._running:
            try:
                await self._manage_warming()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Warming manager error: {e}")
                await asyncio.sleep(60)
    
    async def _eviction_manager(self):
        """Background task to manage model eviction"""
        while self._running:
            try:
                await self._manage_eviction()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Eviction manager error: {e}")
                await asyncio.sleep(60)
    
    async def _manage_warming(self):
        """Manage which models should be warmed"""
        # Get all registered models
        all_models = set(self.model_priorities.keys())
        
        # Find models that should be warm
        should_warm = {
            model_id for model_id in all_models
            if self.should_warm_model(model_id)
        }
        
        # Models to warm (should be warm but aren't)
        to_warm = should_warm - self.warm_models - self.warming_models
        
        # Models to evict (warm but shouldn't be)
        to_evict = (self.warm_models | self.warming_models) - should_warm
        
        # Respect capacity limits
        available_slots = self.config.max_warm_models - len(self.warm_models) - len(self.warming_models)
        if len(to_warm) > available_slots:
            # Sort by priority and traffic
            to_warm = sorted(to_warm, key=lambda m: (
                -self.model_priorities.get(m, 0),  # Higher priority first
                -len(self.model_traffic.get(m, []))  # More traffic first
            ))[:available_slots]
        
        # Log actions
        for model_id in to_warm:
            logger.info(f"Warming model: {model_id}")
        
        for model_id in to_evict:
            logger.info(f"Will evict model: {model_id}")
    
    async def _manage_eviction(self):
        """Manage eviction of idle models"""
        now = datetime.now()
        idle_threshold = timedelta(minutes=self.config.idle_eviction_minutes)
        
        # Find models that have been idle too long
        to_evict = set()
        
        for model_id in self.warm_models:
            if model_id not in self.model_traffic:
                continue
            
            # Find most recent request
            recent_requests = self.model_traffic[model_id]
            if not recent_requests:
                continue
            
            last_request = max(recent_requests)
            if now - last_request > idle_threshold:
                to_evict.add(model_id)
        
        # Don't evict if we're below minimum warm pool size
        if len(self.warm_models) - len(to_evict) < self.config.min_warm_models:
            # Only evict models with lowest priority
            evictable = sorted(to_evict, key=lambda m: self.model_priorities.get(m, 0))
            slots_available = len(self.warm_models) - self.config.min_warm_models
            to_evict = set(evictable[:slots_available])
        
        # Evict models
        for model_id in to_evict:
            self.mark_model_evicted(model_id)
    
    # ── Predictive Warming ──
    
    def predict_traffic(self, model_id: str, hours_ahead: int = 1) -> float:
        """Predict traffic for a model hours ahead based on historical patterns"""
        if not self.config.enable_predictive_warming:
            return 0.0
        
        if model_id not in self.model_traffic:
            return 0.0
        
        now = datetime.now()
        target_hour = (now + timedelta(hours=hours_ahead)).hour
        
        # Get traffic for same hour in previous days
        same_hour_traffic = []
        for days_ago in range(1, 8):  # Look back 7 days
            past_time = now - timedelta(days=days_ago)
            if past_time.hour == target_hour:
                day_traffic = [
                    timestamp for timestamp in self.model_traffic[model_id]
                    if past_time.date() == timestamp.date()
                ]
                same_hour_traffic.append(len(day_traffic))
        
        if not same_hour_traffic:
            return 0.0
        
        # Return average traffic for this hour
        return sum(same_hour_traffic) / len(same_hour_traffic)
    
    def get_predictive_warming_candidates(self, hours_ahead: int = 1) -> List[Tuple[str, float]]:
        """Get models that should be pre-warmed based on predicted traffic"""
        candidates = []
        
        for model_id in self.model_priorities.keys():
            predicted_traffic = self.predict_traffic(model_id, hours_ahead)
            if predicted_traffic >= self.config.warm_threshold_rph:
                candidates.append((model_id, predicted_traffic))
        
        # Sort by predicted traffic
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates
    
    # ── Metrics and Reporting ──
    
    def get_status(self) -> Dict:
        """Get warm pool status"""
        cache_hit_rate = (
            self.metrics.cache_hits / max(1, self.metrics.total_warm_requests)
        )
        
        return {
            'warm_models_count': len(self.warm_models),
            'warming_models_count': len(self.warming_models),
            'total_models': len(self.model_priorities),
            'strategy': self.config.strategy.value,
            'cache_hit_rate': cache_hit_rate,
            'total_requests': self.metrics.total_warm_requests,
            'cold_starts': self.metrics.cold_start_requests,
            'avg_warm_latency_ms': self.metrics.avg_warm_latency_ms,
            'avg_cold_latency_ms': self.metrics.avg_cold_latency_ms,
            'memory_saved_gb': self.metrics.memory_saved_gb,
            'cost_saved_usd': self.metrics.cost_saved_usd,
        }
    
    def get_model_details(self, model_id: str) -> Optional[Dict]:
        """Get detailed information about a model"""
        if model_id not in self.model_priorities:
            return None
        
        is_warm = model_id in self.warm_models
        is_warming = model_id in self.warming_models
        
        # Calculate recent traffic
        now = datetime.now()
        recent_traffic = [
            timestamp for timestamp in self.model_traffic.get(model_id, [])
            if now - timestamp < timedelta(hours=1)
        ]
        
        return {
            'model_id': model_id,
            'priority': self.model_priorities[model_id],
            'is_warm': is_warm,
            'is_warming': is_warming,
            'requests_per_hour': len(recent_traffic),
            'total_requests': len(self.model_traffic.get(model_id, [])),
            'load_time_s': self.model_load_times.get(model_id, 0.0),
            'predicted_traffic_1h': self.predict_traffic(model_id, 1),
            'predicted_traffic_2h': self.predict_traffic(model_id, 2),
        }
    
    def _load_metrics(self):
        """Load metrics from disk"""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    self.metrics = WarmPoolMetrics(**data)
            except Exception as e:
                logger.warning(f"Failed to load warm pool metrics: {e}")
    
    def _save_metrics(self):
        """Save metrics to disk"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            'total_warm_requests': self.metrics.total_warm_requests,
            'cold_start_requests': self.metrics.cold_start_requests,
            'cache_hits': self.metrics.cache_hits,
            'cache_misses': self.metrics.cache_misses,
            'avg_warm_latency_ms': self.metrics.avg_warm_latency_ms,
            'avg_cold_latency_ms': self.metrics.avg_cold_latency_ms,
            'memory_saved_gb': self.metrics.memory_saved_gb,
            'cost_saved_usd': self.metrics.cost_saved_usd,
        }
        
        with open(self.metrics_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_traffic_history(self):
        """Load traffic history from disk"""
        if self.traffic_file.exists():
            try:
                with open(self.traffic_file, 'r') as f:
                    data = json.load(f)
                    self.model_traffic = {
                        model_id: [datetime.fromisoformat(ts) for ts in timestamps]
                        for model_id, timestamps in data.items()
                    }
            except Exception as e:
                logger.warning(f"Failed to load traffic history: {e}")
                self.model_traffic = {}
    
    def _save_traffic_history(self):
        """Save traffic history to disk"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            model_id: [ts.isoformat() for ts in timestamps]
            for model_id, timestamps in self.model_traffic.items()
        }
        
        with open(self.traffic_file, 'w') as f:
            json.dump(data, f, indent=2)
