FROM python:3.11-slim-bookworm

# --- Системные переменные ---
ENV DEBIAN_FRONTEND=noninteractive \
    # Отключаем кэш при установке Python-пакетов
    PIP_NO_CACHE_DIR=1 \
    # Отключаем байткод
    PYTHONDONTWRITEBYTECODE=1 \
    # Включаем небуферизованный вывод в stdout/stderr
    PYTHONUNBUFFERED=1 \
    # Т.к. для конвертации в PDF используем Qt, то указываем "работу без экрана"
    QT_QPA_PLATFORM=offscreen \
    # Java (не удалось сделать динамическое определение архитектуры,
    # поэтому, если хост - MacOS, то нужно заменить на `-arm64`)
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    # Spark
    SPARK_VERSION=3.5.3 \
    HADOOP_VERSION=3 \
    SPARK_HOME=/opt/spark \
    # Python
    PYSPARK_PYTHON=python3 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Куда Playwright будет класть браузеры
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    # Пути
    PATH="${JAVA_HOME}/bin:/opt/spark/bin:/opt/spark/sbin:${PATH}"

# --- Установка системных пакетов ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Java runtime (требуется для Spark)
    openjdk-17-jdk-headless \
    # Сетевые утилиты
    curl wget \
    # Для сборки некоторых Python-пакетов
    build-essential \
    # Для geopandas (работа с геоданными)
    libgdal-dev gdal-bin libgeos-dev libproj-dev \
    # Графика и шрифты (matplotlib/bokeh + кириллица)
    libgl1 libglib2.0-0 \
    fonts-dejavu fontconfig \
    # Pandoc + TeXLive для экспорта в PDF
    pandoc \
    texlive-xetex texlive-fonts-recommended texlive-plain-generic \
    texlive-latex-recommended texlive-latex-extra texlive-lang-cyrillic \
    # wkhtmltopdf для pdfkit
    wkhtmltopdf \
    # Для корректной работы с локалями
    locales \
    # Процесс-менеджер (для отладки)
    procps \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# --- Установка Apache Spark ---
RUN curl -fsSL "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz" \
    | tar -xz -C /opt/ \
    && mv /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} /opt/spark \
    # Скачивание Kafka connector для Spark Streaming (задание 3)
    && curl -fsSL "https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/${SPARK_VERSION}/spark-sql-kafka-0-10_2.12-${SPARK_VERSION}.jar" \
       -o /opt/spark/jars/spark-sql-kafka-0-10_2.12-${SPARK_VERSION}.jar \
    # Kafka clients (зависимость)
    && curl -fsSL "https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.5.1/kafka-clients-3.5.1.jar" \
       -o /opt/spark/jars/kafka-clients-3.5.1.jar \
    # Commons pool (зависимость Kafka connector)
    && curl -fsSL "https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar" \
       -o /opt/spark/jars/commons-pool2-2.11.1.jar \
    # Spark token provider (зависимость)
    && curl -fsSL "https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/${SPARK_VERSION}/spark-token-provider-kafka-0-10_2.12-${SPARK_VERSION}.jar" \
       -o /opt/spark/jars/spark-token-provider-kafka-0-10_2.12-${SPARK_VERSION}.jar

# --- Установка Python-зависимостей ---
WORKDIR /app

# Копируем requirements.txt с Python-зависимостями
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright

# --- Настройка Spark для экономии памяти (8GB RAM) ---
RUN \
    # Память для driver (главный процесс Spark, координирует задачи)
    echo "spark.driver.memory 4g" >> /opt/spark/conf/spark-defaults.conf \
    # Память для executor (выполняет вычисления)
    && echo "spark.executor.memory 2g" >> /opt/spark/conf/spark-defaults.conf \
    # Количество партиций при shuffle-операциях (join, groupBy, и т.д.)
    && echo "spark.sql.shuffle.partitions 8" >> /opt/spark/conf/spark-defaults.conf \
    # Параллелизм для RDD-операций (map, filter, и т.д.)
    && echo "spark.default.parallelism 4" >> /opt/spark/conf/spark-defaults.conf \
    # Доля heap, которую Spark использует для выполнения и хранения
    && echo "spark.memory.fraction 0.6" >> /opt/spark/conf/spark-defaults.conf \
    # Сколько резервировать под storage (кэш RDD/DataFrame)
    && echo "spark.memory.storageFraction 0.3" >> /opt/spark/conf/spark-defaults.conf \
    # Сборка мусора через G1GC
    && echo "spark.driver.extraJavaOptions -XX:+UseG1GC" >> /opt/spark/conf/spark-defaults.conf

# Порт Jupyter
EXPOSE 8888

# --- Рабочая директория ---
WORKDIR /app

CMD ["jupyter", "lab", \
     "--ip=0.0.0.0", \
     "--port=8888", \
     "--no-browser", \
     "--allow-root", \
     "--ServerApp.allow_remote_access=True", \
     "--IdentityProvider.token=", \
     "--ServerApp.password=", \
     "--ServerApp.root_dir=/app"]
