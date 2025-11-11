## Script Overview

The script monitors key metrics for two applications: `guestbook` and `whereami`, which are running in a Kubernetes cluster. The solution provides following insights:

* Ingress controller success and latency metrics.
* `whereami` service success rate.
* Distribution of `guestbook` pods across availability zones (AZs) on the nodes.
* Redis health and performance metrics.

The script collects and reports metrics from Prometheus, relying on Kubernetes API access for specific pod annotations and labels, and temporary port forwarding for traffic routing to the ingress controllers.

## Setup Instructions

The script is accessible from the `/solution` folder, inside which you can find two scripts:

1. **setup.sh**: This script creates  a Python virtual environment and installing the necessary dependencies.
2. **script.py**: This is the main script that runs the monitoring tasks.

### Step-by-Step Setup

1. Run the `setup.sh` script to create the virtual environment and install the required dependencies:

   ```bash
   ./setup.sh
   ```

2. Once the setup is complete, activate the virtual environment:

   ```bash
   source venv/bin/activate
   ```

3. To run the script, use the following format:

   ```bash
   ./script.py <cluster> <namespace>
   ```

   For example, to run the script for the `tm-csre` cluster, and monitoring the two applications in the `default` namespace you can run:

   ```bash
   ./script.py tm-csre default
   ```

## Changes Made to the Manifest Files

To expose relevant metrics to Prometheus, I made several updates to the Kubernetes manifests:

### whereami.yaml

* **Addition of Prometheus annotations**: I added the annotation `prometheus.io/path: '/metrics'` to allow Prometheus to scrape the metrics endpoint from the `whereami` service. Without this, Prometheus was able to reference the service but could not retrieve any metrics as the path wasn't specified.

### prom.yaml

* **Ingress controller scraping**: I updated the `prom.yaml` scrape configuration to include the ingress-nginx job. This allows Prometheus to collect traffic-related metrics like:

  * HTTP request rates and errors (`nginx_ingress_controller_requests`).
  * Latency distributions (`nginx_ingress_controller_request_duration_seconds`).

### ingress.yaml

* **Expose metrics port**: I added the line `containerPort: 10254` to expose the NGINX Ingress Controller metrics to Prometheus.

## Solution Details

The `setup` script sets up a Python virtual environment (venv), installs the necessary dependencies, and activates the environment. Once the setup is complete, you can run the script.

### Key Metrics Collected

* **Ingress Controller Analytics**:

  * Latency percentiles (P25-P99).
  * HTTP success rates (2xx / non-5xx errors).

* **Workload Distribution Analysis**:

  * Availability zone (AZ) and node distribution of `guestbook` pods.
  * Pod-to-node correlation to ensure proper distribution.

* **Application Health Monitoring**:

  * Success rate of the `whereami` service.

* **Redis Health**:

  * Connection statistics (rejected connections, available connections, usage).
  * Cache efficiency ratios (throughput, cache hit ratio).
  * Memory fragmentation analysis (important for detecting potential memory management issues).

### Dependencies

* **Prometheus**: The solution relies on Prometheus running in the `monitoring` namespace to scrape and collect metrics.
* **Kubernetes API**: Kubernetes API access is used to fetch pod-specific annotations and labels, and to perform port forwarding for traffic routing.
* **Port Forwarding**: The script temporarily opens a port forwarding connection on a separate thread to the reverse proxy, enabling traffic routing to the ingress controllers. This requires you to have access to the Cluster API dependent on the local `kubectl` configuration.

**Note**: *Please wait at least 5 minutes after the deployment to get some relevant metrics on the script.*


### Script Parameters

The script accepts the following command-line arguments:

* **`cluster`** *(positional)*:
  The name of the Kubernetes cluster to inspect. This is used for logging and contextual identification, especially when working with multiple clusters.

* **`namespace`** *(positional)*:
  The Kubernetes namespace where the monitored applications (`guestbook` and `whereami`) are deployed.

