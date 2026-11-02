# Шашечки

[Публичный репозиторий](https://github.com/Winkey86/shashechki-mas) · [Матрица проверки](docs/verification.md)

Локальная визуальная многоагентная система такси для четырёх лабораторных работ. Водители, пассажиры и диспетчер имеют собственные знания, ограничения и решения. Приложение моделирует распределение заказов, торг двух приехавших водителей, смену тарифа, репутационные надбавки и отказы F1–F7.

## Запуск

Требуются Python 3.12+ и современный браузер. Установка пакетов, Node.js, аккаунты, ключи API и внешние сервисы для работы приложения не требуются.

```sh
git clone https://github.com/Winkey86/shashechki-mas.git
cd shashechki-mas
export PYTHONPATH="$PWD/src"
python3 -m shashechki serve --host 127.0.0.1 --port 8765 --output-root results
```

Открыть [приложение](http://127.0.0.1:8765). Остановка — Ctrl+C. При занятом порте указать другой через `--port`. Поддерживается только локальный адрес 127.0.0.1. Открытие index.html через file:// не заменяет сервер.

Выбрать сценарий и нажать «Запустить опыт». На карте отображаются автомобили, пассажиры, маршрут и сообщения. Пауза, шаг, возврат, скорость и выбор агента работают с одной сохранённой трассой. Итоговые показатели под картой относятся ко всему опыту; состояния карты, цены и журнала — к выбранной позиции. В разделе «Эксперименты» доступны серии, в «Надёжности» — семь воздействий, в «Материалах» — отчёты и отдельные приложения.

## Комплект сдачи

- [Работа №1: модель и архитектура](reports/lab-01.pdf).
- [Работа №2: распределение](reports/lab-02.pdf).
- [Работа №3: переговоры, тарифы и рейтинг](reports/lab-03.pdf).
- [Работа №4: устойчивость](reports/lab-04.pdf).
- Редактируемые тексты: `reports/lab-01.md` … `reports/lab-04.md`.
- [Отдельный архив исходного кода](evidence/source.zip).
- [Демонстрационный архив](evidence/demo.zip): входы всех пар, компактные таблицы и полные выбранные контрольные прогоны.
- Все 260 полных исходных прогонов остаются в локальном `results/`; каталог не включён в Git. Выбранные результаты в demo.zip сохраняют исходные имена и проверяемые манифесты. Для просмотра на другой машине распаковать приложение из source.zip, затем demo.zip в тот же корень. Четыре PDF передаются отдельно и при необходимости копируются в reports/.
- [Матрица доказательств](evidence/manifest.json), [проверки и ограничения](docs/verification.md), [индекс исследований](evidence/series-index.json).

Тема, язык и архитектура допускаются методическими указаниями. Видео не является обязательным: комплект содержит работающую демонстрацию, трассы, снимки и четыре текстовых отчёта. Даты сдачи из исходного PDF не считаются подтверждённым актуальным расписанием.

## Команды

```sh
python3 -m unittest discover -s tests -v
python3 -m shashechki validate --scenario scenarios/normal.json
python3 -m shashechki validate --experiment scenarios/series/allocation.json
python3 -m shashechki run --scenario scenarios/normal.json --output-root results
python3 -m shashechki run --scenario scenarios/conflict.json --output-root results
python3 -m shashechki run --scenario scenarios/tariff-switch.json --output-root results
python3 -m shashechki run --scenario scenarios/fault-f1.json --protection baseline --output-root results
```

stdout возвращает JSON с result_id и path. Для повторения/сравнения подставить фактические пути вместо обозначений RESULT_ID и REPEATED_ID:

```sh
python3 -m shashechki run --replay-inputs results/RESULT_ID --output-root results
python3 -m shashechki compare --left results/RESULT_ID --right results/REPEATED_ID
python3 -m shashechki export --result results/RESULT_ID --destination /tmp/shashechki-demo.zip
```

Результаты создаются в новых каталогах. Существующий ZIP не перезаписывается. Compare исключает календарные метки, пути и фактическое время расчёта; при различии возвращает код 4. Ошибки входов — код 2, I/O — 3, прерывание — 130.

## Исследования

```sh
python3 -m shashechki series --experiment scenarios/series/allocation.json --output-root results
python3 -m shashechki series --experiment scenarios/series/negotiation.json --output-root results
python3 -m shashechki series --experiment scenarios/series/rating.json --output-root results
python3 -m shashechki series --experiment scenarios/series/faults.json --output-root results
```

Основной комплект: 80 + 20 + 20 + 140 = 260 прогонов, 130 полных пар. Серия allocation содержит четыре условия по 10 пар; negotiation и rating разделены; faults содержит 10 пар для каждого F1–F7. На локальной машине выполнение основных серий занимает несколько минут и около 3,2 ГБ диска: сохраняются полные трассы и проекции, а не только средние. Прогресс выводится в stderr; канонические исходные входы материализуются до вариантов. Серии выполняются последовательно одним worker; допускаются две ожидающие задачи, отмена и восстановление диагностики после перезапуска.

`dynamic-reputation.json` — отдельная дополнительная конфигурация; она не входит в основные 260 прогонов и выводы отчётов.

## Устройство и границы

`src/shashechki/` — общее дискретно-событийное ядро и CLI/HTTP; `web/` — HTML/CSS/ES modules/SVG; `scenarios/` — материализованные контрольные входы и серии; `tests/` — unit/contract/integration; `docs/model.md` — формальная модель; `specs/001-taxi-mas/` — принятая спецификация и задачи.

Деньги вычисляются в копейках и Fraction с явным округлением HALF_UP. Рейтинговый реестр принимает только авторизованные фактом среды события. Маршруты детерминированы; просмотр не повторяет решения агентов. Контрольные точки проекции создаются каждые 100 содержательных изменений, raw trace сохраняется полностью.

Город, тарифы и стратегии синтетические. Один диспетчер остаётся точкой отказа. Правдоподобную ложь без независимых наблюдений нельзя гарантированно выявить. Вариант baseline сохраняет физику и целостность репутации. Результаты не являются оценкой конкретного коммерческого сервиса.

## Пересборка документов

Для использования приложения готовые PDF достаточно открыть. Для пересборки нужны отдельно ReportLab, Graphviz и Poppler; они не являются зависимостями симулятора. Готовые Markdown и иллюстрации позволяют повторить сборку PDF командой render_reports.py. build_evidence.py дополнительно требует полных локальных результатов по evidence/series-index.json; демонстрационный архив содержит выбранные прогоны, а не все исходные трассы:

```sh
python3 scripts/build_evidence.py
python3 scripts/render_reports.py
```

Источники диаграмм: `docs/diagrams/*.mmd` и `*.dot`; данные графиков: `reports/figures/chart-data.json`. Шрифт IBM Plex Sans включён локально с лицензией OFL. Библиотеки графиков и отчётов не загружаются приложением.

Публичная публикация исходников и артефактов разрешена владельцем 03.11.2026. Репозиторий: https://github.com/Winkey86/shashechki-mas. Приложение запускается локально; файлы отчётов и демонстрационные архивы доступны в репозитории.
