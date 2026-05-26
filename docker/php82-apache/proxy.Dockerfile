FROM alpine

RUN apk add --no-cache socat

WORKDIR /proxy