# Cloud-Native Monitoring Stack on Kubernetes

**A complete observability and benchmarking pipeline on MicroK8s — a Java web app, a full Prometheus + Grafana monitoring stack, and a custom containerized load generator, all defined as Infrastructure as Code.**

[![Kubernetes](https://img.shields.io/badge/Kubernetes-MicroK8s-326CE5.svg?logo=kubernetes&logoColor=white)](https://microk8s.io/)
[![Prometheus](https://img.shields.io/badge/Prometheus-monitoring-E6522C.svg?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-dashboards-F46800.svg?logo=grafana&logoColor=white)](https://grafana.com/)
[![Docker](https://img.shields.io/badge/Docker-containers-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Newcastle University — *Cloud Computing*, 2025/26.

---

## Overview

This project provisions and instruments a cloud-native application stack on a single-node **MicroK8s** cluster. It deploys a Java benchmark web app, builds a production-style **observability pipeline** around it (Prometheus, Grafana, Node Exporter, kube-state-metrics, cAdvisor), and stress-tests it with a **purpose-built containerized load generator**. The captured metrics are then used to diagnose a real architectural limitation in the application.

Everything is declarative YAML — apply the manifests and the whole environment reproduces itself.

## Architecture

```
                          ┌──────────────────────┐
   load-generator ───────►│  java-benchmark app  │  NodePort 30000  /primecheck
   (20 req/s, custom)     └──────────┬───────────┘
                                     │
        ┌────────────────────────────┼───────────────────────────┐
        │ metrics                    │ metrics                    │ metrics
        ▼                            ▼                            ▼
  node-exporter (DaemonSet)   kube-state-metrics            cAdvisor (DaemonSet,
  host metrics :9100          cluster object state :8080    containerd socket) :8080
        └────────────────────────────┼───────────────────────────┘
                                     ▼
                         ┌───────────────────────┐
                         │      Prometheus       │  scrape every 15s, :9090
                         └──────────┬────────────┘
                                    ▼
                         ┌───────────────────────┐
                         │       Grafana         │  NodePort 31000
                         └───────────────────────┘
```

## Components

| Component | Kind | Purpose |
|-----------|------|---------|
| Kubernetes Dashboard | ServiceAccount + ClusterRoleBinding | Manual dashboard access via a `cluster-admin` bearer token (not the MicroK8s add-on) |
| javabenchmarkapp | Deployment + NodePort Service | Java web app exposed at `localhost:30000/primecheck` |
| Prometheus | ConfigMap + Deployment + Service | Scrapes all targets every 15s; RBAC for dynamic discovery |
| Node Exporter | DaemonSet | Host-level metrics — one agent per node, auto-scales with the cluster |
| kube-state-metrics | Deployment | Kubernetes object state (pod/deployment health) |
| cAdvisor | DaemonSet + Service | Per-container resource metrics, **adapted for MicroK8s containerd** |
| Grafana | Deployment + NodePort Service | Dashboards at `localhost:31000`, Prometheus data source |
| Load Generator | Python + Docker + Deployment | Configurable HTTP stress tool, pushed to a local registry |

## Repository structure

```
cloud-native-monitoring-stack/
├── README.md
├── LICENSE
├── .gitignore
├── manifests/
│   ├── 00-dashboard-admin.yaml          # Dashboard admin-user + RBAC
│   ├── 01-java-app.yaml                 # Java app Deployment + NodePort Service
│   ├── monitoring/
│   │   ├── 00-monitoring-rbac.yaml      # namespace + Prometheus RBAC
│   │   ├── 01-prometheus.yaml           # ConfigMap + Deployment + Service
│   │   ├── 02-node-exporter.yaml        # DaemonSet (+ Service)
│   │   ├── 03-kube-state-metrics.yaml   # Deployment (+ Service)
│   │   ├── 04-cadvisor.yaml             # DaemonSet (containerd) + Service
│   │   └── 05-grafana.yaml              # Deployment + NodePort Service
│   └── load-generator/
│       └── load-generator-deployment.yaml
├── load-generator/
│   ├── load_generator.py                # custom HTTP load tool
│   └── Dockerfile                       # python:3.9-slim image
├── docs/
│   └── images/                          # Grafana dashboards + screenshots
└── report/
    └── Report.pdf                       # full write-up
```

## Prerequisites

- MicroK8s with `dns`, `rbac`, and `registry` add-ons enabled
- `kubectl` and `docker` available on the host

## Deployment

Manifests are numbered so they apply in dependency order.

```bash
# 1. Dashboard access + the application
kubectl apply -f manifests/00-dashboard-admin.yaml
kubectl apply -f manifests/01-java-app.yaml

# 2. Monitoring stack (namespace/RBAC first)
kubectl apply -f manifests/monitoring/

# 3. Build, tag and push the load generator to the local registry
cd load-generator
docker build -t localhost:32000/load-generator:latest .
docker push localhost:32000/load-generator:latest
cd ..

# 4. Run the load generator
kubectl apply -f manifests/load-generator/load-generator-deployment.yaml
```

### Accessing the services

| Service | URL |
|---------|-----|
| Java app | `http://localhost:30000/primecheck` |
| Grafana | `http://localhost:31000` |
| Prometheus targets | `kubectl port-forward svc/prometheus-service 9090:9090 -n monitoring` then `http://localhost:9090/targets` |

The Dashboard login token is generated from the `admin-user` ServiceAccount created in `00-dashboard-admin.yaml`.

## The load generator

A small, dependency-light Python tool designed to be reusable and resilient:

- **Configurable** via `TARGET` and `FREQUENCY` environment variables (no rebuild needed).
- **Resilient** — wraps each request in `try/except`; any request over a 10s timeout is counted as a failure rather than hanging.
- **Self-reporting** — prints running totals, failures, and average response time, which Prometheus/Grafana then visualise.

## Results & findings

Driving the app at **20 req/s** produced a clean signal in Grafana (0 failures, ~0.143s average response time):

- **CPU** rose from idle and **stabilised at ~0.96 cores** even with all host cores available.
- **Memory** working-set sat around ~456 MB as the JVM allocated heap.

**Diagnosis — single-threaded bottleneck.** The `/primecheck` endpoint is single-threaded: it physically cannot exceed one core, with the remaining ~4% headroom consumed by kernel overhead (context switching, network stack) at 20 req/s.

**Scaling implication.** Vertical scaling (a faster core) won't help. **Horizontal scaling** — raising the Deployment replica count so work spreads across cores — is the correct strategy. The monitoring stack turned raw metrics into this actionable architectural conclusion.

## Technical challenges solved

- **cAdvisor on containerd:** the default cAdvisor expects `/var/run/docker.sock`, but MicroK8s uses containerd. The DaemonSet was reconfigured to mount the containerd socket (`/var/run/microk8s-socket/containerd.sock`) so container-level metrics actually collect.
- **Node-level monitoring as a DaemonSet:** Node Exporter runs as a DaemonSet rather than a Deployment, so any node added to the cluster is automatically monitored — no manual intervention.
- **Least-privilege RBAC:** Prometheus gets a scoped ClusterRole (`get`/`list`/`watch` on core resources only) for dynamic service discovery.

## Report

The full write-up — implementation detail, screenshots, and the complete performance discussion — is in [`report/Report.pdf`](report/Report.pdf).

## Note on the manifests

These YAML/Python files were transcribed from the figures in the original report. They've been organised into separate, ordered files for clarity (the report consolidated some into a single `monitoring-components.yaml`). The Services for `node-exporter` and `kube-state-metrics` are implied by the Prometheus scrape config but weren't pictured in the report — they're included here and flagged with comments, so verify them against your working cluster before relying on them.

## Author

**Karthik S** - MSc Cyber Security, Newcastle University.

## License

Released under the [MIT License](LICENSE).
