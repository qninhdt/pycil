# syntax=docker/dockerfile:1
FROM postgres:18.6-trixie@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336

# The verified upstream WAL-G artifact is amd64; reject other architectures.
RUN test "$(dpkg --print-architecture)" = amd64 \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates jq \
    && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:4f03ee4679db7f660bfd1b2b8291ac5df247cd2ec48074b60c112f4897299f24 \
    https://github.com/wal-g/wal-g/releases/download/v3.0.9/wal-g-pg-22.04-amd64.tar.gz /tmp/wal-g.tar.gz
RUN tar -xzf /tmp/wal-g.tar.gz -C /usr/local/bin \
    && mv /usr/local/bin/wal-g-pg-22.04-amd64 /usr/local/bin/wal-g \
    && chmod 755 /usr/local/bin/wal-g \
    && rm /tmp/wal-g.tar.gz \
    && wal-g --version \
    && ! ldd /usr/local/bin/wal-g 2>&1 | grep 'not found'
COPY --chmod=0755 backup.sh /usr/local/bin/pycil-backup