* **`--ingress-namespace`** *(optional, default: `ingress-nginx`)*:
  Specifies the namespace in which the ingress controller is running. I added this to cover the scenarios where the ingress controller has been deployed to a custom namespace.

* **`--time-range`** *(optional, default: `1h`)*:
  Defines the lookback duration for Prometheus queries, such as success rate and latency. Accepts time durations like `5m`, `1h`, etc., and determines the window over which metrics are aggregated.

## Sample Output

The script outputs the following metrics for each of the services:

### NGINX Ingress Controller

#### Latency (ms)

| Percentile | Latency    |
| ---------- | ---------- |
| p25        | 3.57 ms    |
| p50        | 8.89 ms    |
| p75        | 36.39 ms   |
| p95        | 1010.13 ms |
| p99        | 5367.03 ms |

#### Success Rates

| Metric               | Rate    |
| -------------------- | ------- |
| HTTP Code IS NOT 5xx | 100.00% |
| HTTP Code IS 2xx     | 90.78%  |

### Guestbook Pods AZ Distribution

| Node        | Zone    | Pod                       | Pod Count |
| ----------- | ------- | ------------------------- | --------- |
| tm-csre-m02 | unknown | frontend-8584979b46-5sklj | 1         |
| tm-csre-m03 | unknown | frontend-8584979b46-x5422 | 1         |

### WhereAmI Ingress - Success Rates

| Metric               | Rate    |
| -------------------- | ------- |
| HTTP Code IS NOT 5xx | 100.00% |
| HTTP Code IS 2xx     | 100.00% |

### Redis Health Report

* **Status**: HEALTHY (Uptime: 602s)
* **Connection Metrics**:

  * Rejected connections (rate): 0.0
  * Available connections: 9999.0
  * Connection usage: 0.01%
* **Performance Metrics**:

  * Throughput: 3.01/s
  * Cache hit ratio: 0.00%
* **Memory Metrics**:

  * Fragmentation ratio: 23.44

#### Health Summary

**WARNINGS**:

* High memory fragmentation (>1.5), which could indicate inefficiencies in memory management.

## Possible Enhancements
Here’s a revised and more rigorous version of that section, with clearer explanations and justified assumptions:

---

### Potential Enhancements and Trade-offs
* **Traffic Simulation**
  For the script to generate meaningful metrics—especially related to success rates and latency—the ingress controller must be receiving real traffic. In a testing or isolated environment, this often isn’t the case. A practical enhancement would be the implementation of a traffic generator class that programmatically issues HTTP requests to the exposed ingress endpoints. This would allow deterministic control over request volume, distribution, and timing, enabling more consistent metric evaluation.

* **Error Condition Injection**
  Observing changes in HTTP success rate metrics requires the presence of failed requests. This could be achieved by simulating client-side errors (e.g., issuing requests to invalid routes to trigger `404` responses), or by deliberately modifying the upstream service or ingress configuration to induce server-side errors such as `502`.

* **Adaptive Time Windows**
  The script currently uses a static time window for querying Prometheus metrics (e.g., `--time-range=1h`). This design simplifies parameterization but assumes uniform temporal relevance for all metrics. A more advanced approach would be to dynamically adjust the time window based on the metric type or volatility—e.g., shorter windows for high-frequency events like request rates, and longer windows for slower-changing metrics like memory usage.

* **Retry Logic for Transient Failures**
  The script does not implement retries for common transient errors, such as temporary Prometheus unavailability or Kubernetes API timeouts. Introducing a retry mechanism (with exponential backoff and jitter) would significantly increase robustness, especially in noisy or resource-constrained environments. The current assumption is that all external systems (Prometheus, Kubernetes API) are highly available, which does not always hold.

* **Graceful Error Handling**
  Error handling is currently minimal, lacking structured `try/except` blocks or context-aware logging. This introduces fragility: a single failed API call or malformed response can halt the script. Introducing explicit exception handling for known failure modes (e.g., HTTP errors, missing metrics, invalid kubeconfig) would improve the script’s fault tolerance and user feedback loop.
