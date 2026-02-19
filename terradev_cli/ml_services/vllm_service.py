#!/usr/bin/env python3
"""
vLLM Service Integration for Terradev
High-performance LLM inference server deployment and management
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
class VLLMConfig:
    """vLLM configuration"""
    model_name: str
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: Optional[str] = None
    gpu_memory_utilization: float = 0.9
    max_model_len: Optional[int] = None
    tensor_parallel_size: int = 1


class VLLMService:
    """vLLM integration service for LLM inference"""
    
    def __init__(self, config: VLLMConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = f"http://{config.host}:{config.port}/v1"
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test vLLM server connection"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Test server health
            url = f"http://{self.config.host}:{self.config.port}/health"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return {
                        "status": "connected",
                        "provider": "vllm",
                        "model": self.config.model_name,
                        "endpoint": self.base_url,
                        "host": self.config.host,
                        "port": self.config.port
                    }
                else:
                    return {
                        "status": "failed",
                        "error": f"vLLM server not responding: {response.status}"
                    }
                    
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to connect to vLLM server: {str(e)}"
            }
    
    async def install_vllm(self, instance_ip: str, ssh_user: str = "root", ssh_key: Optional[str] = None) -> Dict[str, Any]:
        """Install vLLM on remote instance"""
        try:
            install_script = f"""
#!/bin/bash
# Install vLLM with GPU support
pip install vllm

# Verify installation
python3 -c "import vllm; print('vLLM installed successfully')"
"""
            
            # Execute installation via SSH
            ssh_cmd = self._build_ssh_command(instance_ip, ssh_user, ssh_key, install_script)
            result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                return {
                    "status": "installed",
                    "instance_ip": instance_ip,
                    "provider": "vllm",
                    "output": result.stdout
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Installation failed: {result.stderr}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to install vLLM: {str(e)}"
            }
    
    def _build_ssh_command(self, ip: str, user: str, key: Optional[str], script: str) -> str:
        """Build SSH command for remote execution"""
        if key:
            ssh_cmd = f"ssh -i {key} {user}@{ip}"
        else:
            ssh_cmd = f"ssh {user}@{ip}"
        
        return f'{ssh_cmd} "{script}"'
    
    async def start_server(self, 
                          instance_ip: str,
                          ssh_user: str = "root",
                          ssh_key: Optional[str] = None,
                          additional_args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Start vLLM server on remote instance"""
        try:
            # Build vLLM server command
            server_cmd = [
                "vllm", "serve", self.config.model_name,
                "--host", self.config.host,
                "--port", str(self.config.port),
                "--gpu-memory-utilization", str(self.config.gpu_memory_utilization),
                "--tensor-parallel-size", str(self.config.tensor_parallel_size)
            ]
            
            if self.config.max_model_len:
                server_cmd.extend(["--max-model-len", str(self.config.max_model_len)])
            
            if self.config.api_key:
                server_cmd.extend(["--api-key", self.config.api_key])
            
            if additional_args:
                server_cmd.extend(additional_args)
            
            # Create systemd service
            service_content = f"""
[Unit]
Description=vLLM Server for {self.config.model_name}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart={" ".join(server_cmd)}
Restart=always
RestartSec=10
Environment=PYTHONPATH=/root

[Install]
WantedBy=multi-user.target
"""
            
            # Create and start service
            setup_script = f"""
#!/bin/bash
# Create vLLM service
echo '{service_content}' > /etc/systemd/system/vllm.service

# Reload systemd and start service
systemctl daemon-reload
systemctl enable vllm
systemctl start vllm

# Wait for service to start
sleep 10
systemctl status vllm
"""
            
            ssh_cmd = self._build_ssh_command(instance_ip, ssh_user, ssh_key, setup_script)
            result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                return {
                    "status": "started",
                    "instance_ip": instance_ip,
                    "provider": "vllm",
                    "model": self.config.model_name,
                    "endpoint": f"http://{instance_ip}:{self.config.port}/v1",
                    "output": result.stdout
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Failed to start server: {result.stderr}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to start vLLM server: {str(e)}"
            }
    
    async def test_inference(self, prompt: str, max_tokens: int = 100) -> Dict[str, Any]:
        """Test vLLM inference"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Prepare OpenAI-compatible request
            url = f"{self.base_url}/completions"
            payload = {
                "model": self.config.model_name,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "stream": False
            }
            
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            async with self.session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "status": "success",
                        "provider": "vllm",
                        "model": self.config.model_name,
                        "prompt": prompt,
                        "response": result["choices"][0]["text"],
                        "usage": result.get("usage", {}),
                        "endpoint": self.base_url
                    }
                else:
                    error_text = await response.text()
                    return {
                        "status": "failed",
                        "error": f"Inference failed: {response.status} - {error_text}"
                    }
                    
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to test inference: {str(e)}"
            }
    
    async def test_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 100) -> Dict[str, Any]:
        """Test vLLM chat completion"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Prepare OpenAI-compatible chat request
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.config.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "stream": False
            }
            
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            async with self.session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "status": "success",
                        "provider": "vllm",
                        "model": self.config.model_name,
                        "messages": messages,
                        "response": result["choices"][0]["message"]["content"],
                        "usage": result.get("usage", {}),
                        "endpoint": self.base_url
                    }
                else:
                    error_text = await response.text()
                    return {
                        "status": "failed",
                        "error": f"Chat completion failed: {response.status} - {error_text}"
                    }
                    
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to test chat completion: {str(e)}"
            }
    
    async def get_server_info(self) -> Dict[str, Any]:
        """Get vLLM server information"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Get model info
            url = f"{self.base_url}/models"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "status": "success",
                        "provider": "vllm",
                        "models": result.get("data", []),
                        "endpoint": self.base_url,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    error_text = await response.text()
                    return {
                        "status": "failed",
                        "error": f"Failed to get server info: {response.status} - {error_text}"
                    }
                    
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to get server info: {str(e)}"
            }
    
    async def stop_server(self, instance_ip: str, ssh_user: str = "root", ssh_key: Optional[str] = None) -> Dict[str, Any]:
        """Stop vLLM server on remote instance"""
        try:
            stop_script = """
