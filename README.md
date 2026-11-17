# Аванс по договору

Отчёт на дату: по каждой работе цена, выплачено и остаток, плюс итог договора.
Правила расчёта и развилки - в `DECISIONS.md`. Как читать файлы - в `ЗАПИСКА.md`.

## Запуск

Нужен Python 3.11+ и стандартная библиотека, зависимостей нет.

```bash
python report.py --data data --date 2026-11-10 --out-dir out
```

Появятся `out/works.csv` и `out/contracts.csv` (`;`, UTF-8 с BOM).

Проверка расчёта на этих данных:

```bash
python -m unittest tests.test_report -v
```
