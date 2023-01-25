# k8s-l3-lb

A pod-aware external LoadBalancer implementation for kubernetes in a pure-l3 network.  l3-lb is intended to run alongside [bgp on each k8s node](https://github.com/nihr43/bgp-unnumbered) in a baremetal cluster, resulting in a network where the routers themselves become aware of kubernetes service ips, and are able to route directly to the physical hosts running the matched pods.  If replicas > 1, a single ip is duplicated in an anycast arrangement, enabling equal-cost-multipath load balancing from the perspective of an equally-connected router.

## implementation

This project is similar to metallb, which is a vastly more complete solution.

This differs from metallb in bgp mode as this daemon does not peer with bgp itself - the /32 loopback addresses provides a simple "interface" between the two systems.  FRR is configured to listen for and advertise any prefix found on the lo interface.  A caveat to this approach is that ingress controllers will not preserve source ips when handing off connections to backing services.  nginx-ingress for example will log the correct source ip of a request, but the backing service will see a request from the cluster ip of the ingress pod.  In the future i hope to experiment with advertising prefixes from python directly to remove the ExternalIP component.

## installation

l3lb can run as either a daemonset or a systemd unit.  For a 'classic' systemd unit installation, see `ansible_installation.example`.

Alternatively, l3lb can run as daemonset within k8s itself.  `kubectl apply -f daemonset.yml`.  Three capabilities are mapped into the containers to allow this to work: `hostNetwork: true`, `automountServiceAccountToken: true`, `capabilities: add: ["NET_ADMIN"]`.  This style of approach is used by the likes of metallb, traefik, rook, calico, etc.

Assuming the existence of a docker registry at `images.local:5000`, `make` will build and push the project.
`daemonset.yml` references this uri.

## example

l3lb service learning and applying loadbalancer configuratons:

```
journalctl -f -u l3lb
Oct 04 19:19:32 x470d4u-zen-9679c l3lb[1462]: INFO:root:minio-54666bfbb5-4c6s6 found on local node matching loadbalancer 10.0.100.112
Oct 04 19:19:35 x470d4u-zen-9679c l3lb[1462]: INFO:root:minio-54666bfbb5-4c6s6 found on local node matching loadbalancer 10.0.100.112
Oct 04 19:19:38 x470d4u-zen-9679c l3lb[1462]: INFO:root:minio-54666bfbb5-4c6s6 found on local node matching loadbalancer 10.0.100.1
Oct 04 19:19:38 x470d4u-zen-9679c l3lb[1462]: INFO:root:assuming address 10.0.100.1
Oct 04 19:19:38 x470d4u-zen-9679c l3lb[1462]: INFO:root:forfeiting address 10.0.100.112
Oct 04 19:20:46 x470d4u-zen-9679c l3lb[1462]: INFO:root:minio-54666bfbb5-4c6s6 found on local node matching loadbalancer 10.0.100.1
Oct 04 19:20:58 x470d4u-zen-9679c l3lb[1462]: INFO:root:minio-54666bfbb5-4c6s6 found on local node matching loadbalancer 10.0.100.1
Oct 04 19:20:58 x470d4u-zen-9679c l3lb[1462]: INFO:root:postgres-55667f648b-7qtck found on local node matching loadbalancer 10.0.100.2
Oct 04 19:20:58 x470d4u-zen-9679c l3lb[1462]: INFO:root:assuming address 10.0.100.2
Oct 04 19:21:06 x470d4u-zen-9679c l3lb[1462]: INFO:root:minio-54666bfbb5-4c6s6 found on local node matching loadbalancer 10.0.100.1
Oct 04 19:21:06 x470d4u-zen-9679c l3lb[1462]: INFO:root:postgres-55667f648b-7qtck found on local node matching loadbalancer 10.0.100.2
Oct 04 19:21:15 x470d4u-zen-9679c l3lb[1462]: INFO:root:minio-54666bfbb5-4c6s6 found on local node matching loadbalancer 10.0.100.1
Oct 04 19:23:23 x470d4u-zen-9679c l3lb[1462]: INFO:root:jenkins-5dfdf8cf55-dq9b4 found on local node matching loadbalancer 10.0.100.3
Oct 04 19:23:23 x470d4u-zen-9679c l3lb[1462]: INFO:root:assuming address 10.0.100.3
```

learned routes on a non-kubernetes node running bgp:

```
~$ ip route | grep 10.0.100.
10.0.100.1 nhid 10 via inet6 fe80::2e0:edff:fe0a:bdae dev enp36s0 proto bgp metric 20 
10.0.100.2 nhid 10 via inet6 fe80::2e0:edff:fe0a:bdae dev enp36s0 proto bgp metric 20 
10.0.100.3 nhid 10 via inet6 fe80::2e0:edff:fe0a:bdae dev enp36s0 proto bgp metric 20 
10.0.100.4 nhid 10 via inet6 fe80::2e0:edff:fe0a:bdae dev enp36s0 proto bgp metric 20
```

effect of draining node x470d4u-zen-9679c:

```
Oct 04 19:32:36 x470d4u-zen-9679c l3lb[1462]: INFO:root:forfeiting address 10.0.100.1
Oct 04 19:32:36 x470d4u-zen-9679c l3lb[1462]: INFO:root:forfeiting address 10.0.100.3
```

causing pods and their associated loadbalancer ips to get rescheduled on node x470d4u-zen-420c2:

```
Oct 04 19:32:37 x470d4u-zen-420c2 l3lb[1544]: INFO:root:minio-54666bfbb5-n2mlx found on local node matching loadbalancer 10.0.100.1
Oct 04 19:32:37 x470d4u-zen-420c2 l3lb[1544]: INFO:root:jenkins-5dfdf8cf55-gh225 found on local node matching loadbalancer 10.0.100.3
Oct 04 19:32:38 x470d4u-zen-420c2 l3lb[1544]: INFO:root:assuming address 10.0.100.1
Oct 04 19:32:38 x470d4u-zen-420c2 l3lb[1544]: INFO:root:assuming address 10.0.100.3
```

the following shows an anycast scenario: a stateless nginx deployment has been scaled up, resulting in 10.0.100.10 being provisioned on three different k8s nodes.  the effect is that the spine router shown has learned multiple routes for 10.0.100.10/32 via bgp, and and equal cost multi-path route has been installed in the kernel routing table.  the network itself is routing directly to and load balancing for pods on different physical hosts.

```
10.0.100.10 nhid 41 proto bgp metric 20
	nexthop via inet6 fe80::aaa1:59ff:fe08:b8f4 dev enp3s6f1 weight 1
	nexthop via inet6 fe80::d250:99ff:feda:f95a dev enp3s8f1 weight 1
	nexthop via inet6 fe80::ae1f:6bff:fe20:b4e2 dev enp3s8f0 weight 1
```

example service manifest to provision 10.0.100.6 for deployment labeled 'app: nginx':

```
---
apiVersion: v1
kind: Service
metadata:
  name: nginx
  labels:
    app: nginx
spec:
  ports:
    - port: 80
  selector:
    app: nginx
  type: LoadBalancer
  externalIPs:
    - 10.0.100.6
```
