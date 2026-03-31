FROM debian:latest
LABEL authors="atan8167"

RUN apt-get update && \
    apt-get install -y iputils-ping iproute2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

CMD ["bash"]