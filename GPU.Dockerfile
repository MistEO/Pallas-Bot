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
    apt-get install -y --no-install-recommends ffmpeg portaudio19-dev python3-all-dev && \
    rm -rf /var/lib/apt/lists/*

RUN wget http://nz2.archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.19_amd64.deb && \
    dpkg -i libssl1.1_1.1.1f-1ubuntu2.19_amd64.deb && \
    rm libssl1.1_1.1.1f-1ubuntu2.19_amd64.deb

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
    pip install --no-cache-dir torch==1.13.1 torchvision==0.14.1 torchaudio==0.13.1 --extra-index-url https://download.pytorch.org/whl/cu117

RUN pip install --no-cache-dir paddlepaddle_gpu==2.5.1.post117 -f https://www.paddlepaddle.org.cn/whl/linux/cudnnin/stable.html && \
    pip install --no-cache-dir tokenizers rwkv paddlespeech==1.4.1 numpy==1.22.4 typeguard==2.13.3

COPY ./ /app/