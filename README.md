# k8s-l3-lb

An pod-aware external LoadBalancer implementation for kubernetes in a pure-l3 network.  l3-lb is intended to run alongside [bgp on each k8s node](https://github.com/nihr43/bgp-unnumbered) in a baremetal cluster, resulting in a network where the spine and leaf routers themselves are aware of kubernetes service declarations, and are able to efficiently route directly to the correct physical hosts running the matched pods.  If replicas > 1, a single ip is provisioned in an anycast arrangement, enabling equal-cost-multipath load balancing from the perspective of an equally-connected router.

## implementation

This project is similar to metallb, though the scope is strictly limited to bringing up /32 ip addresses on the localhost interfaces of k8s cluster nodes - for which routes are advertised by bgp deamons running on the physical hosts.

This differs from metallb in bgp mode as this daemon does not peer with bgp itself - the /32 loopback addresses provide a simple "interface" between the two systems.

## installation

An example systemd unit and ansible task file are included in this repo.  The daemon is intended to run on all kubernetes nodes, and expects to find `/root/.kube/config`.

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

example kubernetes_service resource being used in terraform:

```
resource "kubernetes_service" "jenkins" {
  metadata {
    name = "jenkins"
  }
  spec {
    selector = {
      app = "jenkins"
    }
    port {
      port        = "80"
      target_port = "8080"
    }
    type = "LoadBalancer"
    external_ips  = ["10.0.100.3"]
  }
}
```
