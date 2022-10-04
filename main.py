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


class loadbalancer():
    def __init__(self, ip, nodes):
        self.ip = ip
        self.nodes = []


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


def provision_address(dev: str, address: str, netmask: str, logging, netifaces) -> None:
    '''
    assure an address is assigned to a device
    '''
    if get_address_state(dev, address) is False:
        logging.info('assuming address')
        os.system('ip address add ' + address + netmask + ' dev ' + dev)


def enforce_no_address(dev: str, address: str, netmask: str, logging, netifaces) -> None:
    '''
    assure an address is not assigned to a device
    '''
    if get_address_state(dev, address) is True:
        logging.info('forfeiting address')
        os.system('ip address del ' + address + netmask + ' dev ' + dev)


def local_pod_match(lb) -> bool:
    '''
    determine if a loadbalancer is associated with any local pods.
    this is a determining factor whether we enforce the address.
    '''


def get_loadbalancers():
    '''
    get a list of all loadbalancer objects
    '''


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
