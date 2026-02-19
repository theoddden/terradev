#!/usr/bin/env python3
"""
Stripe Integration Manager for Terradev
Handles dynamic checkout session creation and webhook processing
"""

import os
import json
import stripe
from typing import Dict, Optional, Any
from datetime import datetime
import logging

class StripeManager:
    """Manages Stripe integration for Terradev CLI"""
    
    def __init__(self):
        # Your Stripe keys
        self.publishable_key = "pk_live_51Sz5pwKDFO7eDloBQakbf5HBrurcPPiiiNrk4RREPRT64cBipJC8nmpaXh3sZzUv6redIbaAHh7f4nDEGb4ehQ2m00kvIdxiFP"
        self.secret_key = os.getenv('STRIPE_SECRET_KEY')  # Set this in environment
        
        if not self.secret_key:
            logging.warning("STRIPE_SECRET_KEY not set - using demo mode")
            self.demo_mode = True
        else:
            stripe.api_key = self.secret_key
            self.demo_mode = False
    
    def create_checkout_session(self, tier: str, customer_email: str, success_url: str, cancel_url: str) -> Dict[str, Any]:
        """Create a dynamic Stripe checkout session"""
        
        if self.demo_mode:
            # Demo mode - return mock session
            return {
                'session_id': f'cs_demo_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                'checkout_url': f'https://checkout.stripe.com/demo/{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                'publishable_key': self.publishable_key
            }
        
        # Product configuration
        products = {
            'research_plus': {
                'name': 'Terradev Research+',
                'description': '30 provisions/month, 4 servers, inference support',
                'price': 4999,  # $49.99 in cents
                'currency': 'usd'
            },
            'enterprise': {
                'name': 'Terradev Enterprise',
                'description': 'Unlimited provisions, 32 servers, priority support',
                'price': 29999,  # $299.99 in cents
                'currency': 'usd'
            }
        }
        
        if tier not in products:
            raise ValueError(f"Unknown tier: {tier}")
        
        product_config = products[tier]
        
        try:
            # Create or get product
            product = self._get_or_create_product(tier, product_config)
            
            # Create or get price
            price = self._get_or_create_price(product.id, product_config)
            
            # Create checkout session
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price': price.id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=customer_email,
                metadata={
                    'tier': tier,
                    'product': 'terradev_cli',
                    'version': '1.8.3'
                },
                subscription_data={
                    'metadata': {
                        'tier': tier,
                        'product': 'terradev_cli'
                    }
                }
            )
            
            return {
                'session_id': session.id,
                'checkout_url': session.url,
                'publishable_key': self.publishable_key
            }
            
        except Exception as e:
            logging.error(f"Failed to create Stripe session: {e}")
            raise
    
    def _get_or_create_product(self, tier: str, config: Dict[str, Any]) -> stripe.Product:
        """Get existing product or create new one"""
        
        try:
            # Search for existing product
            products = stripe.Product.list(limit=100, active=True)
            for product in products.data:
                if product.metadata.get('tier') == tier and product.metadata.get('product') == 'terradev_cli':
                    return product
            
            # Create new product
            return stripe.Product.create(
                name=config['name'],
                description=config['description'],
                metadata={
                    'tier': tier,
                    'product': 'terradev_cli',
                    'version': '1.8.3'
                }
            )
            
        except Exception as e:
            logging.error(f"Failed to get/create product: {e}")
            raise
    
    def _get_or_create_price(self, product_id: str, config: Dict[str, Any]) -> stripe.Price:
        """Get existing price or create new one"""
        
        try:
            # Search for existing price
            prices = stripe.Price.list(product=product_id, limit=100, active=True)
            for price in prices.data:
                if price.unit_amount == config['price'] and price.currency == config['currency']:
                    return price
            
            # Create new price
            return stripe.Price.create(
                product=product_id,
                unit_amount=config['price'],
                currency=config['currency'],
                recurring={'interval': 'month'},
                metadata={
                    'tier': config.get('tier', 'unknown'),
                    'product': 'terradev_cli'
                }
            )
            
        except Exception as e:
            logging.error(f"Failed to get/create price: {e}")
            raise
    
    def construct_webhook_event(self, payload: str, sig_header: str, webhook_secret: str) -> stripe.Event:
        """Construct webhook event for verification"""
        
        if self.demo_mode:
            # Demo mode - return mock event
            return {
                'type': 'checkout.session.completed',
                'data': {
                    'object': {
                        'id': f'cs_demo_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                        'customer': 'cus_demo_123',
                        'metadata': {'tier': 'research_plus'},
                        'subscription': 'sub_demo_123'
                    }
                }
            }
        
        try:
            return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except Exception as e:
            logging.error(f"Webhook signature verification failed: {e}")
            raise
    
    def get_customer_info(self, customer_id: str) -> Dict[str, Any]:
        """Get customer information from Stripe"""
        
        if self.demo_mode:
            return {
                'id': customer_id,
                'email': 'demo@example.com',
                'metadata': {'tier': 'research_plus'}
            }
        
        try:
            customer = stripe.Customer.retrieve(customer_id)
            return {
                'id': customer.id,
                'email': customer.email,
                'metadata': customer.metadata
            }
        except Exception as e:
            logging.error(f"Failed to get customer info: {e}")
            raise
    
    def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a subscription"""
        
        if self.demo_mode:
            return True
        
        try:
            stripe.Subscription.delete(subscription_id)
            return True
        except Exception as e:
            logging.error(f"Failed to cancel subscription: {e}")
            return False

# Global instance
stripe_manager = StripeManager()
