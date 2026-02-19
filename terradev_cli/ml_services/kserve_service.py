#!/usr/bin/env python3
"""
KServe Service Integration for Terradev
Manages KServe InferenceService deployments on Kubernetes
"""

import os
import json
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class KServeConfig:
    """KServe configuration"""
    kubernetes_config: Optional[str] = None  # Path to kubeconfig
    namespace: str = "default"
    auth_token: Optional[str] = None
    cluster_endpoint: Optional[str] = None


class KServeService:
    """KServe integration service for model deployment and management"""
    
    def __init__(self, config: KServeConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test KServe connection and get cluster info"""
        try:
            # Try to use kubectl command first
            import subprocess
            
            result = subprocess.run(
                ["kubectl", "cluster-info"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return {
                    "status": "connected",
                    "method": "kubectl",
                    "cluster_info": result.stdout,
                    "namespace": self.config.namespace
                }
            else:
                return {
                    "status": "failed",
                    "error": result.stderr
                }
        except FileNotFoundError:
            return {
                "status": "failed",
                "error": "kubectl not found. Please install kubectl."
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def list_inference_services(self) -> List[Dict[str, Any]]:
        """List all InferenceServices in the namespace"""
        try:
            import subprocess
            
            result = subprocess.run([
                "kubectl", "get", "inferenceservices",
                "-n", self.config.namespace,
                "-o", "json"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                services = []
                
                for item in data.get("items", []):
                    service = {
                        "name": item["metadata"]["name"],
                        "namespace": item["metadata"]["namespace"],
                        "created": item["metadata"]["creationTimestamp"],
                        "predictor": item.get("spec", {}).get("predictor", {}),
                        "status": item.get("status", {})
                    }
                    services.append(service)
                
                return services
            else:
                raise Exception(f"kubectl command failed: {result.stderr}")
                
        except Exception as e:
            raise Exception(f"Failed to list InferenceServices: {e}")
    
    async def create_inference_service(self, 
                                      name: str,
                                      model_uri: str,
                                      framework: str = "tensorflow",
                                      runtime_version: str = "latest",
                                      min_replicas: int = 1,
                                      max_replicas: int = 3) -> Dict[str, Any]:
        """Create a new InferenceService"""
        
        # Generate InferenceService YAML
        service_spec = {
            "apiVersion": "serving.kserve.io/v1beta1",
            "kind": "InferenceService",
            "metadata": {
                "name": name,
                "namespace": self.config.namespace
            },
            "spec": {
                "predictor": {
                    "framework": framework,
                    "runtimeVersion": runtime_version,
                    "model": {
                        "modelFormat": {
                            "name": framework
                        },
                        "storageUri": model_uri
                    },
                    "minReplicas": min_replicas,
                    "maxReplicas": max_replicas
                }
            }
        }
        
        try:
            # Write spec to temporary file and apply
            import tempfile
            import subprocess
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                json.dump(service_spec, f, indent=2)
                temp_file = f.name
            
            try:
                result = subprocess.run([
                    "kubectl", "apply", "-f", temp_file,
                    "-n", self.config.namespace
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    return {
                        "status": "created",
                        "name": name,
                        "namespace": self.config.namespace,
                        "output": result.stdout
                    }
                else:
                    raise Exception(f"Failed to create InferenceService: {result.stderr}")
            finally:
                os.unlink(temp_file)
                
        except Exception as e:
            raise Exception(f"Failed to create InferenceService {name}: {e}")
    
    async def delete_inference_service(self, name: str) -> Dict[str, Any]:
        """Delete an InferenceService"""
        try:
            import subprocess
            
            result = subprocess.run([
                "kubectl", "delete", "inferenceservice", name,
                "-n", self.config.namespace
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {
                    "status": "deleted",
                    "name": name,
                    "output": result.stdout
                }
            else:
                raise Exception(f"Failed to delete InferenceService: {result.stderr}")
                
        except Exception as e:
            raise Exception(f"Failed to delete InferenceService {name}: {e}")
    
    async def get_service_url(self, name: str) -> Optional[str]:
        """Get the prediction URL for an InferenceService"""
        try:
            import subprocess
            
            # Get the service URL
            result = subprocess.run([
                "kubectl", "get", "inferenceservice", name,
                "-n", self.config.namespace,
                "-o", "jsonpath='{.status.url}'"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                url = result.stdout.strip().strip("'\"")
                return url
            else:
                # Try to construct URL from service name
                cluster_info = subprocess.run([
                    "kubectl", "config", "view", "--minify", "-o", "jsonpath='{.clusters[0].cluster.server}'"
                ], capture_output=True, text=True, timeout=10)
                
                if cluster_info.returncode == 0:
                    base_url = cluster_info.stdout.strip().strip("'\"")
                    return f"{base_url}/serving/{self.config.namespace}/v1/models/{name}:predict"
                
            return None
            
        except Exception as e:
            raise Exception(f"Failed to get service URL for {name}: {e}")
    
    async def predict(self, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make a prediction request to the InferenceService"""
        try:
            url = await self.get_service_url(name)
            if not url:
                raise Exception(f"Could not get URL for service {name}")
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Make prediction request
            async with self.session.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Prediction failed: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to make prediction to {name}: {e}")


def create_kserve_service_from_credentials(credentials: Dict[str, str]) -> KServeService:
    """Create KServeService from credential dictionary"""
    config = KServeConfig(
        kubernetes_config=credentials.get("kubeconfig_path"),
        namespace=credentials.get("namespace", "default"),
        auth_token=credentials.get("auth_token"),
        cluster_endpoint=credentials.get("cluster_endpoint")
    )
    
    return KServeService(config)


def get_kserve_setup_instructions() -> str:
    """Get setup instructions for KServe"""
    return """
🚀 KServe Setup Instructions:

1. Install KServe on your Kubernetes cluster:
   kubectl apply -f https://github.com/kserve/kserve/releases/download/v0.11.0/kserve.yaml

2. Install kubectl if not already installed:
   # macOS
   brew install kubectl
   
   # Linux
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   
   # Windows (using Chocolatey)
   choco install kubernetes-cli

3. Configure kubectl to connect to your cluster:
   # For local clusters (minikube, kind, etc.)
   kubectl config use-context your-cluster-name
   
   # For cloud providers, use their CLI tools to configure access

4. Test the connection:
   kubectl cluster-info

5. Configure Terradev with your KServe credentials:
   terradev configure --provider kserve --kubeconfig-path ~/.kube/config --namespace default

📋 Required Credentials:
- kubeconfig_path: Path to Kubernetes config file (optional, uses default)
- namespace: Kubernetes namespace (default: "default")
- auth_token: Authentication token (optional, uses kubeconfig)
- cluster_endpoint: Cluster API endpoint (optional, uses kubeconfig)

💡 Usage Examples:
# List all InferenceServices
terradev kserve list

# Create a new InferenceService
terradev kserve create --name my-model --model-uri s3://my-bucket/model --framework tensorflow

# Make predictions
terradev kserve predict --name my-model --data '{"instances": [[1.0, 2.0, 3.0]]}'
"""
