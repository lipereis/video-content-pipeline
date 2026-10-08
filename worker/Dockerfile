FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg && rm -rf /var/lib/apt/lists/*

# Metis does the content generation. Pinned so a change there cannot break this build.
ARG METIS_REF=ae7b4fc7ebaaab53f45fb75f14659658a5c1dd4f
RUN git clone https://github.com/lipereis/metis-content-strategist /opt/metis \
    && git -C /opt/metis checkout "$METIS_REF"
ENV METIS_PATH=/opt/metis

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
