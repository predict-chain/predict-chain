ARG base_img=ubuntu:22.04

FROM $base_img

ARG base_img=ubuntu:22.04

RUN echo "Building container from '$base_img'... "

WORKDIR /usr/src/app

COPY . .

RUN apt-get update && apt-get install -y python3.10 python3-pip nodejs npm && rm -rf /var/lib/apt/lists/*

RUN python3 --version && pip3 --version && node --version && npm --version

RUN pip install -r requirements.txt
