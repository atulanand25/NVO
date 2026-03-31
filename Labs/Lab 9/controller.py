import os

import docker
import json
from loguru import logger

client = docker.from_env()

logger.add("ryu.log", rotation="500 KB", level="INFO")


def load_config(config_file="topology.json"):
    with open(config_file) as f:
        config = json.load(f)
    logger.info("Loaded deployment config for controllers")
    return config


def run_ryu_controller(ctrl_cfg, network_name):
    name = ctrl_cfg["name"]

    try:
        client.containers.get(name).remove(force=True)
        logger.warning(f"Removed existing controller {name}")
    except docker.errors.NotFound:
        logger.info(f"No existing controller {name}")

    logger.info(f"Starting RYU controller: {name}")
    ryu_config_path = os.path.abspath("./configs/ryu")

    host_config = client.api.create_host_config(
        privileged=True,
        binds={ryu_config_path: {"bind": "/ryu-bgp", "mode": "rw"}}
    )

    # Use low-level API to assign fixed IP
    networking_config = client.api.create_networking_config({
        network_name: client.api.create_endpoint_config(ipv4_address=ctrl_cfg["ip"])
    })

    container = client.api.create_container(
        "osrg/ryu",
        name=name,
        command="tail -f /dev/null",
        working_dir="/ryu-bgp",
        host_config=host_config,
        networking_config=networking_config,
        detach=True,
        tty=True,
        stdin_open=True
    )
    client.api.start(container.get("Id"))
    os.system(f"docker exec -it {name} ryu-manager --verbose bgp_app.py")

    return container