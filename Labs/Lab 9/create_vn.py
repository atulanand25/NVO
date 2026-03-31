import openstack
from loguru import logger
import json

logger.add("create_network.log", rotation="500 KB", level="INFO")

conn = openstack.connect()


def create_virtual_network(topology_file=None):
    """
    Creates network, subnet, and router from a topology JSON file.
    Only uses the 'network' section for OpenStack.
    """
    if not topology_file:
        logger.error("No topology file provided!")
        return

    try:
        with open(topology_file, "r") as f:
            topo = json.load(f)

        network_info = topo["network"]
        network_name = network_info["name"]
        subnet_name = network_info["subnet_name"]
        subnet_cidr = network_info["subnet"]
        gateway_ip = network_info["gateway"]
        router_name = network_info["router_name"]

    except Exception as e:
        logger.error(f"Failed to read topology file {topology_file}: {e}")
        return None

    # --- Create Network ---
    network = conn.network.find_network(network_name)

    if network:
        logger.info(f"Using existing network: {network.name}")
    else:
        network = conn.network.create_network(name=network_name)
        logger.info(f"Created network: {network.name}")

    # --- Create Subnet ---
    subnet = conn.network.find_subnet(subnet_name)
    if subnet:
        logger.info(f"Using existing subnet: {subnet.name}")
    else:
        subnet = conn.network.create_subnet(
            name=subnet_name,
            network_id=network.id,
            ip_version=4,
            cidr=subnet_cidr,
            gateway_ip=gateway_ip,
            dns_nameservers=["8.8.8.8", "8.8.4.4"],
            enable_dhcp=True
        )
        logger.info(f"Created subnet: {subnet.name}")

    # --- Create Router ---
    router = conn.network.find_router(router_name)
    if router:
        logger.info(f"Using existing router: {router.name}")
    else:
        router = conn.network.create_router(name=router_name)
        logger.info(f"Created router: {router.name}")

    # --- Set Router gateway to public network ---
    public_net = conn.network.find_network("public")
    if public_net:
        conn.network.update_router(router, external_gateway_info={"network_id": public_net.id})
        logger.info("Router gateway set to public network")
    else:
        logger.warning("Public network not found. Router gateway not set.")

    # --- Attach subnet to router if not already attached ---
    router_ports = [p.fixed_ips[0]['subnet_id'] for p in conn.network.ports(device_id=router.id)]
    if subnet.id in router_ports:
        logger.info(f"Subnet {subnet.name} already attached to router {router.name}")
    else:
        conn.network.add_interface_to_router(router, subnet_id=subnet.id)
        logger.info(f"Attached subnet {subnet.name} to router {router.name}")

    return network