# === STAGE 1: Builder Basis ===
FROM alpine:latest AS builder
RUN apk add --no-cache git make cmake g++ libusb-dev libpulse-dev qt6-qtbase-dev

# === STAGE 2: RTL-SDR bauen ===
FROM builder AS rtl_fm_build
RUN git clone --depth 1 https://gitea.osmocom.org/sdr/rtl-sdr.git /opt/rtl_sdr
WORKDIR /opt/rtl_sdr/build
RUN cmake -DINSTALL_UDEV_RULES=ON .. && make -j$(nproc) && make install

# === STAGE 3: Multimon-NG bauen ===
FROM builder AS multimon_build
RUN git clone --depth 1 https://github.com/EliasOenal/multimon-ng.git /opt/multimon
WORKDIR /opt/multimon/build
RUN cmake .. && make -j$(nproc) && make install

# === STAGE 4: Gemeinsame Python-Basis ===
# Hier installieren wir die Requirements einmal für beide
FROM python:3.11-alpine AS python-base
WORKDIR /opt/boswatch
RUN apk add --no-cache libusb libpulse sox
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt
# Den Code kopieren wir jetzt erst hier rein
COPY . .

# === STAGE 5: Finaler Client ===
FROM python-base AS client
LABEL org.opencontainers.image.authors="info@schroll-it.de"
# Binaries vom Builder rüberholen
COPY --from=rtl_fm_build /usr/local/bin/rtl_* /usr/local/bin/
COPY --from=rtl_fm_build /usr/local/lib/librtlsdr.so* /usr/local/lib/
COPY --from=multimon_build /usr/local/bin/multimon-ng /usr/local/bin/

# Verlinkung der Libraries aktualisieren
RUN ldconfig /usr/local/lib || true

ENTRYPOINT ["python3", "bw_client.py"]
# Standard-Argument, falls nichts in docker-compose steht:
CMD ["-c", "config/client.yaml"]

# === STAGE 6: Finaler Server ===
FROM python-base AS server
LABEL org.opencontainers.image.authors="info@schroll-it.de"
EXPOSE 8080
ENTRYPOINT ["python3", "bw_server.py"]
CMD ["-c", "config/server.yaml"]