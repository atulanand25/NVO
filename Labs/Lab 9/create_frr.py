import json
import os

import docker
from loguru import logger


docker_client = docker.from_env()
logger.add("frr_lab.log", rotation="500 KB", level="INFO")


def load_config(config_file="topology.json"):
    with open(config_file) as f:
        config = json.load(f)
    logger.info("Loaded deployment configuration")
    return config


def ensure_network(name, subnet, gateway):
    """
    Ensure Docker network exists for this router.
    """
    try:
        docker_client.networks.get(name)
        logger.info(f"Network '{name}' already exists")
    except docker.errors.NotFound:
        logger.info(f"Creating Docker network '{name}'")
        docker_client.networks.create(
            name=name,
            driver="bridge",
            ipam=docker.types.IPAMConfig(
                pool_configs=[
                    docker.types.IPAMPool(
                        subnet=subnet,
                        gateway=gateway
                    )
                ]
            )
        )
        logger.success(f"Created network '{name}'")


def run_router(router_cfg, network_name):
    name = router_cfg["name"]
    ip = router_cfg["ip"]
    config_path = router_cfg["config_path"]
    subnet = router_cfg["subnet"]
    gateway = router_cfg["gateway"]

    ensure_network(network_name, subnet, gateway)

    # Remove existing container
    try:
        existing = docker_client.containers.get(name)
        existing.remove(force=True)
    except docker.errors.NotFound:
        pass

    abs_config_path = os.path.abspath(config_path)
    if not os.path.isdir(abs_config_path):
        raise FileNotFoundError(f"FRR config dir {abs_config_path} missing!")

    # Pull image
    # docker_client.images.pull("frrouting/frr:latest")

    # Use low-level API to assign fixed IP
    networking_config = docker_client.api.create_networking_config({
        network_name: docker_client.api.create_endpoint_config(ipv4_address=ip)
    })
    host_config = docker_client.api.create_host_config(
        privileged=True,
        binds={abs_config_path: {"bind": "/etc/frr", "mode": "rw"}}
    )

    # Create container
    container_info = docker_client.api.create_container(
        image="frrouting/frr:latest",
        name=name,
        tty=True,
        stdin_open=True,
        host_config=host_config,
        networking_config=networking_config
    )
    docker_client.api.start(container_info.get("Id"))
    container = docker_client.containers.get(container_info.get("Id"))

    # Start daemons explicitly
    container.exec_run("rm -f /var/run/frr/*.pid /var/run/frr/zserv.api")
    container.exec_run("/usr/lib/frr/zebra -d")
    container.exec_run("/usr/lib/frr/bgpd -d")

    # Optional: run VTYSH commands if needed
    logger.success(f"Router '{name}' running at {ip}")
    return container


# ---- MAIN ----
if __name__ == "__main__":
    config = load_config()
    network_name = config["network"]["name"]
    router = config.get("routers")
    run_router(router, network_name)

    logger.success("FRR deployment completed successfully")