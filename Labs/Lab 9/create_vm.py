import openstack
from loguru import logger
import json

# OpenStack resources
IMAGE_NAME = "cirros-0.6.3-x86_64-disk"
FLAVOR_NAME = "cirros256"
EXTERNAL_NETWORK = "public"
SERVER_PREFIX = "cirros_auto_"
MAX_SCALE = 4
CPU_THRESHOLD = 10

# Connect to OpenStack
conn = openstack.connect()

# Logger setup
logger.add("autoscale.log", rotation="1 MB", level="INFO")


def get_internal_network_from_topology(topology_file="topology.json"):
    """
    Reads the internal network name from topology JSON.
    """
    try:
        with open(topology_file, "r") as f:
            topo = json.load(f)
        network_name = topo["network"]["name"]
        logger.info(f"Using internal network from topology: {network_name}")
        return network_name
    except Exception as e:
        logger.error(f"Failed to read topology file: {e}")
        return None


def create_server(server_name, topology_file="topology.json"):
    """
    Create a server using the internal network from topology JSON.
    """
    INTERNAL_NETWORK = get_internal_network_from_topology(topology_file)
    if not INTERNAL_NETWORK:
        logger.error("Cannot find internal network. Aborting server creation.")
        return None, None

    logger.info(f"Starting server creation: {server_name}, {INTERNAL_NETWORK}")

    # Find OpenStack resources
    image = conn.image.find_image(IMAGE_NAME)
    flavor = conn.compute.find_flavor(FLAVOR_NAME)
    private_network = conn.network.find_network(INTERNAL_NETWORK)
    public_network = conn.network.find_network(EXTERNAL_NETWORK)

    if not image or not flavor or not private_network or not public_network:
        logger.error("Missing required OpenStack resources!")
        return None, None

    logger.info(f"Image: {image.id}, Flavor: {flavor.id}, Network: {private_network.id}")

    # Create server
    server = conn.compute.create_server(
        name=server_name,
        image_id=image.id,
        flavor_id=flavor.id,
        networks=[{"uuid": private_network.id}],
    )

    logger.info(f"Server {server_name} created, waiting for ACTIVE state...")
    server = conn.compute.wait_for_server(server)
    logger.success(f"Server is ACTIVE: {server.name}")

    # Create/assign floating IP
    floating_ip = create_floating_ip(server, public_network.id)
    if floating_ip:
        logger.success(f"Server {server.name} ready with IP: {floating_ip.floating_ip_address}")
        return server, floating_ip.floating_ip_address
    else:
        return server, None


def create_floating_ip(server, public_network_id):
    """
    Create or attach a floating IP to the server.
    """
    logger.info(f"Checking available floating IPs for {server.name}")

    floating_ips = list(conn.network.ips(status="DOWN"))

    if floating_ips:
        floating_ip = floating_ips[0]
        logger.info(f"Reusing floating IP: {floating_ip.floating_ip_address}")
    else:
        logger.warning("No available floating IPs, creating a new one...")
        floating_ip = conn.network.create_ip(floating_network_id=public_network_id)
        logger.info(f"Created new floating IP: {floating_ip.floating_ip_address}")

    ports = list(conn.network.ports(device_id=server.id))

    if not ports:
        logger.error(f"No ports found for server {server.name}")
        return None

    conn.network.update_ip(floating_ip, port_id=ports[0].id)
    logger.success(f"Attached Floating IP {floating_ip.floating_ip_address} to {server.name}")

    return floating_ip