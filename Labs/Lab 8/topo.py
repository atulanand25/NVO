#!/usr/bin/python

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel
import os

def run_hybrid_topo():
    net = Mininet(controller=RemoteController, switch=OVSSwitch, waitConnected=False)

    print("*** Adding Remote Controller")
    net.addController('c0', ip='127.0.0.1', port=6633)

    print("*** Creating SW3 (Access Switch) and h1")
    sw3 = net.addSwitch('sw3', dpid='3', protocols='OpenFlow13')
    
    # h1 still needs a default route defined so it knows to ARP for it
    h1 = net.addHost('h1', ip='200.1.1.1/24', defaultRoute='via 200.1.1.254')

    print("*** Linking h1 to SW3 (Port 1)")
    net.addLink(h1, sw3)

    print("*** Starting Mininet")
    net.start()

    # --- HYBRID PATCHING ONLY ---
    print("*** Patching SW3 to Physical Bridges sw1 and sw2")
    
    # Patch to SW1
    os.system('sudo ip link add sw3-sw1 type veth peer name sw1-sw3')
    os.system('sudo ovs-vsctl add-port sw3 sw3-sw1 -- set Interface sw3-sw1 ofport_request=2')
    os.system('sudo ovs-vsctl add-port sw1 sw1-sw3 -- set Interface sw1-sw3 ofport_request=1')
    os.system('sudo ip link set sw3-sw1 up')
    os.system('sudo ip link set sw1-sw3 up')

    # Patch to SW2
    os.system('sudo ip link add sw3-sw2 type veth peer name sw2-sw3')
    os.system('sudo ovs-vsctl add-port sw3 sw3-sw2 -- set Interface sw3-sw2 ofport_request=3')
    os.system('sudo ovs-vsctl add-port sw2 sw2-sw3 -- set Interface sw2-sw3 ofport_request=1')
    os.system('sudo ip link set sw3-sw2 up')
    os.system('sudo ip link set sw2-sw3 up')

    print("\n*** HYBRID TOPOLOGY READY.")
    print("*** No host-level IP on sw3. Ryu must handle Gateway logic.")
    
    CLI(net)
    
    print("*** Cleaning up...")
    os.system('sudo ip link del sw3-sw1')
    os.system('sudo ip link del sw3-sw2')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_hybrid_topo()