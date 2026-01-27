#!/usr/bin/env python3

import paramiko
import openstack
import csv
import time
import re
from loguru import logger

# =========================
# CONFIGURATION
# =========================

IMAGE_NAME = "cirros-0.6.3-x86_64-disk"
FLAVOR_NAME = "m1.nano"
PRIVATE_NET = "lab2"
PUBLIC_NET = "public"

INSTANCE_PREFIX = "auto_vm_"
MAX_INSTANCES = 4
CPU_THRESHOLD = 10       # %
POLL_INTERVAL = 5        # seconds

SSH_USER = "cirros"
SSH_PASS = "gocubsgo"
SSH_PORT = 22

CSV_FILE = "instance_access.csv"

# =========================
# OPENSTACK CONNECTION
# =========================

logger.info("Initializing OpenStack connection")
conn = openstack.connect()

# =========================
# METRICS COLLECTION
# =========================

def get_remote_cpu_percent(ip, username, password):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, SSH_PORT, username, password, timeout=5)

        _, stdout, _ = ssh.exec_command("top -bn1 | grep '^CPU:'")
        output = stdout.read().decode()
        ssh.close()

        match = re.search(r"(\d+)% idle", output)
        if not match:
            logger.warning(f"CPU parse failed for {ip}")
            return 0.0

        idle = float(match.group(1))
        cpu = 100.0 - idle

        logger.info(f"CPU usage from {ip}: {cpu:.2f}%")
        return cpu

    except Exception as exc:
        logger.error(f"SSH error on {ip}: {exc}")
        return 0.0

# =========================
# INSTANCE REGISTRY (CSV)
# =========================

def read_instance_registry():
    instances = []

    try:
        with open(CSV_FILE, "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                instances.append(row)
    except FileNotFoundError:
        logger.warning("Instance registry not found — starting fresh")

    logger.info(f"Loaded {len(instances)} registered instances")
    return instances


def append_instance_registry(name, ip):
    file_exists = False

    try:
        with open(CSV_FILE, "r"):
            file_exists = True
    except FileNotFoundError:
        pass

    with open(CSV_FILE, "a+", newline="") as file:
        file.seek(0, 2)
        if file.tell() > 0:
            file.write("\n")

        writer = csv.DictWriter(
            file,
            fieldnames=["name", "ip", "username", "password"]
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "name": name,
            "ip": ip,
            "username": SSH_USER,
            "password": SSH_PASS
        })

    logger.info(f"Registered new instance {name} ({ip})")

# =========================
# OPENSTACK PROVISIONING
# =========================

def provision_instance(index):
    logger.warning("Provisioning new OpenStack instance")

    image = conn.image.find_image(IMAGE_NAME)
    flavor = conn.compute.find_flavor(FLAVOR_NAME)
    private_net = conn.network.find_network(PRIVATE_NET)
    public_net = conn.network.find_network(PUBLIC_NET)

    name = f"{INSTANCE_PREFIX}{index}"

    server = conn.compute.create_server(
        name=name,
        image_id=image.id,
        flavor_id=flavor.id,
        networks=[{"uuid": private_net.id}]
    )

    server = conn.compute.wait_for_server(server)
    logger.info(f"Instance {name} is ACTIVE")

    floating_ip = conn.network.create_ip(
        floating_network_id=public_net.id
    )

    port = list(conn.network.ports(device_id=server.id))[0]
    conn.network.update_ip(floating_ip, port_id=port.id)

    logger.info(
        f"Assigned floating IP {floating_ip.floating_ip_address} to {name}"
    )

    return name, floating_ip.floating_ip_address

# =========================
# AUTOSCALER CORE
# =========================

def autoscale_controller():
    logger.info("Starting autoscaling controller")

    last_scale_time = 0

    while True:
        instances = read_instance_registry()
        instance_count = len(instances)

        if instance_count >= MAX_INSTANCES:
            logger.warning("Maximum instance limit reached")
            time.sleep(POLL_INTERVAL)
            continue

        scale_required = False

        for inst in instances:
            cpu = get_remote_cpu_percent(
                inst["ip"],
                inst["username"],
                inst["password"]
            )

            logger.info(
                f"{inst['name']} ({inst['ip']}) CPU: {cpu:.2f}%"
            )

            if cpu > CPU_THRESHOLD:
                logger.warning(
                    f"CPU threshold exceeded on {inst['name']}"
                )
                scale_required = True
                break

        # Cooldown: avoid scaling on every poll
        if scale_required and time.time() - last_scale_time >= POLL_INTERVAL:
            new_index = instance_count + 1
            logger.warning("Autoscale event triggered")

            name, ip = provision_instance(new_index)
            append_instance_registry(name, ip)

            last_scale_time = time.time()
        else:
            logger.info("System stable — no scaling action")

        time.sleep(POLL_INTERVAL)

# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    autoscale_controller()