#!/bin/bash
# Stop and disable vLLM service
systemctl stop vllm
systemctl disable vllm
rm -f /etc/systemd/system/vllm.service
systemctl daemon-reload
"""
            
            ssh_cmd = self._build_ssh_command(instance_ip, ssh_user, ssh_key, stop_script)
            result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {
                    "status": "stopped",
                    "instance_ip": instance_ip,
                    "provider": "vllm",
                    "output": result.stdout
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Failed to stop server: {result.stderr}"
                }
                
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to stop vLLM server: {str(e)}"
            }
    
    def get_supported_models(self) -> List[str]:
        """Get list of supported models"""
        return [
            "meta-llama/Llama-2-7b-hf",
            "meta-llama/Llama-2-13b-hf",
            "meta-llama/Llama-2-70b-hf",
            "mistralai/Mistral-7B-v0.1",
            "mistralai/Mixtral-8x7B-v0.1",
            "Qwen/Qwen-7B",
            "deepseek-ai/deepseek-coder-6.7b-base",
            "codellama/CodeLlama-7b-hf",
            "codellama/CodeLlama-13b-hf",
            "codellama/CodeLlama-34b-hf"
        ]
    
    def get_deployment_script(self, instance_ip: str, ssh_user: str = "root", ssh_key: Optional[str] = None) -> str:
        """Generate deployment script for vLLM"""
        script = f"""
#!/bin/bash
# vLLM Deployment Script for Terradev
# Target: {instance_ip}

echo "🚀 Deploying vLLM for {self.config.model_name}..."

# Install vLLM
pip install vllm

# Create systemd service
cat > /etc/systemd/system/vllm.service << 'EOF'
[Unit]
Description=vLLM Server for {self.config.model_name}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=vllm serve {self.config.model_name} \\
    --host {self.config.host} \\
    --port {self.config.port} \\
    --gpu-memory-utilization {self.config.gpu_memory_utilization} \\
    --tensor-parallel-size {self.config.tensor_parallel_size}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Start service
systemctl daemon-reload
systemctl enable vllm
systemctl start vllm

echo "✅ vLLM server started on http://{instance_ip}:{self.config.port}/v1"
echo "🔗 Test with: curl http://{instance_ip}:{self.config.port}/v1/models"
"""
        return script
