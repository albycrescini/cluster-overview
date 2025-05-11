MINIKUBE_VERSION ?= latest
CLUSTER_NAME ?= tm-csre
NUM_NODES ?= 3


.PHONY: all install minikube kubectl delete clean label-nodes

all:  minikube

install: minikube deploy

minikube:
		@minikube start --cpus=2 --memory=2048MB --profile ${CLUSTER_NAME} --nodes ${NUM_NODES} --disk-size 3GB
		@kubectl taint nodes ${CLUSTER_NAME} "node-role.kubernetes.io/control-plane:NoSchedule" --overwrite > /dev/null
		$(MAKE) label-nodes

label-nodes:
		@for node in $$(kubectl get nodes --no-headers --sort-by=.metadata.creationTimestamp | cut -d' ' -f1); do \
		kubectl label nodes $$node topology.kubernetes.io/zone=$$node --overwrite > /dev/null ;  \
		done

deploy:
		@echo "Installing services"
		kubectl --context ${CLUSTER_NAME} apply -f ./ingress.yaml

		kubectl --context ${CLUSTER_NAME} wait pod -lapp.kubernetes.io/component=controller  -n ingress-nginx --for=condition=Ready --timeout=180s

		kubectl --context ${CLUSTER_NAME} create ns monitoring

		kubectl --context ${CLUSTER_NAME} apply -f ./prom.yaml
		kubectl --context ${CLUSTER_NAME} apply -f ./ksm.yaml
		kubectl --context ${CLUSTER_NAME} apply -f ./whereami.yaml
		kubectl --context ${CLUSTER_NAME} apply -f ./guestbook.yaml

stop:
		@echo "Stopping Minikube cluster"
		minikube stop --profile ${CLUSTER_NAME}

delete:
		@echo "Deleting Minikube cluster with purge"
		minikube delete --profile ${CLUSTER_NAME} --purge

clean: stop delete #Combines stop and delete for a quick cleanup

