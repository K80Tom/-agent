FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip config set global.index-url "${PIP_INDEX_URL}"

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Runtime image includes the FastAPI service, static frontend, and runtime
# dependencies for Excel ingest plus single-image visual ingest.
# scripts/ and storyboard docs stay out of the build context via .dockerignore.
COPY app ./app
COPY docs ./docs
COPY frontend ./frontend
COPY README.md ./README.md

RUN mkdir -p runtime/uploads

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
