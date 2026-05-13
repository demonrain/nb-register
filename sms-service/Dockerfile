FROM docker.m.daocloud.io/library/python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple grpcio grpcio-tools
COPY *.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 50051
CMD ["python3", "sms_server.py"]
