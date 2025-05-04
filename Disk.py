import yadisk
import pandas as pd

# Параметры
TOKEN = "y0__xDypu3yARjTsTcgx67a-RJgY8JQajMm1lnIvrfxvQbbjE-r-g"  # если хотите работать через API
remote_file_path = "/ВКР/forecast.csv"  # путь на диске
local_file_path = "forecast_downloaded.csv"  # куда сохранить локально

# Подключение
y = yadisk.YaDisk(token=TOKEN)

# Проверка токена
if not y.check_token():
    raise Exception("Ошибка токена! Проверьте правильность доступа.")

# Скачиваем файл
y.download(remote_file_path, local_file_path)
print(f"Файл '{remote_file_path}' успешно скачан как '{local_file_path}'!")

# Загружаем в DataFrame для обработки
df_forecast = pd.read_csv(local_file_path)

print("Прогнозированные данные:")
print(df_forecast.head())