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
import netifaces  # type: ignore
import ipaddress
import random
from time import sleep
from datetime import datetime
from kubernetes import client, config  # type: ignore
from typing import List
from kubernetes.client.models import V1Pod, V1Service  # type: ignore

if os.getenv("L3LB_DEBUG") == "true":
    debug = True
else:
    debug = False


def get_address_state(dev: str, address: str) -> bool:
    """
    determine whether a given address is already assigned
    """
    # 2 is address family AF_INET aka ipv4
    addresses = netifaces.ifaddresses(dev).get(2)

    for a in addresses:
        if a.get("addr") == address:
            return True

    return False


def provision_address(dev: str, address: str, netmask: str) -> None:
    """
    assure an address is assigned to a device
    """
    if debug:
        print("{} is being enforced".format(address))
    if get_address_state(dev, address) is False:
        print("assuming address " + address)
        os.system("ip address add " + address + netmask + " dev " + dev)


def enforce_no_address(dev: str, address: str, netmask: str) -> None:
    """
    assure an address is not assigned to a device
    """
    if get_address_state(dev, address) is True:
        print("forfeiting address " + address)
        os.system("ip address del " + address + netmask + " dev " + dev)


def local_pod_match(pods, lb) -> bool:
    """
    determine if a LoadBalancer's 'selector' matches any local pods.
    this is a determining factor whether we enforce the address.
    """
    for pod in pods:
        for selector in lb.spec.selector:
            # if a pod has any label that matches the lb's selector, it is considered a match.
            # we save a little effort by returning immediately; there is no need to know of multiple matches.
            if pod.metadata.labels.get(selector):
                if pod.metadata.labels.get(selector) == lb.spec.selector.get(selector):
                    if debug:
                        print(
                            "pod {} matches lb {} with selector {}={}".format(
                                pod.metadata.name,
                                lb.metadata.name,
                                selector,
                                lb.spec.selector.get(selector),
                            )
                        )
                    return True

    return False


def get_pods(client) -> List[V1Pod]:
    """
    get a list of local, running, ready, non-terminating pods
    """
    api = client.CoreV1Api()
    current_node = socket.gethostname()
    local_pods = api.list_pod_for_all_namespaces(
        field_selector=f"spec.nodeName={current_node}"
    ).items

    valid_pods = []
    for pod in local_pods:
        if pod.status.phase == "Running" and all(
            p.ready for p in pod.status.container_statuses
        ):
            if not pod.metadata.deletion_timestamp:
                valid_pods.append(pod)

    return valid_pods


def get_loadbalancers(client) -> List[V1Service]:
    """
    get a list of services of type LoadBalancer
    """
    api = client.CoreV1Api()
    return [
        service
        for service in api.list_service_for_all_namespaces().items
        if service.spec.type == "LoadBalancer"
    ]


def existing_ips_in_range(dev: str, net_range: str):
    """
    get a list of all ips in range which are currently assigned to an interface
    """
    parsed_addresses = []
    addresses = netifaces.ifaddresses(dev).get(2)

    for a in addresses:
        try:
            address = a.get("addr")
            if type(ipaddress.ip_address(address)) is ipaddress.IPv4Address:
                if ipaddress.IPv4Address(address) in ipaddress.IPv4Network(net_range):
                    parsed_addresses.append(address)
        except ValueError:
            pass

    return parsed_addresses


if __name__ == "__main__":
    try:
        config.load_incluster_config()
    except config.config_exception.ConfigException:
        config.load_kube_config()

    prefix = os.getenv("L3LB_PREFIX")
    interface = os.getenv("L3LB_INTERFACE", "lo")
    if not prefix:
        raise (KeyError)

    print(f"using prefix {prefix}")
    print(f"using interface {interface}")

    while True:
        sleep(random.randrange(1, 10))
        if debug:
            start_time = datetime.now()

        pods = get_pods(client)
        candidate_ips = []

        for lb in get_loadbalancers(client):
            if local_pod_match(pods, lb):
                for ip in lb.spec.external_i_ps:
                    candidate_ips.append(ip)

        """
        First we enforce the existance of all candidate ips.  provision_address is idempotent.
        Then we enforce the absence of discovered ips which match the prefix L3LB_PREFIX but are not in the set candidate_ips.
        This mechanism lets us garbage collect ips without persisting any state other than the configured prefix.
        """
        for ip in candidate_ips:
            provision_address(interface, ip, "/32")

        invalid_ips = list(
            set(existing_ips_in_range(interface, prefix)).difference(candidate_ips)
        )

        for ip in invalid_ips:
            enforce_no_address(interface, ip, "/32")

        if debug:
            timediff = datetime.now() - start_time
            print("reconciliation took {}\n".format(timediff))
