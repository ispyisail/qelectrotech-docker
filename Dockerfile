# ─────────────────────────────────────────────
# Stage 1: Build
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core build tools
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    # Qt5 development libraries
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    # KDE Frameworks (required by QElectroTech)
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    # SQLite (required at build time)
    libsqlite3-dev \
    # Helpful for debugging the build
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Clone with submodules (pugixml, SingleApplication, KDE addons are fetched by CMake)
RUN git clone --recursive --depth=1 \
    https://github.com/qelectrotech/qelectrotech-source-mirror.git .

# Configure — Release build by default; swap to Debug for gdb/valgrind
ARG BUILD_TYPE=Release
RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=${BUILD_TYPE} \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

# Parallel build (use all available cores)
RUN cmake --build build --parallel $(nproc)

RUN cmake --install build

# ─────────────────────────────────────────────
# Stage 2: Test runner (inherits full build tree)
# ─────────────────────────────────────────────
FROM builder AS test

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Virtual framebuffer — Qt tests need a display even headless
    xvfb \
    libqt5sql5-sqlite \
    libqt5printsupport5 \
    libqt5concurrent5 \
    libx11-6 \
    libxcb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# xvfb-run gives Qt a virtual display; --auto-servernum avoids port clashes
CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1920x1080x24", \
     "ctest", "--test-dir", "build", "--output-on-failure", "--parallel", "4"]

# ─────────────────────────────────────────────
# Stage 3: Runtime
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Qt5 runtime
    libqt5core5a \
    libqt5gui5 \
    libqt5widgets5 \
    libqt5svg5 \
    libqt5xml5 \
    libqt5sql5 \
    libqt5sql5-sqlite \
    libqt5dbus5 \
    libqt5printsupport5 \
    libqt5concurrent5 \
    qt5-gtk-platformtheme \
    # KDE runtime libs
    libkf5coreaddons5 \
    libkf5widgetsaddons5 \
    # SQLite runtime
    libsqlite3-0 \
    # X11/XCB libs for Qt platform plugin
    libx11-6 \
    libxcb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libxext6 \
    libxrender1 \
    # Fonts so the UI renders properly
    fonts-dejavu-core \
    # Useful for troubleshooting inside the container
    strace \
    && rm -rf /var/lib/apt/lists/*

# Copy built binary + installed data from builder
COPY --from=builder /usr/local /usr/local

# Non-root user — running GUI apps as root inside containers is bad practice
RUN useradd -m -u 1000 qet
USER qet
WORKDIR /home/qet

# QET looks for its element/titleblock libraries here
ENV XDG_DATA_DIRS=/usr/local/share:/usr/share

CMD ["qelectrotech"]
