import os
import sys
from datetime import datetime, timedelta, timezone

import boto3
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Configure Loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>"
)


def get_aws_session():
    """
    Create AWS session using env credentials if present,
    otherwise fall back to AWS CLI / IAM role.
    """
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")

    if aws_access_key and aws_secret_key:
        logger.info("Using AWS credentials from environment variables")
        return boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region
        )

    logger.info("Using AWS CLI / IAM role authentication")
    return boto3.Session(region_name=region)


def get_first_running_instance(ec2_resource):
    """
    Fetch the first running EC2 instance.
    """
    for instance in ec2_resource.instances.filter(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    ):
        return instance

    raise RuntimeError("No running EC2 instances found")


def fetch_metric(cloudwatch, instance_id, metric_name, start_time, end_time):
    """
    Fetch average CloudWatch metric value.
    """
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName=metric_name,
        Dimensions=[
            {"Name": "InstanceId", "Value": instance_id}
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=300,  # 5 minutes
        Statistics=["Average"]
    )

    datapoints = response.get("Datapoints", [])
    if not datapoints:
        return "N/A"

    # Use the latest datapoint
    latest = max(datapoints, key=lambda x: x["Timestamp"])
    return round(latest["Average"], 2)


def get_cpu_util(instance_id):
    """
    Reusable helper to fetch CPU utilization for a single instance
    over the last 5 minutes.
    """
    session = get_aws_session()
    cloudwatch = session.client("cloudwatch")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=5)

    cpu = fetch_metric(
        cloudwatch,
        instance_id,
        "CPUUtilization",
        start_time,
        end_time
    )

    return cpu if cpu != "N/A" else 0.0



def main():
    try:
        session = get_aws_session()

        ec2_resource = session.resource("ec2")
        cloudwatch = session.client("cloudwatch")

        instance = get_first_running_instance(ec2_resource)
        instance_id = instance.id

        logger.success(f"Found running instance: {instance_id}")

        # Time window: last 30 minutes
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=30)

        status_check = fetch_metric(
            cloudwatch, instance_id, "StatusCheckFailed", start_time, end_time
        )
        cpu_util = fetch_metric(
            cloudwatch, instance_id, "CPUUtilization", start_time, end_time
        )
        network_in = fetch_metric(
            cloudwatch, instance_id, "NetworkIn", start_time, end_time
        )
        network_out = fetch_metric(
            cloudwatch, instance_id, "NetworkOut", start_time, end_time
        )

        logger.success("\nCloudWatch Metrics Summary")
        logger.success("-" * 35)
        logger.success(f"Instance ID     : {instance_id}")
        logger.success(f"Status Check    : {status_check}")
        logger.success(f"CPU Utilization : {cpu_util} %")
        logger.success(f"Network In      : {network_in} Bytes")
        logger.success(f"Network Out     : {network_out} Bytes")

    except Exception as e:
        logger.error(f"Failed to fetch CloudWatch metrics: {e}")


if __name__ == "__main__":
    main()
