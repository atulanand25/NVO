import openstack
from loguru import logger

# Initialize OpenStack connection
conn = openstack.connect(cloud="openstack")

# Configure logging
logger.add("security.log", rotation="1 MB", level="INFO")


def get_or_create_security_group(name: str):
    """
    Retrieve an existing security group by name, or create it if it doesn't exist.

    Args:
        name (str): Name of the security group.

    Returns:
        SecurityGroup: The OpenStack security group object.
    """
    sg = conn.network.find_security_group(name)
    if sg:
        logger.info(f"Using existing security group: {name}")
        return sg

    sg = conn.network.create_security_group(
        name=name,
        description="Allow all intra- and inter-VN traffic"
    )
    logger.info(f"Created new security group: {name}")
    return sg


def detach_security_group(server_name: str, sg_name: str):
    """
    Remove a security group from a given server using the OpenStack REST API.

    Args:
        server_name (str): Name of the server.
        sg_name (str): Name of the security group to remove.
    """
    server = conn.compute.find_server(server_name)
    if not server:
        logger.info(f"Server '{server_name}' not found.")
        return

    server = conn.compute.get_server(server.id)
    current_sgs = [sg['name'] for sg in server.security_groups]
    logger.info(f"Security groups currently attached to {server_name}: {current_sgs}")

    if sg_name not in current_sgs:
        logger.info(f"Security group '{sg_name}' not attached to server '{server_name}', skipping removal.")
        return

    session = conn.session
    endpoint = conn.compute.get_endpoint()
    url = f"{endpoint}/servers/{server.id}/action"
    payload = {"removeSecurityGroup": {"name": sg_name}}

    response = session.post(url, json=payload)
    if response.status_code == 202:
        logger.info(f"Successfully removed '{sg_name}' from server '{server_name}'")
    else:
        logger.warning(f"Failed to remove '{sg_name}': {response.status_code}, {response.text}")


def rule_exists(sg, protocol, port_min=None, port_max=None, remote_prefix=None):
    """
    Check if a security group rule already exists.

    Args:
        sg: Security group object.
        protocol (str): Protocol ("tcp", "udp", "icmp").
        port_min (int, optional): Minimum port number (for TCP/UDP).
        port_max (int, optional): Maximum port number (for TCP/UDP).
        remote_prefix (str, optional): Remote IP prefix.

    Returns:
        bool: True if the rule exists, False otherwise.
    """
    for rule in conn.network.security_group_rules(security_group_id=sg.id):
        if (rule.direction == "ingress" and
            rule.protocol == protocol and
            (port_min is None or rule.port_range_min == port_min) and
            (port_max is None or rule.port_range_max == port_max) and
            (remote_prefix is None or rule.remote_ip_prefix == remote_prefix)):
            return True
    return False


def attach_sg_if_not_attached(sg, server_name: str):
    """
    Attach a security group to a server if it is not already attached.

    Args:
        sg: Security group object.
        server_name (str): Name of the server.
    """
    server = conn.compute.find_server(server_name)
    if not server:
        logger.warning(f"Server '{server_name}' not found for attachment.")
        return

    server = conn.compute.get_server(server.id)
    current_sgs = [s['name'] for s in server.security_groups]

    if sg.name in current_sgs:
        logger.info(f"Security group '{sg.name}' already attached to server '{server_name}'.")
        return

    conn.compute.add_security_group_to_server(server, sg.name)
    logger.info(f"Security group '{sg.name}' attached to server '{server_name}'.")


def add_icmp_rule(sg, server_name: str):
    """Add an ICMP ingress rule safely."""
    if not rule_exists(sg, protocol="icmp"):
        conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="icmp",
            ethertype="IPv4"
        )
        logger.info(f"ICMP rule added to security group: {sg.name}")
    else:
        logger.info(f"ICMP rule already exists in security group: {sg.name}")

    attach_sg_if_not_attached(sg, server_name)


def add_ssh_rule(sg, server_name: str):
    """Add an SSH ingress rule safely."""
    if not rule_exists(sg, protocol="tcp", port_min=22, port_max=22):
        conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=22,
            port_range_max=22,
            ethertype="IPv4"
        )
        logger.info(f"SSH rule added to security group: {sg.name}")
    else:
        logger.info(f"SSH rule already exists in security group: {sg.name}")

    attach_sg_if_not_attached(sg, server_name)


def add_tcp_rule(sg, server_name: str, remote_prefix="0.0.0.0/0"):
    """Add a TCP ingress rule (all ports) safely."""
    if not rule_exists(sg, protocol="tcp", port_min=1, port_max=65535, remote_prefix=remote_prefix):
        conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="tcp",
            port_range_min=1,
            port_range_max=65535,
            remote_ip_prefix=remote_prefix,
            ethertype="IPv4"
        )
        logger.info(f"TCP rule added to security group: {sg.name}")
    else:
        logger.info(f"TCP rule already exists in security group: {sg.name}")

    attach_sg_if_not_attached(sg, server_name)


def add_udp_rule(sg, server_name: str, remote_prefix="0.0.0.0/0"):
    """Add a UDP ingress rule (all ports) safely."""
    if not rule_exists(sg, protocol="udp", port_min=1, port_max=65535, remote_prefix=remote_prefix):
        conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction="ingress",
            protocol="udp",
            port_range_min=1,
            port_range_max=65535,
            remote_ip_prefix=remote_prefix,
            ethertype="IPv4"
        )
        logger.info(f"UDP rule added to security group: {sg.name}")
    else:
        logger.info(f"UDP rule already exists in security group: {sg.name}")

    attach_sg_if_not_attached(sg, server_name)