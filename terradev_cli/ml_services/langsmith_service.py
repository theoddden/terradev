#!/usr/bin/env python3
"""
LangSmith Service Integration for Terradev
Manages LangSmith tracing and evaluation workflows
"""

import os
import json
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LangSmithConfig:
    """LangSmith configuration"""
    api_key: str
    endpoint: str = "https://api.smith.langchain.com"
    workspace_id: Optional[str] = None
    project_name: Optional[str] = None


class LangSmithService:
    """LangSmith integration service for tracing and evaluation"""
    
    def __init__(self, config: LangSmithConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        self.session = aiohttp.ClientSession(headers=headers)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test LangSmith connection and get workspace info"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
            
            # Test API access
            url = f"{self.config.endpoint}/v1/sessions"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "status": "connected",
                        "workspace_id": self.config.workspace_id,
                        "endpoint": self.config.endpoint,
                        "sessions_count": len(data.get("sessions", []))
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
    
    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects in the workspace"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
            
            url = f"{self.config.endpoint}/v1/projects"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("projects", [])
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to list projects: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to list projects: {e}")
    
    async def create_project(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new LangSmith project"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
            
            url = f"{self.config.endpoint}/v1/projects"
            payload = {
                "name": name,
                "description": description
            }
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200 or response.status == 201:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to create project: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to create project {name}: {e}")
    
    async def list_runs(self, project_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List runs in a project or workspace"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
            
            params = {"limit": limit}
            if project_name:
                params["project_name"] = project_name
            elif self.config.project_name:
                params["project_name"] = self.config.project_name
            
            url = f"{self.config.endpoint}/v1/runs"
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("runs", [])
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to list runs: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to list runs: {e}")
    
    async def get_run_details(self, run_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific run"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
            
            url = f"{self.config.endpoint}/v1/runs/{run_id}"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get run details: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to get run details for {run_id}: {e}")
    
    async def create_dataset(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new dataset for evaluation"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
            
            url = f"{self.config.endpoint}/v1/datasets"
            payload = {
                "name": name,
                "description": description
            }
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200 or response.status == 201:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to create dataset: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to create dataset {name}: {e}")
    
    async def list_datasets(self) -> List[Dict[str, Any]]:
        """List all datasets in the workspace"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                )
            
            url = f"{self.config.endpoint}/v1/datasets"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("datasets", [])
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to list datasets: {response.status} - {error_text}")
                    
        except Exception as e:
            raise Exception(f"Failed to list datasets: {e}")
    
    def get_tracing_config(self) -> Dict[str, str]:
        """Get environment variables for LangSmith tracing"""
        config = {
            "LANGSMITH_API_KEY": self.config.api_key,
            "LANGSMITH_ENDPOINT": self.config.endpoint
        }
        
        if self.config.workspace_id:
            config["LANGSMITH_WORKSPACE_ID"] = self.config.workspace_id
            
        if self.config.project_name:
            config["LANGSMITH_PROJECT"] = self.config.project_name
            
        return config
    
    async def export_runs(self, project_name: Optional[str] = None, format: str = "json") -> str:
        """Export runs data"""
        try:
            runs = await self.list_runs(project_name, limit=1000)
            
            if format.lower() == "json":
                return json.dumps(runs, indent=2)
            elif format.lower() == "csv":
                import csv
                import io
                
                if not runs:
                    return ""
                
                output = io.StringIO()
                fieldnames = ["id", "name", "start_time", "end_time", "status", "error"]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                
                for run in runs:
                    writer.writerow({
                        "id": run.get("id", ""),
                        "name": run.get("name", ""),
                        "start_time": run.get("start_time", ""),
                        "end_time": run.get("end_time", ""),
                        "status": run.get("status", ""),
                        "error": run.get("error", "")
                    })
                
                return output.getvalue()
            else:
                raise ValueError(f"Unsupported format: {format}")
                
        except Exception as e:
            raise Exception(f"Failed to export runs: {e}")


def create_langsmith_service_from_credentials(credentials: Dict[str, str]) -> LangSmithService:
    """Create LangSmithService from credential dictionary"""
    config = LangSmithConfig(
        api_key=credentials["api_key"],
        endpoint=credentials.get("endpoint", "https://api.smith.langchain.com"),
        workspace_id=credentials.get("workspace_id"),
        project_name=credentials.get("project_name")
    )
    
    return LangSmithService(config)


def get_langsmith_setup_instructions() -> str:
    """Get setup instructions for LangSmith"""
    return """
🚀 LangSmith Setup Instructions:

1. Create a LangSmith account:
   - Go to https://smith.langchain.com
   - Sign up for a free account

2. Create an API key:
   - Navigate to Settings → API Keys
   - Click "Create API Key"
   - Choose scope (organization or workspace-scoped)
   - Set expiration (recommended: 90 days)
   - Copy the API key

3. Find your Workspace ID:
   - In LangSmith UI, go to Settings
   - Your Workspace ID is shown in the overview
   - Or use the API: curl -H "Authorization: Bearer YOUR_API_KEY" https://api.smith.langchain.com/v1/workspaces

4. Configure Terradev with your LangSmith credentials:
   terradev configure --provider langsmith --api-key YOUR_API_KEY --workspace-id YOUR_WORKSPACE_ID

📋 Required Credentials:
- api_key: LangSmith API key (required)
- endpoint: API endpoint (default: "https://api.smith.langchain.com")
- workspace_id: Workspace ID (optional but recommended)
- project_name: Default project name (optional)

💡 Usage Examples:
# Test connection
terradev langsmith test

# List projects
terradev langsmith list-projects

# Create a new project
terradev langsmith create-project --name my-project --description "My ML project"

# List recent runs
terradev langsmith list-runs --project my-project --limit 50

# Export runs data
terradev langsmith export --project my-project --format json > runs.json

# Get tracing environment variables
terradev langsmith tracing-config

🔗 Environment Variables for Tracing:
Add these to your ML training scripts:
export LANGSMITH_API_KEY="your-api-key"
export LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
export LANGSMITH_WORKSPACE_ID="your-workspace-id"
export LANGSMITH_PROJECT="your-project-name"

Then in your Python code:
from langchain.callbacks import LangSmithTracer
tracer = LangSmithTracer()
"""
