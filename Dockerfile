FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
RUN useradd -m app && mkdir /data && chown app /data
USER app
ENV LP_DB=/data/learner.db
VOLUME /data
CMD ["python", "http_server.py"]
