#!/usr/bin/env python3
"""
Enhanced Kubernetes Service with Deep Dashboard Integration
Integrates Karpenter, Prometheus, Grafana, and Terradev monitoring
"""

import os
import json
import asyncio
import aiohttp
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class KubernetesConfig:
    """Enhanced Kubernetes configuration"""
    kubeconfig_path: Optional[str] = None
    cluster_name: Optional[str] = None
    namespace: str = "default"
    karpenter_enabled: bool = False
    karpenter_version: str = "v0.32.0"
    aws_region: str = "us-east-1"
    aws_account_id: Optional[str] = None
    monitoring_enabled: bool = False
    prometheus_enabled: bool = False
    grafana_enabled: bool = False
    dashboard_port: int = 3000


class EnhancedKubernetesService:
    """Enhanced Kubernetes service with deep monitoring integration"""
    
    def __init__(self, config: KubernetesConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def install_monitoring_stack(self) -> Dict[str, Any]:
        """Install Prometheus and Grafana with Karpenter dashboards"""
        if not self.config.monitoring_enabled:
            return {
                "status": "failed",
                "error": "Monitoring not enabled in configuration"
            }
        
        try:
            env = os.environ.copy()
            if self.config.kubeconfig_path:
                env["KUBECONFIG"] = self.config.kubeconfig_path
            
            # Create monitoring namespace
            namespace_cmd = ["kubectl", "create", "namespace", "monitoring", "--dry-run=client", "-o", "yaml"]
            result = subprocess.run(namespace_cmd, capture_output=True, text=True, timeout=10, env=env)
            
            if result.returncode == 0:
                apply_result = subprocess.run(
                    ["kubectl", "apply", "-f", "-"],
                    input=result.stdout,
                    text=True,
                    timeout=10,
                    env=env
                )
            
            # Install Prometheus with Karpenter metrics
            prometheus_values = f"""
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'karpenter'
    kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
            - karpenter
            - monitoring
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_name__]
        target_label: __meta_kubernetes_pod_label_name__
    metric_relabel_configs:
      - source_label: __name__
        target_label: __name__
    static_configs:
      - targets: ['localhost:9090']

rule_files:
  - "/etc/prometheus/rules/*.yml"

alerting:
  alertmanagers:
    - static_configs:
      - "/etc/prometheus/alertmanager.yml"
"""
            
            # Write Prometheus values
            with open('/tmp/prometheus-karpenter.yaml', 'w') as f:
                f.write(prometheus_values)
            
            prometheus_cmd = [
                "helm", "install", "prometheus", "prometheus-community/prometheus",
                "--namespace", "monitoring",
                "--values", "/tmp/prometheus-karpenter.yaml",
                "--wait"
            ]
            
            result = subprocess.run(prometheus_cmd, capture_output=True, text=True, timeout=300, env=env)
            
            if result.returncode != 0:
                raise Exception(f"Prometheus installation failed: {result.stderr}")
            
            # Install Grafana with Karpenter dashboards
            grafana_values = f"""
adminPassword: prom-operator
adminUser: admin
service:
  type: LoadBalancer
  port: 80
targetPort: 3000

datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://prometheus.monitoring.svc.cluster.local:9090
        isDefault: true
        editable: true
        jsonData: |
          {{
            "uid": "prometheus",
            "type": "prometheus",
            "url": "http://prometheus.monitoring.svc.cluster.local:9090",
            "access": "proxy",
            "editable": true
          }}

dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
      - name: 'default'
        orgId: 1
        folder: ''
        type: 'file'
        disableDeletion: false
        allowUiUpdates: false
        options:
          path: /var/lib/grafana/dashboards
"""
            
            # Write Grafana values
            with open('/tmp/grafana-karpenter.yaml', 'w') as f:
                f.write(grafana_values)
            
            grafana_cmd = [
                "helm", "install", "grafana", "grafana-charts/grafana",
                "--namespace", "monitoring",
                "--values", "/tmp/grafana-karpenter.yaml",
                "--wait"
            ]
            
            result = subprocess.run(grafana_cmd, capture_output=True, text=True, timeout=300, env=env)
            
            if result.returncode != 0:
                raise Exception(f"Grafana installation failed: {result.stderr}")
            
            # Import Karpenter dashboards
            await self._import_karpenter_dashboards()
            
            return {
                "status": "installed",
                "prometheus": "http://prometheus.monitoring.svc.cluster.local:9090",
                "grafana": "http://grafana.monitoring.svc.cluster.local:80",
                "dashboards": "Karpenter dashboards imported"
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def _import_karpenter_dashboards(self) -> Dict[str, Any]:
        """Import Karpenter-specific dashboards into Grafana"""
        try:
            # Karpenter dashboard configuration
            dashboard_config = {
                "dashboard": {
                    "id": "karpenter-overview",
                    "title": "Karpenter Overview",
                    "tags": ["karpenter", "kubernetes", "autoscaling"],
                    "timezone": "browser",
                    "panels": [
                        {
                            "title": "Node Provisioning Rate",
                            "type": "stat",
                            "targets": [
                                {
                                    "expr": "rate(karpenter_created_nodes_total[5m])",
                                    "legendFormat": "{{instance}} nodes/min"
                                }
                            ],
                            "fieldConfig": {
                                "defaults": {
                                    "unit": "nodes/min",
                                    "min": 0
                                }
                            }
                        },
                        {
                            "title": "Node Deprovisioning Rate",
                            "type": "stat",
                            "targets": [
                                {
                                    "expr": "rate(karpenter_deleted_nodes_total[5m])",
                                    "legendFormat": "{{instance}} nodes/min"
                                }
                            ]
                        },
                        {
                            "title": "Active Nodes",
                            "type": "stat",
                            "targets": [
                                {
                                    "expr": "sum(kubernetes_node_info_condition{{condition=~\"Ready\"}})",
                                    "legendFormat": "{{instance}} nodes"
                                }
                            ]
                        },
                        {
                            "title": "Pending Pods",
                            "type": "stat",
                            "targets": [
                                {
                                    "expr": "sum(kubernetes_pod_status_phase{{phase=\"Pending\"}})",
                                    "legendFormat": "{{instance}} pods"
                                }
                            ]
                        },
                        {
                            "title": "GPU Nodes",
                            "type": "stat",
                            "targets": [
                                {
                                    "expr": "sum(kubernetes_node_info{{label_node_kubernetes_io_instance_type=~\"p5|p4|p3|g5|g4\"}})",
                                    "legendFormat": "{{instance}} GPU nodes"
                                }
                            ]
                        }
                    ],
                    "templating": {
                        "list": [
                            "all_variables",
                            [
                                "datasource",
                                "prometheus",
                                "karpenter"
                            ],
                            [
                                "dashboard",
                                "karpenter"
                            ]
                        ]
                    }
                }
            }
            
            # Import dashboard via Grafana API
            grafana_url = "http://admin:prom-operator@grafana.monitoring.svc.cluster.local:80/api"
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.post(f"{grafana_url}/api/dashboards/db", json=dashboard_config) as response:
                if response.status == 200:
                    return {
                        "status": "imported",
                        "dashboard_id": "karpenter-overview"
                    }
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to import dashboard: {response.status} - {error_text}")
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def get_monitoring_status(self) -> Dict[str, Any]:
        """Get comprehensive monitoring status"""
        try:
            env = os.environ.copy()
            if self.config.kubeconfig_path:
                env["KUBECONFIG"] = self.config.kubeconfig_path
            
            status = {
                "kubernetes": await self._get_cluster_status(),
                "monitoring": {
                    "prometheus": await self._check_prometheus_health(env),
                    "grafana": await self._check_grafana_health(env)
                },
                "karpenter": await self._get_karpenter_status(env)
            }
            
            return status
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def _get_cluster_status(self) -> Dict[str, Any]:
        """Get detailed cluster status"""
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=15,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                nodes_data = json.loads(result.stdout)
                
                status = {
                    "total_nodes": len(nodes_data.get("items", [])),
                    "ready_nodes": len([n for n in nodes_data.get("items", []) 
                                    if n.get("status", {}).get("conditions", [{}])[-1].get("type") == "Ready"]),
                    "gpu_nodes": len([n for n in nodes_data.get("items", [])
                                   if "nvidia.com/gpu" in n.get("status", {}).get("capacity", {})]),
                    "node_pools": self._get_node_pools_summary(nodes_data)
                }
                
                return status
            else:
                raise Exception(f"Failed to get cluster status: {result.stderr}")
                
        except Exception as e:
            raise Exception(f"Failed to get cluster status: {e}")
    
    def _get_node_pools_summary(self, nodes_data: Dict) -> Dict[str, Any]:
        """Get node pools summary"""
        pools = {}
        
        for node in nodes_data.get("items", []):
            labels = node.get("metadata", {}).get("labels", {})
            pool_name = labels.get("karpenter.sh/nodepool", "default")
            
            if pool_name not in pools:
                pools[pool_name] = {
                    "count": 0,
                    "instance_types": set(),
                    "gpu_count": 0
                }
            
            pools[pool_name]["count"] += 1
            
            instance_type = labels.get("node.kubernetes.io/instance-type", "unknown")
            pools[pool_name]["instance_types"].add(instance_type)
            
            gpu_capacity = node.get("status", {}).get("capacity", {}).get("nvidia.com/gpu", "0")
            if gpu_capacity and gpu_capacity != "0":
                pools[pool_name]["gpu_count"] += int(gpu_capacity)
        
        # Convert sets to lists for JSON serialization
        for pool_name in pools:
            pools[pool_name]["instance_types"] = list(pools[pool_name]["instance_types"])
        
        return pools
    
    async def _check_prometheus_health(self, env: Dict[str, str]) -> Dict[str, Any]:
        """Check Prometheus health"""
        try:
            result = subprocess.run(
                ["kubectl", "get", "pod", "-n", "monitoring", "-l", "app=prometheus"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'prometheus' in line and 'Running' in line:
                        return {"status": "healthy", "details": line.strip()}
            
            return {"status": "unhealthy", "error": "Prometheus not running"}
            
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def _check_grafana_health(self, env: Dict[str, str]) -> Dict[str, Any]:
        """Check Grafana health"""
        try:
            result = subprocess.run(
                ["kubectl", "get", "pod", "-n", "monitoring", "-l", "app=grafana"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'grafana' in line and 'Running' in line:
                        return {"status": "healthy", "details": line.strip()}
            
            return {"status": "unhealthy", "error": "Grafana not running"}
            
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def _get_karpenter_status(self, env: Dict[str, str]) -> Dict[str, Any]:
        """Check Karpenter status"""
        try:
            result = subprocess.run(
                ["kubectl", "get", "pod", "-n", "karpenter", "-l", "app=karpenter"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'karpenter' in line and 'Running' in line:
                        return {"status": "healthy", "details": line.strip()}
            
            return {"status": "unhealthy", "error": "Karpenter not running"}
            
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        try:
            if not self.config.monitoring_enabled:
                return {"status": "disabled", "error": "Monitoring not enabled"}
            
            env = os.environ.copy()
            if self.config.kubeconfig_path:
                env["KUBECONFIG"] = self.config.kubeconfig_path
            
            # Get cluster metrics
            cluster_status = await self._get_cluster_status()
            
            # Get resource usage
            resources = await self.get_cluster_resources()
            
            # Get Karpenter metrics if available
            karpenter_metrics = {}
            if self.config.karpenter_enabled:
                try:
                    # Try to get Karpenter metrics from Prometheus
                    prometheus_url = "http://prometheus.monitoring.svc.cluster.local:9090"
                    
                    if not self.session:
                        self.session = aiohttp.ClientSession()
                    
                    async with self.session.get(f"{prometheus_url}/api/v1/query?query=karpenter_created_nodes_total") as response:
                        if response.status == 200:
                            data = await response.json()
                            karpenter_metrics["created_nodes"] = data.get("data", {}).get("result", [{}])[0].get("value", [{}])[0].get("value", 0)
                except:
                    pass
            
            return {
                "cluster": cluster_status,
                "resources": resources,
                "karpenter": karpenter_metrics,
                "monitoring": {
                    "prometheus": await self._check_prometheus_health(env),
                    "grafana": await self._check_grafana_health(env),
                    "karpenter": await self._get_karpenter_status(env)
                }
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def get_cluster_resources(self) -> Dict[str, Any]:
        """Get cluster resource information"""
        try:
            env = os.environ.copy()
            if self.config.kubeconfig_path:
                env["KUBECONFIG"] = self.config.kubeconfig_path
            
            # Get nodes with resource info
            result = subprocess.run(
                ["kubectl", "top", "nodes", "--no-headers"],
                capture_output=True,
                text=True,
                timeout=15,
                env=env
            )
            
            resources = {
                "total_cpu": 0,
                "total_memory": 0,
                "total_gpu": 0,
                "nodes": []
            }
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            node_name = parts[0]
                            cpu_cores = parts[1].replace('m', '')
                            memory = parts[2].replace('Mi', '')
                            
                            try:
                                cpu_int = int(cpu_cores) / 1000 if cpu_cores.endswith('m') else int(cpu_cores)
                                mem_gb = int(memory) / 1024
                                
                                resources["nodes"].append({
                                    "name": node_name,
                                    "cpu_cores": cpu_int,
                                    "memory_gb": mem_gb
                                })
                                
                                resources["total_cpu"] += cpu_int
                                resources["total_memory"] += mem_gb
                            except ValueError:
                                continue
            
            # Get GPU resources
            gpu_result = subprocess.run(
                ["kubectl", "get", "nodes", "-o", "jsonpath='{range .items[*]}{{.metadata.name}}{{\" \"}}{{.status.capacity.nvidia.com/gpu}}{{\"\\n\"}}{end}'"],
                capture_output=True,
                text=True,
                timeout=15,
                env=env
            )
            
            if gpu_result.returncode == 0:
                for line in gpu_result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                gpu_count = int(parts[1])
                                resources["total_gpu"] += gpu_count
                            except ValueError:
                                continue
            
            return resources
            
        except Exception as e:
            raise Exception(f"Failed to get cluster resources: {e}")
    
    def get_enhanced_config(self) -> Dict[str, str]:
        """Get enhanced Kubernetes configuration for environment variables"""
        config = super().get_kubernetes_config()
        
        # Add monitoring configuration
        if self.config.monitoring_enabled:
            config["KARPENTER_MONITORING_ENABLED"] = "true"
        
        if self.config.prometheus_enabled:
            config["PROMETHEUS_ENABLED"] = "true"
            config["PROMETHEUS_URL"] = "http://prometheus.monitoring.svc.cluster.local:9090"
        
        if self.config.grafana_enabled:
            config["GRAFANA_ENABLED"] = "true"
            config["GRAFANA_URL"] = "http://grafana.monitoring.svc.cluster.local:80"
            config["GRAFANA_USERNAME"] = "admin"
            config["GRAFANA_PASSWORD"] = "prom-operator"
        
        return config


def create_enhanced_kubernetes_service_from_credentials(credentials: Dict[str, str]) -> EnhancedKubernetesService:
    """Create enhanced KubernetesService from credential dictionary"""
    config = KubernetesConfig(
        kubeconfig_path=credentials.get("kubeconfig_path"),
        cluster_name=credentials.get("cluster_name"),
        namespace=credentials.get("namespace", "default"),
        karpenter_enabled=credentials.get("karpenter_enabled", "false").lower() == "true",
        karpenter_version=credentials.get("karpenter_version", "v0.32.0"),
        aws_region=credentials.get("aws_region", "us-east-1"),
        aws_account_id=credentials.get("aws_account_id"),
        monitoring_enabled=credentials.get("monitoring_enabled", "false").lower() == "true",
        prometheus_enabled=credentials.get("prometheus_enabled", "false").lower() == "true",
        grafana_enabled=credentials.get("grafana_enabled", "false").lower() == "true",
        dashboard_port=int(credentials.get("dashboard_port", 3000))
    )
    
    return EnhancedKubernetesService(config)


def get_enhanced_kubernetes_setup_instructions() -> str:
    """Get enhanced setup instructions for Kubernetes with monitoring"""
    return """
🚀 Enhanced Kubernetes Setup Instructions:

1. Install kubectl and Helm:
   # macOS
   brew install kubectl helm
   
   # Linux
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
   curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
   
   # Windows
   choco install kubernetes-cli kubernetes-helm

2. Configure cluster access:
   # For EKS
   aws eks update-kubeconfig --region us-east-1 --name your-cluster-name
   
   # For other clusters, use your provider's CLI tools

3. Configure Terradev with enhanced Kubernetes:
   terradev configure --provider kubernetes \\
     --cluster-name my-cluster \\
     --kubeconfig-path ~/.kube/config \\
     --karpenter-enabled true \\
     --monitoring-enabled true \\
     --prometheus-enabled true \\
     --grafana-enabled true

4. Install monitoring stack:
   terradev ml kubernetes --install-monitoring

5. Access dashboards:
   # Grafana Dashboard
   kubectl port-forward --namespace monitoring svc/grafana 3000:80
   
   # Prometheus UI
   kubectl port-forward --namespace monitoring svc/prometheus 9090:9090

6. Get comprehensive status:
   terradev ml kubernetes --metrics-summary

📋 Enhanced Credentials:
- kubeconfig_path: Path to Kubernetes config file (optional, uses default)
- cluster_name: Kubernetes cluster name (optional)
- namespace: Kubernetes namespace (default: "default")
- karpenter_enabled: Enable Karpenter (default: "false")
- karpenter_version: Karpenter version (default: "v0.32.0")
- aws_region: AWS region (default: "us-east-1")
- aws_account_id: AWS account ID (optional)
- monitoring_enabled: Enable monitoring stack (default: "false")
- prometheus_enabled: Enable Prometheus (default: "false")
- grafana_enabled: Enable Grafana (default: "false")
- dashboard_port: Grafana port (default: 3000)

💡 Enhanced Usage Examples:
# Test connection
terradev ml kubernetes --test

# Install complete monitoring stack
terradev ml kubernetes --install-monitoring

# Get comprehensive status
terradev ml kubernetes --metrics-summary

# List GPU nodes with monitoring
terradev ml kubernetes --gpu-nodes

# Get cluster resources
terradev ml kubernetes --resources

# Access Grafana dashboard
terradev ml kubernetes --dashboard

🔗 Monitoring Integration:
- **Prometheus**: Metrics collection from Karpenter and Kubernetes
- **Grafana**: Pre-configured Karpenter dashboards
- **Karpenter Metrics**: Node provisioning/deprovisioning rates
- **Cluster Metrics**: CPU, memory, GPU utilization
- **Dashboard Templates**: Ready-to-use Karpenter dashboards

🎯 Dashboard Features:
- **Node Provisioning Rate**: Real-time node creation metrics
- **Node Deprovisioning Rate**: Automatic cleanup metrics
- **Active/Pending Pods**: Pod status monitoring
- **GPU Node Tracking**: GPU-specific node monitoring
- **Resource Utilization**: CPU, memory, GPU usage trends
- **Cluster Health**: Comprehensive cluster status

🔧 Integration with Terradev:
- **Provisioning Integration**: Terradev GPU provisioning + Karpenter auto-scaling
- **Cost Tracking**: Monitor infrastructure costs via dashboards
- **Performance Metrics**: Track ML workload performance
- **Resource Optimization**: Optimize based on monitoring data

📊 Dashboard URLs:
- Grafana: http://localhost:3000 (admin/prom-operator)
- Prometheus: http://localhost:9090
- Karpenter: Integrated in Grafana dashboards

🎯 Advanced Features:
- **Alerting**: Configure alerts for node failures
- **Auto-scaling**: Karpenter + Kubernetes HPA integration
- **Multi-cloud**: Support for AWS, GCP, Azure providers
- **Security**: RBAC and network policies
- **Persistence**: Long-term metrics storage
"""
