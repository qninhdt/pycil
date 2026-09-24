# PostgreSQL with the pinned WAL-G binary for base backups and WAL archiving.
#
# Debian rather than Alpine on purpose. WAL-G ships glibc builds, and running one
# against musl needs `libc6-compat` — a shim in front of the one component whose
# failure mode is "the backup silently did not happen". The image is a little
# larger; a database image is the wrong place to save it.
FROM postgres:16-bookworm

# Pinned, and verified at build time. An unpinned `latest` would mean two hosts
# could archive with different binaries, and a restore is the moment that
# difference would surface.
ARG WAL_G_VERSION=v3.0.9
ARG WAL_G_SHA256=4f03ee4679db7f660bfd1b2b8291ac5df247cd2ec48074b60c112f4897299f24

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL -o /tmp/wal-g.tar.gz \
      "https://github.com/wal-g/wal-g/releases/download/${WAL_G_VERSION}/wal-g-pg-22.04-amd64.tar.gz" \
 && echo "${WAL_G_SHA256}  /tmp/wal-g.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/wal-g.tar.gz -C /usr/local/bin \
 && mv /usr/local/bin/wal-g-pg-22.04-amd64 /usr/local/bin/wal-g \
 && chmod +x /usr/local/bin/wal-g \
 && rm -f /tmp/wal-g.tar.gz \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY entrypoint-walg.sh /usr/local/bin/entrypoint-walg.sh
RUN chmod +x /usr/local/bin/entrypoint-walg.sh

# The stock PostgreSQL entrypoint still does the real work; this only refuses to
# start a cluster whose archiving is misconfigured, because a cluster that starts
# and then fails to archive looks healthy until the restore is needed.
#
# Archive settings are passed as `-c` flags by the compose file rather than
# mounted as a `config_file`. Pointing `config_file` at a file of our own replaces
# the generated postgresql.conf instead of extending it, which drops
# `listen_addresses = '*'` and leaves the container unreachable from the host.
ENTRYPOINT ["/usr/local/bin/entrypoint-walg.sh"]
CMD ["postgres"]
