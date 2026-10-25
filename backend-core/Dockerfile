FROM debian:bookworm-slim AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ cmake make libcurl4-openssl-dev ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt ./
COPY include include
COPY src src
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DSTORY_TESTS=OFF \
 && cmake --build build -j"$(nproc)" --target storyteller

FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libcurl4 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/build/storyteller /app/storyteller
COPY config /app/config
ENV STORY_CONFIG_DIR=/app/config PORT=10000
EXPOSE 10000
USER nobody
CMD ["/app/storyteller", "serve"]
