FROM python:3.9 as requirements-stage

WORKDIR /tmp

COPY ./pyproject.toml ./poetry.lock* /tmp/

RUN curl -sSL https://install.python-poetry.org -o install-poetry.py

RUN python install-poetry.py --yes

ENV PATH="${PATH}:/root/.local/bin"

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

FROM tiangolo/uvicorn-gunicorn-fastapi:python3.9

WORKDIR /app

RUN apt-get update && \
    apt-get install -y ffmpeg portaudio19-dev python3-all-dev && \
    rm -rf /var/lib/apt/lists/*

ADD https://github.com/ufoscout/docker-compose-wait/releases/download/2.9.0/wait /app/wait

RUN chmod +x /app/wait && \
    echo "./wait" >> /app/prestart.sh

COPY --from=requirements-stage /tmp/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r requirements.txt

RUN rm requirements.txt

COPY ./ /app/

WORKDIR /app

RUN git submodule update --init --recursive

RUN pip install --no-cache-dir --upgrade -r src/plugins/sing/requirements.txt && \
    pip install --no-cache-dir torch==1.11.0 torchvision==0.12.0 torchaudio==0.11.0

RUN pip install --no-cache-dir paddlepaddle==2.4.2 paddlespeech==1.3.0 && \
    pip install --no-cache-dir tokenizers rwkv numpy==1.23.5 typeguard==2.13.3

COPY ./ /app/