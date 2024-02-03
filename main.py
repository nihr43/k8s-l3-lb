"""
>>> import netifaces

No common machine should have address 1.1.1.1:
>>> get_address_state('lo', '1.1.1.1', netifaces)
False

But we should have 127.0.0.1:
>>> get_address_state('lo', '127.0.0.1', netifaces)
True

>>> import pylxd
>>> client = pylxd.Client()
>>> config = {'name': 'l3lb-testing',
...           'source': {'type': 'image',
...                      'mode': 'pull',
...                      'server': 'https://images.linuxcontainers.org',
...                      'protocol': 'simplestreams',
...                      'alias': 'alpine/edge'}}
>>> inst = client.instances.create(config, wait=True)
>>> inst.start(wait=True)
>>> inst.state().network['lo']['addresses'][0]
{'family': 'inet', 'address': '127.0.0.1', 'netmask': '8', 'scope': 'local'}
>>> inst.stop(wait=True)
>>> inst.delete(wait=True)
"""

import os
import socket
import netifaces
import ipaddress
import random
from time import sleep
from kubernetes import client, config


def get_address_state(dev: str, address: str, netifaces) -> bool:
    """
    determine whether a given address is already assigned
    """
    parsed_addresses = []
    ifaces = netifaces.ifaddresses(dev)

    for i in ifaces:
        for j in ifaces[i]:
            for a, b in j.items():
                if a == "addr":
                    parsed_addresses.append(b)

    if address in parsed_addresses:
        return True
    else:
        return False


def provision_address(dev: str, address: str, netmask: str, netifaces, os) -> None:
    """
    assure an address is assigned to a device
    """
    if get_address_state(dev, address, netifaces) is False:
        print("assuming address " + address)
        os.system("ip address add " + address + netmask + " dev " + dev)


def enforce_no_address(dev: str, address: str, netmask: str, netifaces, os) -> None:
    """
    assure an address is not assigned to a device
    """
    if get_address_state(dev, address, netifaces) is True:
        print("forfeiting address " + address)
        os.system("ip address del " + address + netmask + " dev " + dev)


def local_pod_match(pods, lb) -> bool:
    """
    determine if a LoadBalancer's 'selector' matches any local pods.
    this is a determining factor whether we enforce the address.
    """
    matched_pods = []

    for pod in pods:
        for selector in lb.spec.selector:
            # if a pod has any label that matches the lb's selector, it is considered a match
            if pod.metadata.labels.get(selector):
                if pod.metadata.labels.get(selector) == lb.spec.selector.get(selector):
                    print(
                        "pod {} matches lb {} with selector {}={}".format(
                            pod.metadata.name,
                            lb.metadata.name,
                            selector,
                            lb.spec.selector.get(selector),
                        )
                    )
                    matched_pods.append(pod)
    if len(matched_pods) == 0:
        return False
    else:
        return True


def get_pods(client):
    """
    get all running local pods
    """
    api = client.CoreV1Api()
    current_node = socket.gethostname()
    all_pods = api.list_pod_for_all_namespaces()
    local_pods = [pod for pod in all_pods.items if pod.spec.node_name == current_node]
    running_pods = [pod for pod in local_pods if pod.status.phase == "Running"]
    return running_pods


def get_loadbalancers(client):
    """
    get a list of services of type LoadBalancer
    """
    api = client.CoreV1Api()
    lbs = []
    for service in api.list_service_for_all_namespaces().items:
        if service.spec.type == "LoadBalancer":
            lbs.append(service)
    return lbs


def existing_ips_in_range(dev, netifaces, net_range, ipaddress):
    """
    get a list of all ips in range which are currently assigned to an interface
    """
    parsed_addresses = []
    ifaces = netifaces.ifaddresses(dev)

    for i in ifaces:
        for j in ifaces[i]:
            for a, b in j.items():
                if a == "addr":
                    try:
                        if type(ipaddress.ip_address(b)) is ipaddress.IPv4Address:
                            if ipaddress.IPv4Address(b) in ipaddress.IPv4Network(
                                net_range
                            ):
                                parsed_addresses.append(b)
                    except ValueError:
                        pass

    return parsed_addresses


if __name__ == "__main__":
    if os.getenv("L3LB_IN_K8S"):
        config.load_incluster_config()
    else:
        config.load_kube_config()

    network = os.getenv("L3LB_NETWORK")
    interface = os.getenv("L3LB_INTERFACE")

    print("using network " + network)
    print("using interface " + interface)

    while True:
        my_valid_ips = []
        sleep(random.randrange(1, 10))
        pods = get_pods(client)

        for lb in get_loadbalancers(client):
            if local_pod_match(pods, lb):
                for ip in lb.spec.external_i_ps:
                    my_valid_ips.append(ip)

        """
            in order to assure absence of leftover ips, or ips which belong to
            other nodes due to topology changes or pod migration, we create
            the list my_valid_ips and check any found addresses in the provided
            range against it.  this mechanism allows us to catch deletions -
            without any persisted state outside of kubernetes or the currently
            assigned addresses themselves.
            """
        for ip in my_valid_ips:
            provision_address(interface, ip, "/32", netifaces, os)

        invalid_ips = list(
            set(
                existing_ips_in_range(interface, netifaces, network, ipaddress)
            ).difference(my_valid_ips)
        )

        for ip in invalid_ips:
            enforce_no_address(interface, ip, "/32", netifaces, os)
