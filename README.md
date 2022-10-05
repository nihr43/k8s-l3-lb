# k8s-l3-lb

An external LoadBalancer implementation for kubernetes in a pure-l3 network.

## implementation

This project is similar to metallb, though the scope is strictly limited to bringing up /32 ip addresses on the localhost interfaces of k8s cluster nodes - for which routes are advertised by bgp deamons running on the physical hosts.

This differs from metallb in bgp mode as this daemon does not peer with bgp itself - the /32 loopback addresses provide a simple "interface" between the two systems.

The pure-l3 approach allows us to provision pod-aware unicast or anycast loadbalancer endpoints, while benefiting from all the attributes of an intelligently routed datacenter network.

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
