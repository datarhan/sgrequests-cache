FROM python:3.12-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps for lxml etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libxml2-dev libxslt1-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-tests.txt /app/requirements-tests.txt
RUN pip install --upgrade pip && pip install -r requirements-tests.txt

COPY . /app
RUN chmod +x scripts/run_tests.sh || true

CMD ["bash"]

