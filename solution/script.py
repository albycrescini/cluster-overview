#!/usr/bin/env python3

import requests
import subprocess, threading
from kubernetes import client, config
import socket
import time
import re
from tabulate import tabulate
from kubernetes import client, config
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description='Thought Machine CSRE Home Assessment - Alberto Crescini')
    parser.add_argument('cluster', help='Name of the Kubernetes cluster')
    parser.add_argument('namespace', help='Namespace to inspect')
    parser.add_argument('--ingress-namespace', default='ingress-nginx',
                      help='Namespace where ingress controller is installed')
    parser.add_argument('--time-range', default='1h',
                      help='Time range for Prometheus queries (e.g., 5m, 1h)')
    return parser.parse_args()

class Utils():
    def __init__(self):
        pass

    def find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def start_port_forward(self, svc_name="ingress-nginx-controller", local_port=None, container_port=80, namespace="ingress-nginx"):
        if not local_port:
            local_port = self.find_free_port()

        def port_forward():
            cmd = [
                "kubectl", "port-forward",
                "-n", namespace,
                f"svc/{svc_name}",
                f"{local_port}:{container_port}"
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        thread = threading.Thread(target=port_forward, daemon=True)
        thread.start()

        for _ in range(20):
            try:
                with socket.create_connection(("localhost", local_port), timeout=1):
                    return local_port
            except (ConnectionRefusedError, OSError):
                time.sleep(0.5)

        raise TimeoutError(f"Port-forward to svc/{svc_name} on port {local_port} did not succeed.")

    def is_this_up(self, reverse_proxy_url):
        try:
            resp = requests.get(reverse_proxy_url, timeout=20)
            return resp.ok
        except requests.RequestException:
            return False

    def get_guestbook_pods(self, namespace="default", label_selector="app=guestbook"):
        config.load_kube_config()
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        return [pod.metadata.name for pod in pods.items]

class PrometheusInspector:
    def __init__(self, base_url="http://prometheus.default.svc.cluster.local:9090"):
        self.base_url = base_url.rstrip('/')

    def query(self, promql):
        response = requests.get(f"{self.base_url}/api/v1/query", params={"query": promql})
        if response.status_code != 200:
            raise RuntimeError(f"Prometheus query failed: {response.text}")
        data = response.json()
        return data["data"]["result"]

    def check_metric_available(self, metric_name):
        results = self.query(metric_name)
        return len(results) > 0

class IngressInspector:
    def __init__(self, prometheus: PrometheusInspector, time_range: str = "5m"):
        self.prometheus = prometheus
        self.time_range = time_range
        self.percentiles = {
            "p25": 0.25,
            "p50": 0.50,
            "p75": 0.75,
            "p95": 0.95,
            "p99": 0.99,
        }

    def get_latency_percentiles(self):
        results = []
        for label, quantile in self.percentiles.items():
            promql = (
                f"histogram_quantile({quantile}, "
                f"sum(rate(nginx_ingress_controller_request_duration_seconds_bucket[{self.time_range}])) by (le))"
            )
            try:
                data = self.prometheus.query(promql)
                value = float(data[0]["value"][1]) if data else None
                latency = f"{value * 1000:.2f} ms" if value is not None else "N/A"
            except Exception as e:
                latency = f"error: {str(e)}"
            results.append((label, latency))
        return results

    def get_success_rate(self, status_code_range="2.."):
        query = f"""
        sum(rate(nginx_ingress_controller_requests{{status=~"{status_code_range}"}}[{self.time_range}]))
        /
        sum(rate(nginx_ingress_controller_requests[{self.time_range}]))
        """
        try:
            result = self.prometheus.query(query.strip())
            if result:
                success_rate = float(result[0]["value"][1]) * 100
                return f"{success_rate:.2f}%"
            else:
                return "N/A"
        except Exception as e:
            return f"error: {str(e)}"

    def print_ingress_metrics(self):
        latency_table = self.get_latency_percentiles()
        print(f"\n{Colors.BOLD}{Colors.UNDERLINE}{Colors.BLUE}NGINX Ingress Controller{Colors.END}\n\n{Colors.BOLD}{Colors.BLUE}Latency (ms){Colors.END}\n")
        print(tabulate(latency_table, headers=["Percentile", "Latency"], tablefmt="github"))

        non_5xx_success_rate = self.get_success_rate("^[1-4].*") # non 500
        two_xx_success_rate = self.get_success_rate("2..") # 2xx family

        print(f"\n{Colors.BOLD}{Colors.BLUE}Success Rates{Colors.END}\n")
        print(f"{Colors.BOLD}HTTP Code IS NOT 5xx: {non_5xx_success_rate}{Colors.END}")
        print(f"{Colors.BOLD}HTTP Code IS 2xx: {two_xx_success_rate}{Colors.END}")

class GuestbookDistributionInspector:
    def __init__(self, prometheus: PrometheusInspector, namespace: str, pod_list: list[str]):
        self.prometheus = prometheus
        self.namespace = namespace
        self.pod_list = pod_list

    def build_promql(self):
        escaped_pods = [re.escape(p).replace("\\", r"\\") for p in self.pod_list]
        pod_regex = "|".join(escaped_pods)
        return f'kube_pod_info{{pod=~"{pod_regex}", namespace="{self.namespace}"}}'

    def get_distribution(self):
        promql = self.build_promql()
        results = self.prometheus.query(promql)

        distribution = {}
        for entry in results:
            labels = entry.get("metric", {})
            node = labels.get("node", "unknown")
            zone = labels.get("topology_kubernetes_io_zone", "unknown")
            pod = labels.get("pod", "unknown")
            key = (node, zone, pod)
            distribution[key] = distribution.get(key, 0) + 1

        return distribution

    def print_distribution_table(self):
        print(f"\n{Colors.BOLD}{Colors.UNDERLINE}{Colors.BLUE}Guestbook Pods AZ Distribution{Colors.END}\n")
        dist = self.get_distribution()
        table = [(node, zone, pod, count) for (node, zone, pod), count in sorted(dist.items())]
        print(tabulate(table, headers=["Node", "Zone", "Pod", "Pod Count"], tablefmt="github"))

class WhereamiInspector:
    def __init__(self, prometheus: PrometheusInspector, namespace: str = "default", svc_name: str = "whereami", time_range: str = "5m"):
        self.prometheus = prometheus
        self.namespace = namespace
        self.svc_name = svc_name
        self.time_range = time_range

    def get_success_rate(self, status_code_range="2.."):
        query = f"""
        sum(rate(flask_http_request_total{{app="{self.svc_name}", kubernetes_namespace="{self.namespace}", status=~"{status_code_range}"}}[{self.time_range}]))
        /
        sum(rate(flask_http_request_total{{app="{self.svc_name}", kubernetes_namespace="{self.namespace}"}}[{self.time_range}]))
        """

        try:
            result = self.prometheus.query(query.strip())
            if result:
                success_rate = float(result[0]["value"][1]) * 100
                return f"{success_rate:.2f}%"
            else:
                return "N/A"
        except Exception as e:
            return f"error: {str(e)}"

    def print_success_rate(self):
        non_5xx_success_rate = self.get_success_rate("^[1-4].*") # non 500
        two_xx_success_rate = self.get_success_rate("2..") # 2xx family
        print(f"\n{Colors.BOLD}{Colors.UNDERLINE}{Colors.BLUE}WhereAmI Ingress{Colors.END}{Colors.BOLD}{Colors.BLUE} - Success Rates{Colors.END}\n")
        print(f"{Colors.BOLD}HTTP Code IS NOT 5xx: {non_5xx_success_rate}{Colors.END}")
        print(f"{Colors.BOLD}HTTP Code IS 2xx: {two_xx_success_rate}{Colors.END}")

class RedisInspector:
    def __init__(self, prometheus: PrometheusInspector, time_range: str = "5m"):
        self.prometheus = prometheus
        self.time_range = time_range

    def get_uptime(self):
        """Check if Redis has been up for at least 5 minutes"""
        query = "redis_uptime_in_seconds"
        try:
            data = self.prometheus.query(query)
            if data:
                uptime = int(float(data[0]["value"][1]))
                return uptime >= 300, f"{uptime}s"
            return False, "N/A"
        except Exception as e:
            return False, f"error: {str(e)}"

    def get_connection_metrics(self):
        """Get connection stats including rejections and available connections"""
        metrics = {}
        try:
            # Rejected connections
            rejected = self.prometheus.query(
                f"rate(redis_rejected_connections_total[{self.time_range}])"
            )
            metrics['rejected'] = float(rejected[0]["value"][1]) if rejected else 0
            
            # Connection usage
            max_clients = self.prometheus.query("redis_config_maxclients")
            connected = self.prometheus.query("redis_connected_clients")
            
            if max_clients and connected:
                max_val = float(max_clients[0]["value"][1])
                connected_val = float(connected[0]["value"][1])
                metrics['available'] = max_val - connected_val
                metrics['usage_pct'] = (connected_val / max_val) * 100
            else:
                metrics['available'] = "N/A"
                metrics['usage_pct'] = "N/A"
                
        except Exception as e:
            metrics['error'] = str(e)
            
        return metrics

    def get_performance_metrics(self):
        """Get latency, throughput, and cache hit ratio"""
        metrics = {}
        try:
            # Throughput
            throughput = self.prometheus.query(
                f"rate(redis_commands_processed_total[{self.time_range}])"
            )
            metrics['throughput'] = f"{float(throughput[0]['value'][1]):.2f}/s" if throughput else "N/A"
            
            # Cache hit ratio
            hits = self.prometheus.query(
                f"rate(redis_keyspace_hits_total[{self.time_range}])"
            )
            misses = self.prometheus.query(
                f"rate(redis_keyspace_misses_total[{self.time_range}])"
            )
            
            if hits and misses:
                hit_rate = float(hits[0]["value"][1])
                miss_rate = float(misses[0]["value"][1])
                ratio = hit_rate / (hit_rate + miss_rate) if (hit_rate + miss_rate) > 0 else 0
                metrics['hit_ratio'] = f"{ratio * 100:.2f}%"
            else:
                metrics['hit_ratio'] = "N/A"
                
        except Exception as e:
            metrics['error'] = str(e)
            
        return metrics

    def get_memory_metrics(self):
        """Get memory usage and fragmentation"""
        metrics = {}
        try:
            # Fragmentation
            frag = self.prometheus.query("redis_mem_fragmentation_ratio")
            metrics['fragmentation'] = float(frag[0]["value"][1]) if frag else "N/A"
            
        except Exception as e:
            metrics['error'] = str(e)
            
        return metrics

    def print_redis_metrics(self):
        """Print comprehensive Redis health report"""
        print(f"\n{Colors.BOLD}{Colors.UNDERLINE}{Colors.BLUE}Redis Health Report{Colors.END}\n")
        
        # Uptime check
        healthy, uptime = self.get_uptime()
        status = f"{Colors.GREEN}HEALTHY{Colors.END}" if healthy else f"{Colors.YELLOW}WARNING{Colors.END}"
        print(f"Status: {status} (Uptime: {uptime})")
        
        # Connection metrics
        conn_metrics = self.get_connection_metrics()
        print(f"\n{Colors.BOLD}{Colors.BLUE}Connection Metrics{Colors.END}\n")
        print(f"Rejected connections (rate): {conn_metrics.get('rejected', 'N/A')}")
        print(f"Available connections: {conn_metrics.get('available', 'N/A')}")
        print(f"Connection usage: {conn_metrics.get('usage_pct', 'N/A')}%")
        
        # Performance metrics
        perf_metrics = self.get_performance_metrics()
        print(f"\n{Colors.BOLD}{Colors.BLUE}Performance Metrics{Colors.END}\n")
        print(f"Throughput: {perf_metrics.get('throughput', 'N/A')}")
        print(f"Cache hit ratio: {perf_metrics.get('hit_ratio', 'N/A')}")
        
        # Memory metrics
        mem_metrics = self.get_memory_metrics()
        print(f"\n{Colors.BOLD}{Colors.BLUE}Memory Metrics{Colors.END}\n")
        print(f"Fragmentation ratio: {mem_metrics.get('fragmentation', 'N/A')}")
        
        # Health summary
        print(f"\n{Colors.BOLD}{Colors.BLUE}Health Summary{Colors.END}\n")
        warnings = []
        if not healthy:
            warnings.append("Redis restarted recently (<5m)")
        if conn_metrics.get('rejected', 0) > 0:
            warnings.append("Connection rejections detected")
        if float(mem_metrics.get('fragmentation', 0)) > 1.5:
            warnings.append("High memory fragmentation (>1.5)")
            
        if warnings:
            print("WARNINGS:")
            for warning in warnings:
                print(f"- {Colors.YELLOW}{warning}{Colors.END}")
        else:
            print("No critical issues detected")

class Colors:
    """ANSI color codes"""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"

if __name__ == "__main__":
    print("\n##############################################################")
    print(f"## {Colors.BOLD}{Colors.CYAN}Thought Machine CSRE Home Assessment {Colors.END}{Colors.BOLD}## Alberto Crescini {Colors.END}##")
    print("##############################################################\n")
    args = parse_args()
    
    try:
        config.load_kube_config(context=args.cluster)
    except Exception as e:
        print(f"Failed to load cluster {args.cluster}: {str(e)}")
        exit(1)

    u = Utils()
    port = u.start_port_forward("ingress-nginx-controller", 
                              container_port=80,
                              namespace=args.ingress_namespace)
    reverse_proxy_url = f"http://localhost:{port}"
    print(f"Opened a port-forward to NGINX Ingress controller at: {reverse_proxy_url}")

    prometheus_url = f"{reverse_proxy_url}/prom"

    if u.is_this_up(prometheus_url):
        print(f"Prometheus is up! Monitoring namespace '{args.namespace}' on K8s Cluster '{args.cluster}'")
        prometheus = PrometheusInspector(prometheus_url)

        ingress = IngressInspector(prometheus, time_range=args.time_range)
        ingress.print_ingress_metrics()
        
        guestbook_pods = u.get_guestbook_pods(namespace=args.namespace)
        guestbook = GuestbookDistributionInspector(prometheus,
                                                 namespace=args.namespace,
                                                 pod_list=guestbook_pods)
        guestbook.print_distribution_table()

        whereami = WhereamiInspector(prometheus, 
                                   namespace=args.namespace, 
                                   time_range=args.time_range)
        whereami.print_success_rate()

        redis = RedisInspector(prometheus, time_range=args.time_range)
        redis.print_redis_metrics()
        
    else:
        print("Prometheus is not reachable.")