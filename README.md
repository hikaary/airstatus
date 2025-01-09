# AirStatus

Простой скрипт на Python для мониторинга уровня заряда AirPods через Bluetooth LE.

## Возможности

- Определение уровня заряда AirPods
- Отображение статуса зарядки
- Поддержка вывода в JSON формате
- Возможность периодического обновления данных

## Требования

- Python 3.7+
- bleak

## Установка

```bash
pip install bleak
```

## Использование

Базовый запуск:
```bash
python3 airpods_monitor.py
```

Дополнительные опции:
- `--json` - вывод в формате JSON
- `--debug` - включение отладочной информации
- `--interval N` - интервал обновления в секундах (0 для единичной проверки)
- `--min-rssi N` - минимальное значение RSSI (по умолчанию: -90)

Примеры:
```bash
# Вывод в JSON формате
python3 airpods_monitor.py --json

# Обновление каждые 5 секунд
python3 airpods_monitor.py --interval 5

# Режим отладки
python3 airpods_monitor.py --debug
```
