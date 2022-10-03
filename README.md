# k8s-l3-lb

An external LoadBalancer implementation for kubernetes in a pure-l3 network.

## implementation

This project is similar to metallb, though the scope is strictly limited to bringing up /32 ip addresses on the localhost interfaces of k8s cluster nodes - for which routes are advertised by bgp deamons running on the physical hosts.

This differs from metallb in bgp mode as this daemon does not peer with bgp itself - the /32 loopback addresses provide a simple "interface" between the two systems.

The pure-l3 approach allows us to provision pod-aware unicast or anycast loadbalancer endpoints, while benefiting from all the attributes of an intelligently routed datacenter network.
