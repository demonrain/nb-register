FROM docker.m.daocloud.io/library/python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple "requests[socks]"
COPY *.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python3", "bot.py"]
