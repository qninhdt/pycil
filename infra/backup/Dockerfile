FROM alpine:3.19

RUN apk add --no-cache postgresql16-client restic ca-certificates tzdata

COPY backup.sh /backup.sh
COPY restore.sh /restore.sh
RUN chmod +x /backup.sh /restore.sh

ENTRYPOINT ["/backup.sh"]
