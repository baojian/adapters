FROM {docker_binary_image} AS docker-binaries
FROM dcp-eval/cpmpy_python:v1
COPY --from=docker-binaries /usr/local/bin/docker /usr/local/bin/dockerd /usr/local/bin/containerd /usr/local/bin/containerd-shim-runc-v2 /usr/local/bin/ctr /usr/local/bin/runc /usr/local/bin/docker-proxy /usr/local/bin/dind /usr/local/bin/
ENTRYPOINT []
COPY . /tests/
WORKDIR /tests/native
CMD ["sleep", "infinity"]
