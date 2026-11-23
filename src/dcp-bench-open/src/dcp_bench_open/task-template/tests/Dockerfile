FROM {docker_binary_image} AS docker-binaries
FROM dcp-eval/cpmpy_python:v1
COPY --from=docker-binaries /usr/local/bin/docker /usr/local/bin/dockerd /usr/local/bin/containerd /usr/local/bin/containerd-shim-runc-v2 /usr/local/bin/ctr /usr/local/bin/runc /usr/local/bin/docker-proxy /usr/local/bin/dind /usr/local/bin/
ENTRYPOINT []
COPY solver-image.tar /tests/solver-image.tar
COPY native/ /tests/native/
COPY test.sh grade.py check_archive.py case.json /tests/
WORKDIR /tests/native
CMD ["sleep", "infinity"]
