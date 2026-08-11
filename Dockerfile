# ========== 构建阶段 ==========
FROM python:3.10-slim-bookworm AS builder

WORKDIR /build

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    rm -rf /root/.cache/pip

# ========== 运行阶段 ==========
FROM python:3.10-slim-bookworm

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY conf/*.yml ./conf/
COPY api.py ./
COPY worker.py ./
COPY app ./app
COPY templates ./templates
COPY static ./static

RUN mkdir -p log data conf

EXPOSE 5001

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5001", "api:app"]
