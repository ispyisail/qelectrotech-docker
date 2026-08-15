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
# Stage 3: Debug (Debug build + GDB + Valgrind)
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS debug-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Same deps as builder but we rebuild with -DCMAKE_BUILD_TYPE=Debug
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive --depth=1 \
    https://github.com/qelectrotech/qelectrotech-source-mirror.git .

# Apply fix for thread-unsafe QStandardPaths (PR #514)
COPY qetapp.cpp.patch sources/qetapp.cpp
# Apply PR #515 fixes: MachineInfo uninit members, main-thread pre-init, m_first_show order
COPY machine_info.h    sources/machine_info.h
COPY main.cpp          sources/main.cpp
COPY qetdiagrameditor.h sources/qetdiagrameditor.h
# Apply PR #516 fixes: thread-safe setUpData(), inline const QString in qetinformation.h
COPY fileelementcollectionitem.h   sources/ElementsCollection/fileelementcollectionitem.h
COPY fileelementcollectionitem.cpp sources/ElementsCollection/fileelementcollectionitem.cpp
COPY xmlprojectelementcollectionitem.h   sources/ElementsCollection/xmlprojectelementcollectionitem.h
COPY xmlprojectelementcollectionitem.cpp sources/ElementsCollection/xmlprojectelementcollectionitem.cpp
COPY elementscollectionmodel.cpp   sources/ElementsCollection/elementscollectionmodel.cpp
COPY elementslocation.cpp          sources/ElementsCollection/elementslocation.cpp
COPY terminal.cpp                  sources/qetgraphicsitem/terminal.cpp
COPY qetinformation.h sources/qetinformation.h
# Fix issue #481: element editor first-click moves item (dock resize → spurious mouseMoveEvents)
COPY customelementgraphicpart.cpp  sources/editor/graphicspart/customelementgraphicpart.cpp
COPY parttext.cpp                  sources/editor/graphicspart/parttext.cpp
COPY partdynamictextfield.cpp      sources/editor/graphicspart/partdynamictextfield.cpp
# Fix issue #283: AlignHCenter saved but AlignCenter checked on load — center alignment lost
COPY addtabledialog.cpp            sources/factory/ui/addtabledialog.cpp

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS debug

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
    # X11/XCB
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
    fonts-dejavu-core \
    # ── Fault-finding tools ──
    gdb \
    valgrind \
    strace \
    ltrace \
    linux-tools-generic \
    && rm -rf /var/lib/apt/lists/*

COPY --from=debug-builder /usr/local /usr/local
# Also copy the full source tree so GDB can find source files
COPY --from=debug-builder /src /src

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share
ENV QT_X11_NO_MITSHM=1

# Default: run under GDB. Override CMD in docker-compose for valgrind etc.
CMD ["gdb", "-ex", "run", "-ex", "bt", "--args", "qelectrotech"]

# ─────────────────────────────────────────────
# Stage 4: Runtime
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

# ─────────────────────────────────────────────
# Stage 5: ThreadSanitizer (detects data races)
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS tsan-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive --depth=1 \
    https://github.com/qelectrotech/qelectrotech-source-mirror.git .

COPY qetapp.cpp.patch sources/qetapp.cpp
COPY machine_info.h    sources/machine_info.h
COPY main.cpp          sources/main.cpp
COPY qetdiagrameditor.h sources/qetdiagrameditor.h
COPY fileelementcollectionitem.h   sources/ElementsCollection/fileelementcollectionitem.h
COPY fileelementcollectionitem.cpp sources/ElementsCollection/fileelementcollectionitem.cpp
COPY xmlprojectelementcollectionitem.h   sources/ElementsCollection/xmlprojectelementcollectionitem.h
COPY xmlprojectelementcollectionitem.cpp sources/ElementsCollection/xmlprojectelementcollectionitem.cpp
COPY elementscollectionmodel.cpp   sources/ElementsCollection/elementscollectionmodel.cpp
COPY terminal.cpp                  sources/qetgraphicsitem/terminal.cpp
COPY qetinformation.h sources/qetinformation.h

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_C_FLAGS="-fsanitize=thread -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_CXX_FLAGS="-fsanitize=thread -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=thread" \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS tsan

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    libkf5coreaddons5 \
    libkf5widgetsaddons5 \
    libsqlite3-0 \
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
    fonts-dejavu-core \
    xvfb \
    libtsan0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tsan-builder /usr/local /usr/local
COPY --from=tsan-builder /src /src

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share
ENV QT_X11_NO_MITSHM=1
# halt_on_error=0: collect all races, not just the first
# second_deadlock_stack=1: show both threads' stacks on deadlock
# history_size=7: maximum race history (uses more RAM but catches more)
ENV TSAN_OPTIONS="halt_on_error=0:log_path=/tsan-logs/tsan:second_deadlock_stack=1:history_size=7"

RUN mkdir -p /tsan-logs

CMD ["qelectrotech"]

# ─────────────────────────────────────────────
# Stage 6: AddressSanitizer (detects memory errors)
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS asan-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive --depth=1 \
    https://github.com/qelectrotech/qelectrotech-source-mirror.git .

COPY qetapp.cpp.patch sources/qetapp.cpp
COPY machine_info.h    sources/machine_info.h
COPY main.cpp          sources/main.cpp
COPY qetdiagrameditor.h sources/qetdiagrameditor.h
COPY fileelementcollectionitem.h   sources/ElementsCollection/fileelementcollectionitem.h
COPY fileelementcollectionitem.cpp sources/ElementsCollection/fileelementcollectionitem.cpp
COPY xmlprojectelementcollectionitem.h   sources/ElementsCollection/xmlprojectelementcollectionitem.h
COPY xmlprojectelementcollectionitem.cpp sources/ElementsCollection/xmlprojectelementcollectionitem.cpp
COPY elementscollectionmodel.cpp   sources/ElementsCollection/elementscollectionmodel.cpp
COPY terminal.cpp                  sources/qetgraphicsitem/terminal.cpp
COPY styleeditor.cpp               sources/editor/styleeditor.cpp
COPY exportdialog.cpp              sources/exportdialog.cpp
COPY genericpanel.cpp              sources/genericpanel.cpp
COPY elementscene.cpp              sources/editor/elementscene.cpp
COPY qetinformation.h sources/qetinformation.h

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_C_FLAGS="-fsanitize=address -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_CXX_FLAGS="-fsanitize=address -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS asan

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    libkf5coreaddons5 \
    libkf5widgetsaddons5 \
    libsqlite3-0 \
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
    fonts-dejavu-core \
    xvfb \
    libasan6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=asan-builder /usr/local /usr/local
COPY --from=asan-builder /src /src

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share
ENV QT_X11_NO_MITSHM=1
# halt_on_error=0: report all errors, keep running
# detect_leaks=1: enable LeakSanitizer for heap leak detection
ENV ASAN_OPTIONS="halt_on_error=0:log_path=/asan-logs/asan:detect_leaks=1"

RUN mkdir -p /asan-logs

CMD ["qelectrotech"]

# ─────────────────────────────────────────────
# Stage 7: Fuzzer — GUI stress tester (debug binary + Python fuzzer)
# ─────────────────────────────────────────────
# The fuzzer image is self-contained: it runs Xvfb internally, drives
# QET via xdotool, and logs all crashes to /fuzzer/logs/.
#
# Environment variables (all optional):
#   FUZZER_HOURS  — how long to run (default 1)
#   FUZZER_SPEED  — slow | normal | fast (default normal)
#   FUZZER_SEED   — random seed for reproducibility
#   FUZZER_LOG_DIR — where to write logs (default /fuzzer/logs)
#
FROM ubuntu:22.04 AS fuzzer-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive --depth=1 \
    https://github.com/qelectrotech/qelectrotech-source-mirror.git .

COPY qetapp.cpp.patch sources/qetapp.cpp
COPY machine_info.h    sources/machine_info.h
COPY main.cpp          sources/main.cpp
COPY qetdiagrameditor.h sources/qetdiagrameditor.h
COPY fileelementcollectionitem.h   sources/ElementsCollection/fileelementcollectionitem.h
COPY fileelementcollectionitem.cpp sources/ElementsCollection/fileelementcollectionitem.cpp
COPY xmlprojectelementcollectionitem.h   sources/ElementsCollection/xmlprojectelementcollectionitem.h
COPY xmlprojectelementcollectionitem.cpp sources/ElementsCollection/xmlprojectelementcollectionitem.cpp
COPY elementscollectionmodel.cpp   sources/ElementsCollection/elementscollectionmodel.cpp
COPY elementslocation.cpp          sources/ElementsCollection/elementslocation.cpp
COPY terminal.cpp                  sources/qetgraphicsitem/terminal.cpp
COPY qetinformation.h sources/qetinformation.h
COPY customelementgraphicpart.cpp  sources/editor/graphicspart/customelementgraphicpart.cpp
COPY parttext.cpp                  sources/editor/graphicspart/parttext.cpp
COPY partdynamictextfield.cpp      sources/editor/graphicspart/partdynamictextfield.cpp
# Fix issue #283: AlignHCenter saved but AlignCenter checked on load — center alignment lost
COPY addtabledialog.cpp            sources/factory/ui/addtabledialog.cpp

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS fuzzer

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
    # X11/XCB
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
    fonts-dejavu-core \
    # Fuzzer tooling
    xvfb \
    xdotool \
    openbox \
    scrot \
    python3 \
    python3-pip \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

COPY --from=fuzzer-builder /usr/local /usr/local

# Install fuzzer scripts
COPY fuzzer/ /fuzzer/

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share
ENV QT_X11_NO_MITSHM=1
ENV DISPLAY=:99
ENV FUZZER_LOG_DIR=/fuzzer/logs
ENV FUZZER_HOURS=1
ENV FUZZER_SPEED=normal

RUN mkdir -p /fuzzer/logs /fuzzer/logs/screenshots

ENTRYPOINT ["/bin/bash", "/fuzzer/run.sh"]

# ─────────────────────────────────────────────
# Stage 8: Fuzzer-ASAN (AddressSanitizer binary + fuzzer)
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS fuzzer-asan-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates build-essential cmake git pkg-config \
    qtbase5-dev qtbase5-private-dev qttools5-dev qttools5-dev-tools \
    libqt5svg5-dev extra-cmake-modules libkf5coreaddons-dev \
    libkf5widgetsaddons-dev libsqlite3-dev ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive --depth=1 \
    https://github.com/qelectrotech/qelectrotech-source-mirror.git .

COPY qetapp.cpp.patch sources/qetapp.cpp
COPY machine_info.h    sources/machine_info.h
COPY main.cpp          sources/main.cpp
COPY qetdiagrameditor.h sources/qetdiagrameditor.h
COPY fileelementcollectionitem.h   sources/ElementsCollection/fileelementcollectionitem.h
COPY fileelementcollectionitem.cpp sources/ElementsCollection/fileelementcollectionitem.cpp
COPY xmlprojectelementcollectionitem.h   sources/ElementsCollection/xmlprojectelementcollectionitem.h
COPY xmlprojectelementcollectionitem.cpp sources/ElementsCollection/xmlprojectelementcollectionitem.cpp
COPY elementscollectionmodel.cpp   sources/ElementsCollection/elementscollectionmodel.cpp
COPY elementslocation.cpp          sources/ElementsCollection/elementslocation.cpp
COPY terminal.cpp                  sources/qetgraphicsitem/terminal.cpp
COPY qetinformation.h sources/qetinformation.h
COPY customelementgraphicpart.cpp  sources/editor/graphicspart/customelementgraphicpart.cpp
COPY parttext.cpp                  sources/editor/graphicspart/parttext.cpp
COPY partdynamictextfield.cpp      sources/editor/graphicspart/partdynamictextfield.cpp

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_C_FLAGS="-fsanitize=address -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_CXX_FLAGS="-fsanitize=address -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address" \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS fuzzer-asan

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    libqt5core5a libqt5gui5 libqt5widgets5 libqt5svg5 libqt5xml5 \
    libqt5sql5 libqt5sql5-sqlite libqt5dbus5 libqt5printsupport5 \
    libqt5concurrent5 qt5-gtk-platformtheme \
    libkf5coreaddons5 libkf5widgetsaddons5 libsqlite3-0 \
    libx11-6 libxcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 \
    libxkbcommon-x11-0 libxext6 libxrender1 fonts-dejavu-core \
    xvfb xdotool openbox scrot python3 imagemagick libasan6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=fuzzer-asan-builder /usr/local /usr/local
COPY fuzzer/ /fuzzer/

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share
ENV QT_X11_NO_MITSHM=1
ENV DISPLAY=:99
ENV FUZZER_LOG_DIR=/fuzzer/logs
ENV FUZZER_HOURS=1
ENV FUZZER_SPEED=normal
ENV ASAN_OPTIONS="halt_on_error=0:log_path=/fuzzer/logs/asan:detect_leaks=1"

RUN mkdir -p /fuzzer/logs /fuzzer/logs/screenshots

ENTRYPOINT ["/bin/bash", "/fuzzer/run.sh"]

# ─────────────────────────────────────────────
# Stage 9: Fuzzer-TSan (ThreadSanitizer binary + fuzzer)
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS fuzzer-tsan-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates build-essential cmake git pkg-config \
    qtbase5-dev qtbase5-private-dev qttools5-dev qttools5-dev-tools \
    libqt5svg5-dev extra-cmake-modules libkf5coreaddons-dev \
    libkf5widgetsaddons-dev libsqlite3-dev ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive --depth=1 \
    https://github.com/qelectrotech/qelectrotech-source-mirror.git .

COPY qetapp.cpp.patch sources/qetapp.cpp
COPY machine_info.h    sources/machine_info.h
COPY main.cpp          sources/main.cpp
COPY qetdiagrameditor.h sources/qetdiagrameditor.h
COPY fileelementcollectionitem.h   sources/ElementsCollection/fileelementcollectionitem.h
COPY fileelementcollectionitem.cpp sources/ElementsCollection/fileelementcollectionitem.cpp
COPY xmlprojectelementcollectionitem.h   sources/ElementsCollection/xmlprojectelementcollectionitem.h
COPY xmlprojectelementcollectionitem.cpp sources/ElementsCollection/xmlprojectelementcollectionitem.cpp
COPY elementscollectionmodel.cpp   sources/ElementsCollection/elementscollectionmodel.cpp
COPY elementslocation.cpp          sources/ElementsCollection/elementslocation.cpp
COPY terminal.cpp                  sources/qetgraphicsitem/terminal.cpp
COPY qetinformation.h sources/qetinformation.h
COPY customelementgraphicpart.cpp  sources/editor/graphicspart/customelementgraphicpart.cpp
COPY parttext.cpp                  sources/editor/graphicspart/parttext.cpp
COPY partdynamictextfield.cpp      sources/editor/graphicspart/partdynamictextfield.cpp

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_C_FLAGS="-fsanitize=thread -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_CXX_FLAGS="-fsanitize=thread -g -O1 -fno-omit-frame-pointer" \
    -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=thread" \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS fuzzer-tsan

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    libqt5core5a libqt5gui5 libqt5widgets5 libqt5svg5 libqt5xml5 \
    libqt5sql5 libqt5sql5-sqlite libqt5dbus5 libqt5printsupport5 \
    libqt5concurrent5 qt5-gtk-platformtheme \
    libkf5coreaddons5 libkf5widgetsaddons5 libsqlite3-0 \
    libx11-6 libxcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 \
    libxkbcommon-x11-0 libxext6 libxrender1 fonts-dejavu-core \
    xvfb xdotool openbox scrot python3 imagemagick libtsan0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=fuzzer-tsan-builder /usr/local /usr/local
COPY fuzzer/ /fuzzer/

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share
ENV QT_X11_NO_MITSHM=1
ENV DISPLAY=:99
ENV FUZZER_LOG_DIR=/fuzzer/logs
ENV FUZZER_HOURS=1
ENV FUZZER_SPEED=normal
ENV TSAN_OPTIONS="halt_on_error=0:log_path=/fuzzer/logs/tsan:second_deadlock_stack=1:history_size=7"

RUN mkdir -p /fuzzer/logs /fuzzer/logs/screenshots

ENTRYPOINT ["/bin/bash", "/fuzzer/run.sh"]

# ─────────────────────────────────────────────
# Stage 10: EDZ feature branch (run to test importer)
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS edz-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive --depth=1 --branch feature/edz-import \
    https://github.com/ispyisail/qelectrotech-source-mirror.git .

# Apply terminalNr-based grouping fix (PR #513 response)
COPY edzpart.h            sources/import/edz/edzpart.h
COPY edzpart.cpp          sources/import/edz/edzpart.cpp
COPY edzelementbuilder.cpp sources/import/edz/edzelementbuilder.cpp

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS edz

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    libkf5coreaddons5 \
    libkf5widgetsaddons5 \
    libsqlite3-0 \
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
    fonts-dejavu-core \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=edz-builder /usr/local /usr/local

RUN useradd -m -u 1000 qet
USER qet
WORKDIR /home/qet

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share

CMD ["qelectrotech"]

# ── EDZ importer fuzzer ───────────────────────────────────────────────────────
# Builds a standalone harness that drives EdzImporter::importToDirectory()
# against a corpus of malformed .edz files, compiled with ASAN + UBSan.
FROM edz-builder AS edz-fuzzer-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    clang \
    python3 \
    p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY edz-fuzzer/ /edz-fuzzer/

RUN cmake -B /edz-fuzzer/build \
    -S /edz-fuzzer \
    -DEDZ_SRC=/src/sources/import/edz \
    -DASAN=ON \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -G Ninja \
    && cmake --build /edz-fuzzer/build --parallel $(nproc)

FROM ubuntu:22.04 AS edz-fuzzer

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    libqt5core5a \
    libqt5xml5 \
    python3 \
    p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY --from=edz-fuzzer-builder /edz-fuzzer/build/fuzz_edz /edz-fuzzer/build/fuzz_edz
COPY --from=edz-fuzzer-builder /usr/local/lib /usr/local/lib
COPY edz-fuzzer/ /edz-fuzzer/

RUN mkdir -p /edz-fuzzer/logs /edz-fuzzer/corpus

CMD ["bash", "/edz-fuzzer/run.sh"]

# ─────────────────────────────────────────────
# Stage 11: Combined test build for manual review
# master + PR #646/#647 (diagnostic logging rework) +
# PR #625/#628/#629/#630 (discussion #503 wiring-database stack).
# Throwaway branch, not a proposed change -- see
# test-build-logging-wiring on the ispyisail fork.
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS testbuild-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Docker caches the git clone layer by command string alone, so re-running a
# build after the branch has been force-pushed would silently reuse the OLD
# commits -- i.e. hand someone a stale binary they believe is current. Bump
# TESTBUILD_REV (any new value) to force a genuinely fresh clone:
#   docker compose build --build-arg TESTBUILD_REV=$(date +%s) qet-testbuild
ARG TESTBUILD_REV=1
RUN echo "cache key: ${TESTBUILD_REV}" \
    && git clone --recursive --depth=1 --branch test-build-logging-wiring \
       https://github.com/ispyisail/qelectrotech-source-mirror.git . \
    && git log -1 --format='built from %H %s' > /src/BUILT_FROM.txt \
    && cat /src/BUILT_FROM.txt

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS testbuild

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    libkf5coreaddons5 \
    libkf5widgetsaddons5 \
    libsqlite3-0 \
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
    fonts-dejavu-core \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=testbuild-builder /usr/local /usr/local
# Record which commit this image was actually built from, so a stale image can
# be spotted: docker run --rm qelectrotech:testbuild cat /BUILT_FROM.txt
COPY --from=testbuild-builder /src/BUILT_FROM.txt /BUILT_FROM.txt

RUN useradd -m -u 1000 qet
USER qet
WORKDIR /home/qet

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share

CMD ["qelectrotech"]

# ── Manual test build: feature/report-link-autonum (PR #701/#702) ─────────────
# Clean single-branch build (no merging, unlike testbuild above) so PR #702
# can be exercised as-is: clickable folio-reference arrows, Renvois
# auto-numbering with optional Préfixe/Suffixe, and the report-label
# reload/live-update fix.
FROM ubuntu:22.04 AS reportlink-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Same staleness trap as TESTBUILD_REV above: this branch gets new commits
# pushed to it as review feedback lands, but Docker caches the git clone
# layer by command string alone. Bump REPORTLINK_REV to force a fresh clone:
#   docker compose build --build-arg REPORTLINK_REV=$(date +%s) qet-reportlink
ARG REPORTLINK_REV=1
RUN echo "cache key: ${REPORTLINK_REV}" \
    && git clone --recursive --depth=1 --branch feature/report-link-autonum \
       https://github.com/ispyisail/qelectrotech-source-mirror.git . \
    && git log -1 --format='built from %H %s' > /src/BUILT_FROM.txt \
    && cat /src/BUILT_FROM.txt

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS reportlink

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    libkf5coreaddons5 \
    libkf5widgetsaddons5 \
    libsqlite3-0 \
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
    fonts-dejavu-core \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=reportlink-builder /usr/local /usr/local
# Record which commit this image was actually built from:
# docker run --rm qelectrotech:reportlink cat /BUILT_FROM.txt
COPY --from=reportlink-builder /src/BUILT_FROM.txt /BUILT_FROM.txt

RUN useradd -m -u 1000 qet
USER qet
WORKDIR /home/qet

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share

CMD ["qelectrotech"]

# ── Manual test build: mega multi-PR combined build (2026-08-11) ──────────
# Fresh clone from upstream master with 47 currently-open, Qt5-compatible
# PRs merged in. Excludes: Qt6-migration PRs (#709, #705, #507, #505),
# a draft (#635, needs libspnav besides) and #396 (CI-only draft) --
# #690/#704/#692 (all drafts) were added by explicit request, each merged
# clean or with a small hand-resolved conflict -- CONFLICTING-with-master
# PRs per GitHub (#505, #502), a CI-only workflow PR not relevant to an
# app testbuild (#510), and 2 PRs left unmerged after hand-resolving 9 of
# the original 11 conflicts: #657 (60-QAction refactor touching most of
# qetdiagrameditor.cpp -- too large to safely hand-merge quickly) and
# #516 (a genuine data-race fix in setUpData() -- merging it risked either
# silently reintroducing the race or breaking its related unreadable-
# folder tooltip feature). Branch: testbuild-mega-20260811 on the
# ispyisail fork. Throwaway integration branch, not a proposed change --
# never open a PR
# from it. To refresh: re-merge onto current master, force-push the
# branch, then rebuild with a new cache key:
#   docker compose build --build-arg MEGATEST_REV=$(date +%s) qet-megatest
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS megatest-builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    qtbase5-dev \
    qtbase5-private-dev \
    qttools5-dev \
    qttools5-dev-tools \
    libqt5svg5-dev \
    extra-cmake-modules \
    libkf5coreaddons-dev \
    libkf5widgetsaddons-dev \
    libsqlite3-dev \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

ARG MEGATEST_REV=1
RUN echo "cache key: ${MEGATEST_REV}" \
    && git clone --recursive --depth=1 --branch testbuild-mega-20260811 \
       https://github.com/ispyisail/qelectrotech-source-mirror.git . \
    && git log -1 --format='built from %H %s' > /src/BUILT_FROM.txt \
    && cat /src/BUILT_FROM.txt

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -G Ninja

RUN cmake --build build --parallel $(nproc)
RUN cmake --install build

FROM ubuntu:22.04 AS megatest

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    libkf5coreaddons5 \
    libkf5widgetsaddons5 \
    libsqlite3-0 \
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
    fonts-dejavu-core \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=megatest-builder /usr/local /usr/local
# Record which commit this image was actually built from:
# docker run --rm qelectrotech:megatest cat /BUILT_FROM.txt
COPY --from=megatest-builder /src/BUILT_FROM.txt /BUILT_FROM.txt

RUN useradd -m -u 1000 qet
USER qet
WORKDIR /home/qet

ENV XDG_DATA_DIRS=/usr/local/share:/usr/share

CMD ["qelectrotech"]

# ── Scenario runner: deterministic, scripted GUI tests on the mega build ──
# Adds xdotool/scrot/python3 automation tooling and scenarios/ (+ the
# fuzzer.actions GUI-driving code and simulator.canon verification it
# reuses) on top of the already-built, elements-collection-complete
# megatest image, rather than rebuilding QET again from scratch.
# Runs with the host's real X server (network_mode: host, X11 socket
# mounted -- see docker-compose.yml's qet-scenarios service), not an
# internal Xvfb, so a run is actually visible while it happens.
FROM megatest AS scenarios

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    xdotool \
    scrot \
    python3 \
    python3-pip \
    python3-pil \
    x11-utils \
    x11-xserver-utils \
    && rm -rf /var/lib/apt/lists/*

COPY scenarios/ /app/scenarios/
COPY fuzzer/actions/ /app/fuzzer/actions/
COPY simulator/ /app/simulator/
RUN chown -R qet:qet /app

USER qet
WORKDIR /app

ENV QET_BINARY=/usr/local/bin/qelectrotech

ENTRYPOINT ["python3", "-m", "scenarios"]
CMD ["--list"]

# ─────────────────────────────────────────────
# Stage 12: elements repo fetch (10_electric only)
# Standalone clone of qelectrotech/qelectrotech-elements -- the same repo
# the elements/ submodule in qelectrotech-source-mirror points at -- kept
# only for pulling out 10_electric on its own, e.g. for IEC 81346
# classification work (discussion #666). Not part of the QET build.
# ─────────────────────────────────────────────
FROM ubuntu:22.04 AS elements-10-electric

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 https://github.com/qelectrotech/qelectrotech-elements.git /tmp/elements \
    && mkdir -p /out \
    && cp -r /tmp/elements/10_electric /out/ \
    && git -C /tmp/elements log -1 --format='10_electric copied from %H %s' > /out/FETCHED_FROM.txt \
    && cat /out/FETCHED_FROM.txt \
    && rm -rf /tmp/elements
