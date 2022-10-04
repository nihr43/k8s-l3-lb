#!/usr/bin/python3

'''
>>> import netifaces

No common machine should have address 1.1.1.1:
>>> get_address_state('lo', '1.1.1.1', netifaces)
False

But we should have 127.0.0.1:
>>> get_address_state('lo', '127.0.0.1', netifaces)
True
'''

import random
from time import sleep


def get_address_state(dev: str, address: str, netifaces) -> bool:
    '''
    determine whether a given address is already assigned
    '''
    parsed_addresses = []
    ifaces = netifaces.ifaddresses(dev)

    for i in ifaces:
        for j in ifaces[i]:
            for a, b in j.items():
                if a == 'addr':
                    parsed_addresses.append(b)

    if address in parsed_addresses:
        return True
    else:
        return False


def provision_address(dev: str, address: str, netmask: str, logging, netifaces, os) -> None:
    '''
    assure an address is assigned to a device
    '''
    if get_address_state(dev, address, netifaces) is False:
        logging.info('assuming address ' + address)
        os.system('ip address add ' + address + netmask + ' dev ' + dev)


def enforce_no_address(dev: str, address: str, netmask: str, logging, netifaces, os) -> None:
    '''
    assure an address is not assigned to a device
    '''
    if get_address_state(dev, address, netifaces) is True:
        logging.info('forfeiting address ' + address)
        os.system('ip address del ' + address + netmask + ' dev ' + dev)


def local_pod_match(client, lb, current_node, logging) -> bool:
    '''
    determine if a LoadBalancer's 'selector' matches any local pods.
    this is a determining factor whether we enforce the address.
    '''
    api = client.CoreV1Api()
    matched_pods = []
    for pod in api.list_pod_for_all_namespaces().items:
        if pod.spec.node_name == current_node:
            if pod.metadata.labels.get('app') == lb.spec.selector.get('app'):
                logging.info(pod.metadata.name + ' found on local node matching loadbalancer ' + lb.spec.external_i_ps[0]) # TODO: if ever support more than one ip, this needs to change
                matched_pods.append(pod)
    if len(matched_pods) == 0:
        return False
    else:
        return True


def get_loadbalancers(client):
    '''
    get a list of services of type LoadBalancer
    '''
    api = client.CoreV1Api()
    lbs = []
    for service in api.list_service_for_all_namespaces().items:
        if service.spec.type == 'LoadBalancer':
            lbs.append(service)
    return lbs


if __name__ == '__main__':
    def privileged_main():
        import os
        import netifaces
        import logging
        from kubernetes import client, config

        logging.basicConfig(level=logging.INFO)
        config.load_kube_config()

        namespace = 'default'

        while True:
            sleep(random.randrange(1, 15))

            for lb in get_loadbalancers(client):
                if local_pod_match(lb):
                    provision_address('lo', lb.ip, '255.255.255.255', logging, netifaces)
                else:
                    # to maintain consistent state, we always actively enforce_no_address if no match
                    enforce_no_address('lo', lb.ip, '255.255.255.255', logging, netifaces)


    privileged_main()
