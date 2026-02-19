#!/usr/bin/env python3
"""
Egress Optimizer — Intelligent data routing to minimize transfer costs between clouds.

Knows the real egress pricing for each cloud and finds the cheapest path
to move data between any two (provider, region) pairs.
"""

from typing import Dict, List, Any, Tuple, Optional


# ── Egress pricing per GB (USD) ──────────────────────────────────────
# Source: public pricing pages as of 2025-Q4.  Intra-region is free on
# most clouds; same-continent cross-region is cheaper than intercontinental.

EGRESS_RATES: Dict[str, Dict[str, float]] = {
    # provider -> { destination_class: $/GB }
    "aws": {
        "same_region": 0.00,
        "same_continent": 0.01,
        "cross_continent": 0.09,
        "internet": 0.09,
    },
    "gcp": {
        "same_region": 0.00,
        "same_continent": 0.01,
        "cross_continent": 0.08,
        "internet": 0.12,
    },
    "azure": {
        "same_region": 0.00,
        "same_continent": 0.01,
        "cross_continent": 0.08,
        "internet": 0.087,
    },
    "runpod": {
        "same_region": 0.00,
        "same_continent": 0.00,
        "cross_continent": 0.00,
        "internet": 0.00,  # RunPod doesn't charge egress
    },
    "vastai": {
        "same_region": 0.00,
        "same_continent": 0.00,
        "cross_continent": 0.00,
        "internet": 0.00,
    },
    "lambda_labs": {
        "same_region": 0.00,
        "same_continent": 0.00,
        "cross_continent": 0.00,
        "internet": 0.00,
    },
    "coreweave": {
        "same_region": 0.00,
        "same_continent": 0.01,
        "cross_continent": 0.05,
        "internet": 0.05,
    },
    "tensordock": {
        "same_region": 0.00,
        "same_continent": 0.00,
        "cross_continent": 0.00,
        "internet": 0.00,
    },
    "oracle": {
        "same_region": 0.00,
        "same_continent": 0.0085,
        "cross_continent": 0.0085,
        "internet": 0.0085,  # Oracle is famously cheap
    },
}

# Region continent mapping (simplified)
REGION_CONTINENT: Dict[str, str] = {
    "us-east-1": "na", "us-east-2": "na", "us-west-1": "na", "us-west-2": "na",
    "us-central1": "na", "eastus": "na", "westus": "na", "westus2": "na",
    "us-ashburn-1": "na", "us-phoenix-1": "na",
    "eu-west-1": "eu", "eu-central-1": "eu", "europe-west1": "eu", "northeurope": "eu",
    "westeurope": "eu",
    "ap-southeast-1": "ap", "ap-northeast-1": "ap", "asia-east1": "ap",
    "southeastasia": "ap",
    # GPU cloud regions (generic)
    "us-east": "na", "us-west": "na", "eu-west": "eu", "ap-east": "ap",
}


def _continent(region: str) -> str:
    """Best-effort continent lookup."""
    r = region.lower().strip()
    if r in REGION_CONTINENT:
        return REGION_CONTINENT[r]
    if r.startswith("us") or r.startswith("na"):
        return "na"
    if r.startswith("eu") or r.startswith("north") or r.startswith("west"):
        return "eu"
    if r.startswith("ap") or r.startswith("asia") or r.startswith("south"):
        return "ap"
    return "unknown"


def _dest_class(src_provider: str, src_region: str, dst_provider: str, dst_region: str) -> str:
    """Classify the transfer destination for pricing lookup."""
    if src_provider == dst_provider and src_region == dst_region:
        return "same_region"
    if src_provider == dst_provider and _continent(src_region) == _continent(dst_region):
        return "same_continent"
    if _continent(src_region) == _continent(dst_region):
        return "same_continent"
    if src_provider != dst_provider:
        return "internet"
    return "cross_continent"


def estimate_egress_cost(
    src_provider: str,
    src_region: str,
    dst_provider: str,
    dst_region: str,
    size_gb: float,
) -> float:
    """Estimate egress cost in USD for a transfer."""
    rates = EGRESS_RATES.get(src_provider.lower(), EGRESS_RATES.get("aws"))
    dest = _dest_class(src_provider.lower(), src_region, dst_provider.lower(), dst_region)
    rate = rates.get(dest, rates.get("internet", 0.09))
    return round(rate * size_gb, 4)


def find_cheapest_route(
    src_provider: str,
    src_region: str,
    dst_candidates: List[Dict[str, str]],
    size_gb: float,
) -> List[Dict[str, Any]]:
    """
    Given a source and a list of destination candidates, rank them by egress cost.

    dst_candidates: [{"provider": "aws", "region": "us-east-1"}, ...]
    Returns sorted list with cost attached.
    """
    results = []
    for dst in dst_candidates:
        cost = estimate_egress_cost(
            src_provider, src_region, dst["provider"], dst["region"], size_gb
        )
        results.append({
            "provider": dst["provider"],
            "region": dst["region"],
            "egress_cost": cost,
            "size_gb": size_gb,
            "rate_per_gb": round(cost / max(size_gb, 0.001), 4),
        })
    results.sort(key=lambda x: x["egress_cost"])
    return results


def optimize_transfer_plan(
    data_location: Dict[str, str],
    compute_targets: List[Dict[str, str]],
    size_gb: float,
) -> Dict[str, Any]:
    """
    Build an optimized transfer plan.

    data_location: {"provider": "aws", "region": "us-east-1"}
    compute_targets: [{"provider": "runpod", "region": "us-east"}, ...]

    Returns a plan with per-target costs, total cost, and recommendations.
    """
    routes = find_cheapest_route(
        data_location["provider"],
        data_location["region"],
        compute_targets,
        size_gb,
    )

    total_cost = sum(r["egress_cost"] for r in routes)
    free_routes = [r for r in routes if r["egress_cost"] == 0]
    paid_routes = [r for r in routes if r["egress_cost"] > 0]

    recommendations = []
    if paid_routes:
        cheapest_free = free_routes[0] if free_routes else None
        for pr in paid_routes:
            if cheapest_free:
                recommendations.append(
                    f"Move compute from {pr['provider']}/{pr['region']} to "
                    f"{cheapest_free['provider']}/{cheapest_free['region']} to save "
                    f"${pr['egress_cost']:.2f}"
                )
            else:
                recommendations.append(
                    f"Stage data closer to {pr['provider']}/{pr['region']} to reduce "
                    f"${pr['egress_cost']:.2f} egress"
                )

    return {
        "routes": routes,
        "total_egress_cost": round(total_cost, 2),
        "free_routes": len(free_routes),
        "paid_routes": len(paid_routes),
        "recommendations": recommendations,
        "data_location": data_location,
        "size_gb": size_gb,
    }
