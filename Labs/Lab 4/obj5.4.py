import os
import sys
import time

import boto3
from dotenv import load_dotenv
from loguru import logger

from get_metrics import get_cpu_util

# Load env vars
load_dotenv()

# Loguru config
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>"
)

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", 10))
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", 10))

AMI_ID = os.getenv("EC2_AMI_ID")
INSTANCE_TYPE = os.getenv("EC2_INSTANCE_TYPE", "t3.micro")
KEY_NAME = os.getenv("EC2_KEY_NAME")
BASE_NAME = os.getenv("EC2_BASE_NAME", "cpu-auto")

SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")


def get_aws_session():
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")

    if access_key and secret_key:
        logger.info("Using AWS credentials from env")
        return boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )

    logger.info("Using AWS CLI / IAM role")
    return boto3.Session(region_name=region)


def get_two_running_instances(ec2):
    return list(
        ec2.instances.filter(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
    )[:2]


def send_alert(sns, message):
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject="EC2 CPU Threshold Breached",
        Message=message
    )
    logger.success("SNS alert sent")


def main():
    session = get_aws_session()
    ec2 = session.resource("ec2")
    sns = session.client("sns")

    while True:
        try:
            instances = get_two_running_instances(ec2)

            if len(instances) < 2:
                logger.warning("Less than two running instances found")
                time.sleep(MONITOR_INTERVAL)
                continue

            for inst in instances:
                cpu = get_cpu_util(inst.id)
                logger.info(f"Instance {inst.id} CPU: {cpu}%")

                if cpu >= CPU_THRESHOLD:
                    logger.warning(f"CPU threshold exceeded for {inst.id}")

                    # Stop instances
                    for i in instances:
                        i.stop()

                    for i in instances:
                        i.wait_until_stopped()

                    logger.success("Instances stopped")

                    # Create replacements
                    new_instances = ec2.create_instances(
                        ImageId=AMI_ID,
                        InstanceType=INSTANCE_TYPE,
                        KeyName=KEY_NAME,
                        MinCount=2,
                        MaxCount=2
                    )

                    for ni in new_instances:
                        ni.wait_until_running()
                        ni.create_tags(
                            Tags=[{"Key": "Name", "Value": f"{BASE_NAME}-{int(time.time())}"}]
                        )
                        logger.success(f"Replacement instance launched: {ni.id}")

                    send_alert(
                        sns,
                        f"CPU exceeded {CPU_THRESHOLD}%.\n"
                        f"Stopped instances {[i.id for i in instances]} "
                        f"and launched replacements {[n.id for n in new_instances]}."
                    )

                    return  # react once and exit

            time.sleep(MONITOR_INTERVAL)

        except Exception as e:
            logger.error(f"Monitoring error: {e}")
            time.sleep(MONITOR_INTERVAL)


if __name__ == "__main__":
    main()
