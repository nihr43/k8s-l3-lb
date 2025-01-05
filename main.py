"""
>>> import netifaces

No common machine should have address 1.1.1.1:
>>> get_address_state('lo', '1.1.1.1', netifaces)
False

But we should have 127.0.0.1:
>>> get_address_state('lo', '127.0.0.1', netifaces)
True
"""

import os
import socket
import netifaces  # type: ignore
import ipaddress
import queue
import threading
from datetime import datetime
from kubernetes import client, config, watch  # type: ignore
from typing import List
from kubernetes.client.models import V1Pod, V1Service  # type: ignore
from kubernetes.client.exceptions import ApiException

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


def get_pods(api) -> List[V1Pod]:
    """
    get a list of local, running, ready, non-terminating pods
    """
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


def get_loadbalancers(api) -> List[V1Service]:
    """
    get a list of services of type LoadBalancer
    """
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


def watch_services():
    start_time = datetime.now()
    config.load_kube_config()
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_service_for_all_namespaces):
        service_event = {
            "type": "service",
            "event_type": event["type"],
            "name": event["object"].metadata.name,
        }
        if (
            event["object"].metadata.creation_timestamp.replace(tzinfo=None)
            > start_time
        ):
            # we dont need to trigger on service creation because
            # there are sure to be subsequent endpoint events
            if service_event["event_type"] in ["MODIFIED"]:
                event_queue.put(service_event)


def watch_endpoints():
    start_time = datetime.now()
    config.load_kube_config()
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_endpoints_for_all_namespaces):
        endpoint_event = {
            "type": "endpoint",
            "event_type": event["type"],
            "name": event["object"].metadata.name,
        }
        if (
            event["object"].metadata.creation_timestamp.replace(tzinfo=None)
            > start_time
        ):
            if endpoint_event["event_type"] in ["MODIFIED", "DELETED"]:
                event_queue.put(endpoint_event)


def poll_queue(api, interface, prefix):
    while True:
        event = event_queue.get()
        if event is None:
            print("queue exiting")
            break

        if debug:
            print(f"{event['type']} event: {event['event_type']} {event['name']}")

        reconcile(api, interface, prefix)


def reconcile(api, interface, prefix):
    if debug:
        start_time = datetime.now()

    pods = get_pods(api)
    candidate_ips = []

    for lb in get_loadbalancers(api):
        if local_pod_match(pods, lb):
            if (
                lb.status.load_balancer.ingress is None
                and lb.spec.load_balancer_ip is not None
            ):
                try:
                    print("allocating static load_balancer_ip")
                    lb.status.load_balancer.ingress = [{"ip": lb.spec.load_balancer_ip}]
                    api.patch_namespaced_service_status(
                        lb.metadata.name, lb.metadata.namespace, lb
                    )
                except ApiException as e:
                    print(e)
            candidate_ips.append(lb.spec.load_balancer_ip)

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


def main():
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

    api = client.CoreV1Api()
    reconcile(api, interface, prefix)

    service_thread = threading.Thread(target=watch_services, daemon=True)
    endpoints_thread = threading.Thread(target=watch_endpoints, daemon=True)
    service_thread.start()
    endpoints_thread.start()

    try:
        poll_queue(api, interface, prefix)
    except KeyboardInterrupt:
        print("Stopping...")
        event_queue.put(None)
        service_thread.join()
        endpoints_thread.join()


if __name__ == "__main__":
    event_queue = queue.Queue()
    main()
