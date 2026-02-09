import os
import sys
import boto3
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Configure Loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
)

def get_ec2_resource():
    """
    If AWS creds are present in env, use boto3.Session explicitly.
    Otherwise, fall back to AWS CLI / IAM role.
    """
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")

    if aws_access_key and aws_secret_key:
        logger.info("Using AWS credentials from environment variables")
        session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region
        )
    else:
        logger.info("Using AWS CLI / IAM role authentication")
        session = boto3.Session(region_name=region)

    return session.resource("ec2")


def manage_ec2_resources():
    ec2_resource = get_ec2_resource()

    ami_id = os.getenv("EC2_AMI_ID")
    instance_type = os.getenv("EC2_INSTANCE_TYPE", "t2.micro")
    instance_count = int(os.getenv("EC2_INSTANCE_COUNT", 2))
    base_name = os.getenv("EC2_INSTANCE_NAME", "MyInstance")
    key_name = os.getenv("EC2_KEY_NAME")  # Must exist in your AWS account

    if not ami_id:
        raise ValueError("EC2_AMI_ID must be set in environment variables")
    if not key_name:
        raise ValueError("EC2_KEY_NAME must be set in environment variables")

    try:
        logger.info(f"Provisioning {instance_count} EC2 instances...")

        new_instances = ec2_resource.create_instances(
            ImageId=ami_id,
            MinCount=instance_count,
            MaxCount=instance_count,
            InstanceType=instance_type,
            KeyName=key_name
        )

        # Tag instances with Name
        for idx, inst in enumerate(new_instances, start=1):
            name_tag = f"{base_name}-{idx}"
            inst.create_tags(Tags=[{"Key": "Name", "Value": name_tag}])
            logger.success(f"Created Instance: {inst.id} with Name: {name_tag}")

        # Wait for all instances to reach 'running' state
        logger.info("Waiting for instances to reach 'running' state...")
        for inst in new_instances:
            inst.wait_until_running()
            inst.reload()  # refresh instance attributes
            logger.success(f"Instance {inst.id} ({[t['Value'] for t in inst.tags if t['Key']=='Name'][0]}) is now running.")

        # Stop second instance if it exists
        if len(new_instances) > 1:
            target_instance = new_instances[1]
            target_name = [t['Value'] for t in target_instance.tags if t['Key']=='Name'][0]

            logger.warning(f"Stopping instance: {target_instance.id} ({target_name})")
            target_instance.stop()
            logger.info("Waiting for instance to stop...")
            target_instance.wait_until_stopped()
            logger.success(f"Instance {target_instance.id} ({target_name}) stopped.")

        # Display instance details
        logger.info("Fetching instance status...")
        logger.success(f"\n{'INSTANCE ID':<25} {'NAME':<20} {'TYPE':<12} {'PRIVATE IP':<15} {'STATE':<12}")
        logger.success("-" * 80)

        for instance in ec2_resource.instances.all():
            tags = instance.tags or []
            name = next((t['Value'] for t in tags if t['Key'] == "Name"), "N/A")
            ip_addr = instance.private_ip_address or "N/A"
            status = instance.state["Name"]

            logger.success(
                f"{instance.id:<25} {name:<20} {instance.instance_type:<12} {ip_addr:<15} {status:<12}"
            )


    except Exception as e:
        logger.error(f"AWS operation failed: {e}")


if __name__ == "__main__":
    manage_ec2_resources()
