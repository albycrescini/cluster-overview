# Thought Machine Take Home Challenge

## Premise

The premise of this challenge is that you are an engineer who has been asked to work with a client
to validate that their deployments across their Kubernetes clusters are healthy. They have provided
you with a dev cluster with an example of the workload, but they will expect to run the solution
against multiple different clusters and namespaces.

## Task

The aim of this challenge is to create a set of scripts that will inspect a cluster and the
applications on that cluster to verify that is healthy. You can assume that basic tooling like
`bash`, `kubectl`, `curl`, `go` and `python` are installed, and you can install additional tooling
if documented or automated. Solutions should use `go` or `python` in some combination.

To create a cluster you will need to have `minikube` installed.
Once you have minikube installed then you can use the `Makefile` to create the cluster and deployments.

## Installing Minikube

Please select the specific OS and CPU architecture, then run the command listed on the page.
[Minikube](https://minikube.sigs.k8s.io/docs/start/?arch=/macos/arm64/stable/binary+download)

```bash
curl -LO https://github.com/kubernetes/minikube/releases/latest/download/minikube-darwin-arm64
sudo install minikube-darwin-arm64 /usr/local/bin/minikube
```

The cluster will have the following applications installed:

- Nginx Ingress
- Prometheus
- Kube State Metrics

There are two applications called `guestbook` and `whereami` which are also running. `guestbook` is
a microservice style app, with multiple replicas running that need to run in multiple availability
zones, talking to a Redis backend. `whereami` is a stateless application that serves information
about the current connection. `guestbook` and `whereami` can run in multiple namespaces, so a
solution will need to take account of each namespace individually.

## Requirements

The script should report at least:

- Success rate of the nginx-ingress
- Success rate of the whereami service
- Whether the pods guestbook are distributed across availability zones on the nodes.
- Latency report of the ingress
- Redis health

The script should be executable in the following format: `./<script> <cluster> <namespace>`. The
solution should also have a README that provides some documentation of what the solution is and some
discussion of trade-offs made in the approach.

## Cleanup

To delete the cluster created during the challenge, run `make clean`. This will remove the cluster created.
