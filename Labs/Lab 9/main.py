import create_vm
import create_vn
import create_security_groups
import controller
import create_frr

from loguru import logger

# Setup logging
logger.add("nvo.log", rotation="1 MB", level="INFO")


def menu():
    print("\n" + "═"*50)
    print("🚀  NVO AUTOMATION LAB9 FRAMEWORK")
    print("═"*50)
    print(" [1] Create Virtual Network")
    print(" [2] Add Virtual Machine")
    print(" [3] Configure Security Groups")
    print(" [4] Deploy FRR BGP Containers")
    print(" [5] Deploy RYU Controllers")
    print(" [6] Exit")
    print("═"*50)


def main():
    while True:
        menu()
        choice = input("Enter your choice: ").strip()
        logger.info(f"User selected option: {choice}")

        if choice == "1":
            create_vn.create_virtual_network(topology_file="topology.json")

        # ---- VM ----
        elif choice == "2":
            server_name = input("Enter server name: ")
            logger.info(f"Creating VM: {server_name}")
            create_vm.create_server(server_name)

        # ---- SECURITY GROUP ----
        elif choice == "3":
            group_name = input("Enter security group: ")
            server_name = input("Enter server name: ")

            logger.info(f"Creating security group: {group_name}")
            sec_group = create_security_groups.get_or_create_security_group(group_name)

            create_security_groups.detach_security_group(
                server_name, "default"
            )

            while True:
                logger.info("=== Security Group Services ===")
                logger.info("1. SSH")
                logger.info("2. TCP")
                logger.info("3. UDP")
                logger.info("4. ICMP")
                logger.info("5. Exit")
                logger.info("================================")

                sub_choice = input("Enter your choice: ").strip()

                if sub_choice == "1":
                    logger.info("Allowing SSH")
                    create_security_groups.add_ssh_rule(sec_group, server_name)

                elif sub_choice == "2":
                    logger.info("Allowing TCP")
                    create_security_groups.add_tcp_rule(sec_group, server_name)

                elif sub_choice == "3":
                    logger.info("Allowing UDP")
                    create_security_groups.add_udp_rule(sec_group, server_name)

                elif sub_choice == "4":
                    logger.info("Allowing ICMP")
                    create_security_groups.add_icmp_rule(sec_group, server_name)

                elif sub_choice == "5":
                    break
                else:
                    logger.warning("Invalid security group option")

        # ---- FRR DEPLOYMENT ----
        elif choice == "4":
            logger.info("Starting FRR deployment using deployment.json")
            try:
                config = create_frr.load_config()
                network_name = config["network"]["name"]
                router = config.get("routers")
                logger.info(f"Starting FRR deployment using topology.json - network: {network_name} router: {router}")
                create_frr.run_router(router, network_name)
                logger.success("FRR deployment completed")
            except Exception as e:
                logger.error(f"FRR deployment failed: {e}")
        elif choice == "5":
            logger.info("Starting RYU deployment using topology.json")

            try:
                config = controller.load_config()
                network_name = config["network"]["name"]
                router = config.get("controllers")
                controller.run_ryu_controller(router, network_name)
                logger.success("RYU deployment completed")

            except Exception as e:
                logger.error(f"RYU deployment failed: {e}")

        elif choice == "6":
            logger.info("Exiting NVO framework")
            break

        else:
            logger.warning("Invalid choice, try again")


if __name__ == "__main__":
    main()