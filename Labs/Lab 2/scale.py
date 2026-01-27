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
CPU_LIMIT = 10          # %
CHECK_INTERVAL = 5     # seconds

SSH_USER = "cirros"
SSH_PASS = "gocubsgo"
SSH_PORT = 22

CSV_FILE = "instance_access.csv"
# =========================
# OPENSTACK CONNECTION
# =========================

logger.info("Connecting to OpenStack")
conn = openstack.connect()

def fetch_cpu_usage(ip, user, password):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, SSH_PORT, user, password, timeout=5)

        stdin, stdout, stderr = ssh.exec_command("top -bn1 | grep '^CPU:'")
        output = stdout.read().decode()
        logger.debug(output)
        ssh.close()

        match = re.search(r"(\d+)% idle", output)
        if match:
            idle = float(match.group(1))
            cpu = 100 - idle
            logger.info(f"CPU usage from {ip}: {cpu:.2f}%")
            return cpu

        logger.warning(f"Could not parse CPU usage from {ip}")
        return 0

    except Exception as e:
        logger.error(f"SSH failed for {ip}: {e}")
        return 0


def load_instances():
    instances = []
    with open(CSV_FILE, "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            instances.append(row)

    logger.info(f"Loaded {len(instances)} instances from CSV")
    return instances


def save_instance(name, ip):
    file_exists = False

    try:
        with open(CSV_FILE, "r"):
            file_exists = True
    except FileNotFoundError:
        pass

    with open(CSV_FILE, "a+", newline="") as file:
        file.seek(0, 2)  # go to end of file

        # 🔑 FORCE newline if file is not empty
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

    logger.info(f"Saved instance {name} ({ip}) to CSV")


def create_instance(index):
    logger.warning("Creating new OpenStack instance")

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
    logger.info(f"Instance {name} created")

    floating_ip = conn.network.create_ip(
        floating_network_id=public_net.id
    )

    port = list(conn.network.ports(device_id=server.id))[0]
    conn.network.update_ip(floating_ip, port_id=port.id)

    logger.info(f"Floating IP {floating_ip.floating_ip_address} attached to {name}")

    return name, floating_ip.floating_ip_address

def monitor_and_scale():
    instance_count = 0
    last_check = time.time()

    logger.info("Starting monitoring and auto-scaling loop")

    while instance_count < MAX_INSTANCES:
        instances = load_instances()
        high_cpu_detected = False

        for inst in instances:
            cpu = fetch_cpu_usage(
                inst["ip"],
                inst["username"],
                inst["password"]
            )

            logger.info(
                f"Instance {inst['name']} ({inst['ip']}) CPU usage: {cpu:.2f}%"
            )

            if cpu > CPU_LIMIT:
                high_cpu_detected = True
                logger.warning(
                    f"CPU threshold exceeded on {inst['name']} ({cpu:.2f}%)"
                )

        if time.time() - last_check >= CHECK_INTERVAL:
            if high_cpu_detected:
                instance_count += 1
                logger.warning("Scaling triggered — launching new instance")

                name, ip = create_instance(instance_count)
                save_instance(name, ip)
            else:
                logger.info("CPU usage normal — no scaling action")

            last_check = time.time()

        time.sleep(5)


if __name__ == "__main__":
    monitor_and_scale()
