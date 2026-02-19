#!/usr/bin/env python3
"""
MLflow Service Integration for Terradev
Manages MLflow experiments, runs, and model registry
"""

import os
import json
import asyncio
import aiohttp
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MLflowConfig:
    """MLflow configuration"""
    tracking_uri: str
    username: Optional[str] = None
    password: Optional[str] = None
    experiment_name: Optional[str] = None
    registry_uri: Optional[str] = None


class MLflowService:
    """MLflow integration service for experiment tracking and model registry"""
    
    def __init__(self, config: MLflowConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        if self.config.username and self.config.password:
            auth = aiohttp.BasicAuth(self.config.username, self.config.password)
            self.session = aiohttp.ClientSession(auth=auth)
        else:
            self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test MLflow connection and get server info"""
        try:
            if not self.session:
                if self.config.username and self.config.password:
                    auth = aiohttp.BasicAuth(self.config.username, self.config.password)
                    self.session = aiohttp.ClientSession(auth=auth)
                else:
                    self.session = aiohttp.ClientSession()
            
            # Test API access
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/experiments/list"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "status": "connected",
                        "tracking_uri": self.config.tracking_uri,
                        "experiments_count": len(data.get("experiments", [])),
                        "registry_uri": self.config.registry_uri
                    }
                else:
                    error_text = await response.text()
                    return {
                        "status": "failed",
                        "error": f"API request failed: {response.status} - {error_text}"
                    }
                    
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def list_experiments(self) -> List[Dict[str, Any]]:
        """List all experiments"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/experiments/list"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("experiments", [])
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to list experiments: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to list experiments: {e}")
    
    async def create_experiment(self, name: str, artifact_location: Optional[str] = None) -> Dict[str, Any]:
        """Create a new experiment"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/experiments/create"
            payload = {"name": name}
            if artifact_location:
                payload["artifact_location"] = artifact_location
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to create experiment: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to create experiment {name}: {e}")
    
    async def get_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """Get experiment details"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/experiments/get"
            payload = {"experiment_id": experiment_id}
            
            async with self.session.get(url, params=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get experiment: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to get experiment {experiment_id}: {e}")
    
    async def list_runs(self, experiment_ids: Optional[List[str]] = None, max_results: int = 1000) -> List[Dict[str, Any]]:
        """List runs in experiments"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/runs/search"
            payload = {"max_results": max_results}
            
            if experiment_ids:
                eid_list = ', '.join(f'"{eid}"' for eid in experiment_ids)
                payload["filter"] = f"experiment_id IN ({eid_list})"
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("runs", [])
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to list runs: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to list runs: {e}")
    
    async def get_run(self, run_id: str) -> Dict[str, Any]:
        """Get run details"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/runs/get"
            payload = {"run_id": run_id}
            
            async with self.session.get(url, params=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get run: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to get run {run_id}: {e}")
    
    async def log_run(self, run_id: str, metrics: Dict[str, float], params: Dict[str, Any], tags: Dict[str, str]) -> Dict[str, Any]:
        """Log metrics, parameters, and tags to a run"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Log metrics
            if metrics:
                url = f"{self.config.tracking_uri}/api/2.0/mlflow/runs/log-metrics"
                metrics_payload = {
                    "run_id": run_id,
                    "metrics": [{"key": k, "value": v, "timestamp": int(datetime.now().timestamp() * 1000)} for k, v in metrics.items()]
                }
                
                async with self.session.post(url, json=metrics_payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Failed to log metrics: {response.status} - {error_text}")
            
            # Log parameters
            if params:
                url = f"{self.config.tracking_uri}/api/2.0/mlflow/runs/log-parameters"
                params_payload = {
                    "run_id": run_id,
                    "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]
                }
                
                async with self.session.post(url, json=params_payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Failed to log parameters: {response.status} - {error_text}")
            
            # Log tags
            if tags:
                url = f"{self.config.tracking_uri}/api/2.0/mlflow/runs/set-tags"
                tags_payload = {
                    "run_id": run_id,
                    "tags": tags
                }
                
                async with self.session.post(url, json=tags_payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Failed to log tags: {response.status} - {error_text}")
            
            return {"status": "logged", "run_id": run_id}
            
        except Exception as e:
            raise Exception(f"Failed to log to run {run_id}: {e}")
    
    async def list_registered_models(self) -> List[Dict[str, Any]]:
        """List registered models"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/registered-models/list"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("registered_models", [])
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to list registered models: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to list registered models: {e}")
    
    async def create_model_version(self, name: str, source: str, run_id: Optional[str] = None, description: str = "") -> Dict[str, Any]:
        """Create a new model version"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.config.tracking_uri}/api/2.0/mlflow/model-versions/create"
            payload = {
                "name": name,
                "source": source,
                "run_id": run_id,
                "description": description
            }
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to create model version: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to create model version {name}: {e}")
    
    def get_tracking_config(self) -> Dict[str, str]:
        """Get environment variables for MLflow tracking"""
        config = {
            "MLFLOW_TRACKING_URI": self.config.tracking_uri
        }
        
        if self.config.username:
            config["MLFLOW_TRACKING_USERNAME"] = self.config.username
            
        if self.config.password:
            config["MLFLOW_TRACKING_PASSWORD"] = self.config.password
            
        if self.config.registry_uri:
            config["MLFLOW_REGISTRY_URI"] = self.config.registry_uri
            
        return config
    
    async def export_experiment_data(self, experiment_id: str, format: str = "json") -> str:
        """Export experiment data"""
        try:
            runs = await self.list_runs([experiment_id])
            
            if format.lower() == "json":
                return json.dumps(runs, indent=2)
            elif format.lower() == "csv":
                import csv
                import io
                
                if not runs:
                    return ""
                
                output = io.StringIO()
                fieldnames = ["run_id", "experiment_id", "status", "start_time", "end_time", "artifact_uri"]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                
                for run in runs:
                    info = run.get("info", {})
                    writer.writerow({
                        "run_id": info.get("run_id", ""),
                        "experiment_id": info.get("experiment_id", ""),
                        "status": info.get("status", ""),
                        "start_time": info.get("start_time", ""),
                        "end_time": info.get("end_time", ""),
                        "artifact_uri": info.get("artifact_uri", "")
                    })
                
                return output.getvalue()
            else:
                raise ValueError(f"Unsupported format: {format}")
                
        except Exception as e:
            raise Exception(f"Failed to export experiment data: {e}")


def create_mlflow_service_from_credentials(credentials: Dict[str, str]) -> MLflowService:
    """Create MLflowService from credential dictionary"""
    config = MLflowConfig(
        tracking_uri=credentials["tracking_uri"],
        username=credentials.get("username"),
        password=credentials.get("password"),
        experiment_name=credentials.get("experiment_name"),
        registry_uri=credentials.get("registry_uri")
    )
    
    return MLflowService(config)


def get_mlflow_setup_instructions() -> str:
    """Get setup instructions for MLflow"""
    return """
🚀 MLflow Setup Instructions:

1. Install MLflow:
   pip install mlflow

2. Start MLflow tracking server:
   # Basic server
   mlflow server
   
   # With authentication
   mlflow server --app-name basic-auth
   
   # With custom host and port
   mlflow server --host 0.0.0.0 --port 5000

3. Set up authentication (optional but recommended):
   export MLFLOW_FLASK_SECRET_KEY="your-secret-key"
   export MLFLOW_TRACKING_USERNAME="admin"
   export MLFLOW_TRACKING_PASSWORD="your-password"

4. Configure Terradev with your MLflow credentials:
   terradev configure --provider mlflow --tracking-uri http://localhost:5000 --username admin --password your-password

📋 Required Credentials:
- tracking_uri: MLflow tracking server URI (required)
- username: Username for basic auth (optional)
- password: Password for basic auth (optional)
- experiment_name: Default experiment name (optional)
- registry_uri: Model registry URI (optional)

💡 Usage Examples:
# Test connection
terradev mlflow test

# List experiments
terradev mlflow list-experiments

# Create a new experiment
terradev mlflow create-experiment --name my-experiment

# List runs in an experiment
terradev mlflow list-runs --experiment-id your-experiment-id

# Log metrics to a run
terradev mlflow log-run --run-id your-run-id --metrics '{"accuracy": 0.95, "loss": 0.05}'

# List registered models
terradev mlflow list-models

# Create a model version
terradev mlflow create-model --name my-model --source s3://my-bucket/model

# Export experiment data
terradev mlflow export --experiment-id your-experiment-id --format json > experiment.json

🔗 Environment Variables for Tracking:
Add these to your ML training scripts:
export MLFLOW_TRACKING_URI="http://localhost:5000"
export MLFLOW_TRACKING_USERNAME="admin"
export MLFLOW_TRACKING_PASSWORD="your-password"

Then in your Python code:
import mlflow
with mlflow.start_run():
    mlflow.log_param("learning_rate", 0.01)
    mlflow.log_metric("accuracy", 0.95)

🐳 Docker MLflow Server:
docker run -p 5000:5000 --rm -e MLFLOW_FLASK_SECRET_KEY=your-key python:3.9-slim bash -c "
pip install mlflow && mlflow server --host 0.0.0.0
"

☸️ Kubernetes MLflow:
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlflow-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mlflow-server
  template:
    metadata:
      labels:
        app: mlflow-server
    spec:
      containers:
      - name: mlflow-server
        image: python:3.9-slim
        ports:
        - containerPort: 5000
        env:
        - name: MLFLOW_FLASK_SECRET_KEY
          value: "your-secret-key"
        command:
        - bash
        - -c
        - |
          pip install mlflow &&
          mlflow server --host 0.0.0.0 --port 5000
"""
