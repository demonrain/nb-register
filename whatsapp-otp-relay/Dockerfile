FROM docker.m.daocloud.io/library/golang:1.26-alpine AS builder

WORKDIR /app

ENV GOPROXY=https://goproxy.cn,direct
ENV PATH=/root/go/bin:$PATH

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories \
    && apk add --no-cache git protobuf-dev \
    && go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.11 \
    && go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1

COPY whatsapp-otp-relay/go.mod whatsapp-otp-relay/go.sum* ./
RUN go mod download

COPY proto ./proto
COPY whatsapp-otp-relay ./
RUN mkdir -p pb \
    && rm -f pb/*.pb.go pb/*_grpc.pb.go \
    && protoc -I proto --go_out=pb --go-grpc_out=pb proto/otp.proto
RUN go build -o whatsapp-otp-relay .

FROM docker.m.daocloud.io/library/alpine:latest

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories \
    && apk add --no-cache ca-certificates

WORKDIR /app
COPY --from=builder /app/whatsapp-otp-relay .

EXPOSE 50051 8081

CMD ["./whatsapp-otp-relay"]
