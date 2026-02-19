#!/usr/bin/env python3
"""
Inference Router — Auto-failover + latency-aware routing for inference endpoints.

Features:
  1. Health checks on active inference endpoints (HTTP probe)
  2. Auto-failover: if primary provider goes down, traffic shifts to backup
  3. Latency-aware routing: pick the lowest-latency healthy provider
  4. Integrates with WebPageTest TTFB probes and simple ping latency
"""

import asyncio
import aiohttp
import json
import os
import time
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class EndpointHealth(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthProbe:
    """Result of a single health probe"""
    endpoint_id: str
    provider: str
    timestamp: datetime
    latency_ms: float
    status_code: int
    healthy: bool
    error: Optional[str] = None


@dataclass
class InferenceEndpoint:
    """Tracked inference endpoint with health state"""
    endpoint_id: str
    provider: str
    url: str
    model: str
    gpu_type: str
    region: str
    price_per_hour: float
    created_at: datetime
    # Health tracking
    health: EndpointHealth = EndpointHealth.UNKNOWN
    last_probe: Optional[HealthProbe] = None
    consecutive_failures: int = 0
    avg_latency_ms: float = 0.0
    latency_history: List[float] = field(default_factory=list)
    # Failover
    is_primary: bool = True
    backup_endpoint_id: Optional[str] = None


class InferenceRouter:
    """
    Routes inference traffic to the healthiest, lowest-latency provider.
    Handles auto-failover when a provider goes down.
    """

    # Thresholds
    HEALTH_CHECK_INTERVAL_S = 30
    UNHEALTHY_AFTER_FAILURES = 3
    DEGRADED_AFTER_FAILURES = 1
    LATENCY_HISTORY_SIZE = 20
    FAILOVER_COOLDOWN_S = 60

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / '.terradev'
        self.endpoints_file = self.config_dir / 'inference_endpoints.json'
        self.endpoints: Dict[str, InferenceEndpoint] = {}
        self._load_endpoints()
        self._last_failover: Dict[str, float] = {}

    # ── Persistence ──

    def _load_endpoints(self):
        """Load tracked endpoints from disk"""
        if self.endpoints_file.exists():
            try:
                with open(self.endpoints_file, 'r') as f:
                    data = json.load(f)
                for ep_data in data:
                    ep = InferenceEndpoint(
                        endpoint_id=ep_data['endpoint_id'],
                        provider=ep_data['provider'],
                        url=ep_data.get('url', ''),
                        model=ep_data.get('model', ''),
                        gpu_type=ep_data.get('gpu_type', ''),
                        region=ep_data.get('region', ''),
                        price_per_hour=ep_data.get('price_per_hour', 0.0),
                        created_at=datetime.fromisoformat(ep_data.get('created_at', datetime.now().isoformat())),
                        health=EndpointHealth(ep_data.get('health', 'unknown')),
                        is_primary=ep_data.get('is_primary', True),
                        backup_endpoint_id=ep_data.get('backup_endpoint_id'),
                        avg_latency_ms=ep_data.get('avg_latency_ms', 0.0),
                    )
                    self.endpoints[ep.endpoint_id] = ep
            except Exception:
                pass

    def _save_endpoints(self):
        """Persist endpoint state to disk"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = []
        for ep in self.endpoints.values():
            data.append({
                'endpoint_id': ep.endpoint_id,
                'provider': ep.provider,
                'url': ep.url,
                'model': ep.model,
                'gpu_type': ep.gpu_type,
                'region': ep.region,
                'price_per_hour': ep.price_per_hour,
                'created_at': ep.created_at.isoformat(),
                'health': ep.health.value,
                'is_primary': ep.is_primary,
                'backup_endpoint_id': ep.backup_endpoint_id,
                'avg_latency_ms': ep.avg_latency_ms,
            })
        with open(self.endpoints_file, 'w') as f:
            json.dump(data, f, indent=2)
        os.chmod(self.endpoints_file, 0o600)

    # ── Endpoint Management ──

    def register_endpoint(self, endpoint_id: str, provider: str, url: str,
                          model: str, gpu_type: str, region: str,
                          price_per_hour: float, is_primary: bool = True,
                          backup_endpoint_id: Optional[str] = None) -> InferenceEndpoint:
        """Register a new inference endpoint for health tracking and routing"""
        ep = InferenceEndpoint(
            endpoint_id=endpoint_id,
            provider=provider,
            url=url,
            model=model,
            gpu_type=gpu_type,
            region=region,
            price_per_hour=price_per_hour,
            created_at=datetime.now(),
            is_primary=is_primary,
            backup_endpoint_id=backup_endpoint_id,
        )
        self.endpoints[endpoint_id] = ep
        self._save_endpoints()
        return ep

    def remove_endpoint(self, endpoint_id: str):
        """Remove an endpoint from tracking"""
        self.endpoints.pop(endpoint_id, None)
        self._save_endpoints()

    def set_backup(self, primary_id: str, backup_id: str):
        """Link a backup endpoint to a primary"""
        if primary_id in self.endpoints and backup_id in self.endpoints:
            self.endpoints[primary_id].backup_endpoint_id = backup_id
            self.endpoints[backup_id].is_primary = False
            self._save_endpoints()

    # ── Health Checks ──

    async def probe_endpoint(self, endpoint_id: str) -> HealthProbe:
        """HTTP health probe against an inference endpoint"""
        ep = self.endpoints.get(endpoint_id)
        if not ep or not ep.url:
            return HealthProbe(
                endpoint_id=endpoint_id,
                provider=ep.provider if ep else 'unknown',
                timestamp=datetime.now(),
                latency_ms=0,
                status_code=0,
                healthy=False,
                error='No URL configured',
            )

        probe_url = ep.url.rstrip('/') + '/health'
        start = time.monotonic()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(probe_url) as resp:
                    latency_ms = (time.monotonic() - start) * 1000
                    healthy = resp.status < 500
                    return HealthProbe(
                        endpoint_id=endpoint_id,
                        provider=ep.provider,
                        timestamp=datetime.now(),
                        latency_ms=latency_ms,
                        status_code=resp.status,
                        healthy=healthy,
                    )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthProbe(
                endpoint_id=endpoint_id,
                provider=ep.provider,
                timestamp=datetime.now(),
                latency_ms=latency_ms,
                status_code=0,
                healthy=False,
                error=str(e),
            )

    async def check_all_endpoints(self) -> Dict[str, HealthProbe]:
        """Probe all registered endpoints in parallel"""
        tasks = {eid: self.probe_endpoint(eid) for eid in self.endpoints}
        results = {}
        if tasks:
            done = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for eid, result in zip(tasks.keys(), done):
                if isinstance(result, Exception):
                    results[eid] = HealthProbe(
                        endpoint_id=eid,
                        provider=self.endpoints[eid].provider,
                        timestamp=datetime.now(),
                        latency_ms=0,
                        status_code=0,
                        healthy=False,
                        error=str(result),
                    )
                else:
                    results[eid] = result
                self._update_health(eid, results[eid])
        self._save_endpoints()
        return results

    def _update_health(self, endpoint_id: str, probe: HealthProbe):
        """Update endpoint health state from probe result"""
        ep = self.endpoints.get(endpoint_id)
        if not ep:
            return

        ep.last_probe = probe

        if probe.healthy:
            ep.consecutive_failures = 0
            ep.health = EndpointHealth.HEALTHY
            # Track latency
            ep.latency_history.append(probe.latency_ms)
            if len(ep.latency_history) > self.LATENCY_HISTORY_SIZE:
                ep.latency_history = ep.latency_history[-self.LATENCY_HISTORY_SIZE:]
            ep.avg_latency_ms = sum(ep.latency_history) / len(ep.latency_history)
        else:
            ep.consecutive_failures += 1
            if ep.consecutive_failures >= self.UNHEALTHY_AFTER_FAILURES:
                ep.health = EndpointHealth.UNHEALTHY
            elif ep.consecutive_failures >= self.DEGRADED_AFTER_FAILURES:
                ep.health = EndpointHealth.DEGRADED

    # ── Auto-Failover ──

    async def check_and_failover(self) -> List[Dict]:
        """Run health checks and trigger failover for unhealthy primaries.
        Returns list of failover events."""
        probes = await self.check_all_endpoints()
        failover_events = []

        for eid, probe in probes.items():
            ep = self.endpoints.get(eid)
            if not ep or not ep.is_primary:
                continue

            if ep.health == EndpointHealth.UNHEALTHY and ep.backup_endpoint_id:
                # Cooldown check
                last = self._last_failover.get(eid, 0)
                if time.time() - last < self.FAILOVER_COOLDOWN_S:
                    continue

                backup = self.endpoints.get(ep.backup_endpoint_id)
                if backup and backup.health in (EndpointHealth.HEALTHY, EndpointHealth.UNKNOWN):
                    # Promote backup to primary
                    backup.is_primary = True
                    ep.is_primary = False
                    ep.backup_endpoint_id = None
                    backup.backup_endpoint_id = eid  # old primary becomes backup
                    self._last_failover[eid] = time.time()

                    event = {
                        'type': 'failover',
                        'timestamp': datetime.now().isoformat(),
                        'failed_endpoint': eid,
                        'failed_provider': ep.provider,
                        'new_primary': backup.endpoint_id,
                        'new_provider': backup.provider,
                        'reason': f'{ep.consecutive_failures} consecutive health check failures',
                    }
                    failover_events.append(event)
                    logger.warning(
                        f"FAILOVER: {ep.provider}/{eid} → {backup.provider}/{backup.endpoint_id}"
                    )

        if failover_events:
            self._save_endpoints()
            self._save_failover_log(failover_events)

        return failover_events

    def _save_failover_log(self, events: List[Dict]):
        """Append failover events to audit log"""
        log_file = self.config_dir / 'failover_log.json'
        existing = []
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing.extend(events)
        with open(log_file, 'w') as f:
            json.dump(existing, f, indent=2)
        os.chmod(log_file, 0o600)

    # ── Latency-Aware Routing ──

    async def measure_latency_ping(self, target: str, count: int = 3) -> Optional[float]:
        """Measure latency to a target via async ping (ms)"""
        try:
            proc = await asyncio.create_subprocess_exec(
                'ping', '-c', str(count), '-W', '2', target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode()
            latencies = []
            for line in output.split('\n'):
                if 'time=' in line:
                    t = float(line.split('time=')[1].split()[0])
                    latencies.append(t)
            return sum(latencies) / len(latencies) if latencies else None
        except Exception:
            return None

    async def measure_latency_wpt(self, url: str, wpt_api_key: Optional[str] = None) -> Optional[float]:
        """Measure TTFB via WebPageTest API (ms).
        Falls back to direct HTTP probe if no WPT key."""
        if wpt_api_key:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                    # Submit test
                    params = {
                        'url': url,
                        'f': 'json',
                        'k': wpt_api_key,
                        'runs': '1',
                        'fvonly': '1',
                    }
                    async with session.get('https://www.webpagetest.org/runtest.php', params=params) as resp:
                        result = await resp.json()
                        test_id = result.get('data', {}).get('testId')
                        if not test_id:
                            return None

                    # Poll for result (up to 60s)
                    for _ in range(12):
                        await asyncio.sleep(5)
                        async with session.get(
                            f'https://www.webpagetest.org/jsonResult.php?test={test_id}'
                        ) as resp:
                            result = await resp.json()
                            status = result.get('statusCode', 0)
                            if status == 200:
                                ttfb = (result.get('data', {})
                                        .get('runs', {}).get('1', {})
                                        .get('firstView', {}).get('TTFB', None))
                                return float(ttfb) if ttfb is not None else None
                    return None
            except Exception:
                return None

        # Fallback: direct HTTP TTFB probe
        try:
            start = time.monotonic()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url) as resp:
                    ttfb_ms = (time.monotonic() - start) * 1000
                    return ttfb_ms
        except Exception:
            return None

    def get_best_endpoint(self, model: Optional[str] = None,
                          strategy: str = 'latency') -> Optional[InferenceEndpoint]:
        """Select the best healthy endpoint for routing.

        Strategies:
          - 'latency': lowest average latency (default)
          - 'cost': lowest price per hour
          - 'score': combined latency + cost score
        """
        candidates = [
            ep for ep in self.endpoints.values()
            if ep.health in (EndpointHealth.HEALTHY, EndpointHealth.UNKNOWN)
            and (model is None or ep.model == model)
        ]

        if not candidates:
            return None

        if strategy == 'latency':
            # Sort by avg latency, break ties by price
            candidates.sort(key=lambda e: (e.avg_latency_ms or 9999, e.price_per_hour))
        elif strategy == 'cost':
            candidates.sort(key=lambda e: (e.price_per_hour, e.avg_latency_ms or 9999))
        elif strategy == 'score':
            # Weighted: 60% latency, 40% cost
            max_lat = max(e.avg_latency_ms for e in candidates) or 1
            max_price = max(e.price_per_hour for e in candidates) or 1
            candidates.sort(key=lambda e: (
                0.6 * ((e.avg_latency_ms or 9999) / max_lat) +
                0.4 * (e.price_per_hour / max_price)
            ))

        return candidates[0]

    # ── Status Report ──

    def get_status(self) -> Dict:
        """Get full inference routing status"""
        endpoints = []
        for ep in self.endpoints.values():
            endpoints.append({
                'endpoint_id': ep.endpoint_id,
                'provider': ep.provider,
                'model': ep.model,
                'health': ep.health.value,
                'avg_latency_ms': round(ep.avg_latency_ms, 1),
                'price_per_hour': ep.price_per_hour,
                'is_primary': ep.is_primary,
                'backup': ep.backup_endpoint_id,
                'consecutive_failures': ep.consecutive_failures,
                'region': ep.region,
            })

        healthy = sum(1 for e in self.endpoints.values() if e.health == EndpointHealth.HEALTHY)
        total = len(self.endpoints)

        return {
            'total_endpoints': total,
            'healthy': healthy,
            'unhealthy': total - healthy,
            'endpoints': endpoints,
        }
