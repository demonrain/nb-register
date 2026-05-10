FROM docker.m.daocloud.io/library/python:3.12-slim-bookworm

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY proto/email.proto /app/proto/email.proto
RUN python -m grpc_tools.protoc -I /app/proto --python_out=/app --grpc_python_out=/app /app/proto/email.proto
COPY email_service.py /app/email_service.py

EXPOSE 50051

ENTRYPOINT ["python", "/app/email_service.py"]
