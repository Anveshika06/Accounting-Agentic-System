FROM python:3.11-slim
WORKDIR /app
COPY src/ src/
COPY data/ data/
COPY requirements.txt run.yaml ./
RUN mkdir -p artifacts && adduser --disabled-password --gecos '' runner && chown -R runner:runner /app
USER runner
ENV PYTHONUNBUFFERED=1
CMD ["python", "src/app.py", "demo"]
