#!/usr/bin/env python3
"""
Provider Factory - Creates and manages cloud provider instances
"""

import logging
from typing import Dict, Any
from .aws_provider import AWSProvider

logger = logging.getLogger(__name__)
from .gcp_provider import GCPProvider
from .azure_provider import AzureProvider
from .runpod_provider import RunPodProvider
from .vastai_provider import VastAIProvider
from .lambda_labs_provider import LambdaLabsProvider
from .coreweave_provider import CoreWeaveProvider
from .tensordock_provider import TensorDockProvider
from .huggingface_provider import HuggingFaceProvider
from .baseten_provider import BasetenProvider
from .oracle_provider import OracleProvider
from .crusoe_provider import CrusoeProvider
from .digitalocean_provider import DigitalOceanProvider
from .hyperstack_provider import HyperstackProvider
from .demo_mode import DemoModeProvider
from .base_provider import BaseProvider


class ProviderFactory:
    """Factory for creating cloud provider instances"""

    def __init__(self):
        self._provider_classes = {
            "aws": AWSProvider,
            "gcp": GCPProvider,
            "azure": AzureProvider,
            "runpod": RunPodProvider,
            "vastai": VastAIProvider,
            "lambda": LambdaLabsProvider,
            "coreweave": CoreWeaveProvider,
            "tensordock": TensorDockProvider,
            "huggingface": HuggingFaceProvider,
            "baseten": BasetenProvider,
            "oracle": OracleProvider,
            "crusoe": CrusoeProvider,
            "hyperstack": HyperstackProvider,
            "digitalocean": DigitalOceanProvider,
            "demo": DemoModeProvider
        }

    def create_provider(
        self, provider_name: str, credentials: Dict[str, str]
    ) -> BaseProvider:
        """Create a provider instance"""
        if provider_name not in self._provider_classes:
            raise ValueError(f"Unknown provider: {provider_name}")

        provider_class = self._provider_classes[provider_name]
        return provider_class(credentials)

    def get_supported_providers(self) -> list:
        """Get list of supported providers"""
        return list(self._provider_classes.keys())

    def register_provider(self, provider_name: str, provider_class: type) -> None:
        """Register a new provider class"""
        if not issubclass(provider_class, BaseProvider):
            raise ValueError("Provider class must inherit from BaseProvider")

        self._provider_classes[provider_name] = provider_class

    def create_all_providers(
        self, credentials: Dict[str, Dict[str, str]]
    ) -> Dict[str, BaseProvider]:
        """Create all configured providers"""
        providers = {}

        for provider_name, provider_credentials in credentials.items():
            try:
                provider = self.create_provider(provider_name, provider_credentials)
                providers[provider_name] = provider
            except Exception as e:
                logger.debug(f"Failed to create provider {provider_name}: {e}")

        return providers
