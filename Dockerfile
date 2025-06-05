# Базовый образ с Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем все файлы в контейнер
COPY . /app

# Обновляем pip и устанавливаем зависимости
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Запускаем файл bot.py
CMD ["python", "bot.py"]