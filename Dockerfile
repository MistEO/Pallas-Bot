FROM namiya233/go-cqhttp

FROM python:3.8

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

VOLUME /home/moles
ADD / /
CMD ["python","bot.py"]
