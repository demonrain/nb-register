FROM docker.m.daocloud.io/library/node:22-bookworm-slim AS web-builder

WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web .
RUN npm run build

FROM docker.m.daocloud.io/library/golang:1.26-alpine AS go-builder

WORKDIR /app
ENV GOPROXY=https://goproxy.cn,direct
ENV PATH=/root/go/bin:$PATH
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories \
    && apk add --no-cache git protobuf-dev \
    && go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.11 \
    && go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
COPY --from=web-builder /web/dist ./web/dist
RUN mkdir -p pb \
    && protoc -I proto --go_out=pb --go-grpc_out=pb proto/*.proto
RUN go build -o dashboard .

FROM docker.m.daocloud.io/library/alpine:latest

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories \
    && apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=go-builder /app/dashboard .
COPY --from=go-builder /app/web/dist ./web/dist

EXPOSE 8080
CMD ["./dashboard"]
