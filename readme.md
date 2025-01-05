# l3lb

An external LoadBalancer implementation for kubernetes in a pure-l3 network.  l3lb is intended to run alongside [bgp on each k8s node](https://github.com/nihr43/bgp-unnumbered) in a baremetal cluster, resulting in a network where the routers themselves become aware of kubernetes service ips, and are able to route directly to the physical hosts running the matched pods.  If replicas > 1, a single ip is duplicated in an anycast arrangement, enabling equal-cost-multipath load balancing from the perspective of an equally-connected router.

## implementation

l3lb watches service and endpoint events and reconciles candidate ips for each node on each event.  The readiness of relevant pods is checked, so it will pull an ip if a pod is unhealthy, terminating, pending, etc.  Ips found on the interface belonging to the configured prefix which do not match any configured service are garbage collected on each tick - allowing us to avoid storing any other state.

l3lb itself does not peer with bgp.  It is designed to run alongside an frr configuration such as this:

```
      frr defaults datacenter

      router bgp {{hostvars["as_number"]}}
        bgp router-id {{hostvars["loopback"]}}
        bgp fast-convergence
        bgp bestpath compare-routerid
        bgp bestpath as-path multipath-relax
{% for i in hostvars["bgp_interfaces"] %}
        neighbor {{i}} interface remote-as external
{% endfor %}
        address-family ipv4 unicast
          redistribute connected
{% for i in hostvars["bgp_interfaces"] %}
          neighbor {{i}} route-map default in
{% endfor %}

      ip prefix-list p1 permit 10.0.0.0/16 ge 32
      ip prefix-list p1 permit 172.30.0.0/16 le 27
      ip prefix-list p1 permit 0.0.0.0/0

      route-map default permit 10
        match ip address prefix-list p1
```

`redistribute connected` along with `permit 10.0.0.0/16 ge 32` causes frr to simply detect and advertise /32 addresses on `lo`.  An `L3LB_PREFIX` in this case might be `10.0.100.0/24`.

An example manifest to provision 10.0.100.6 might look like this:

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
  loadBalancerIP: 10.0.100.6
```

I wrote l3lb to run on k8s hosts running bgp unnumbered.  Metallb in frr mode in my experience doesn't seem to play nice when you are already running frr on the host.

## installation

l3lb is intended to be run as a daemonset.  `daemonset.yml` is included, as well as terraform module `main.yml`.  To pull the terraform module into a project and update:

```
mkdur -p modules
git -C modules submodule add git@github.com:nihr43/k8s-l3-lb.git
git submodule update --recursive --remote
```

```
module "l3lb" {
  source    = "./modules/k8s-l3-lb"
  prefix    = "10.0.100.0/24"
  interface = "lo"
}
```

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
