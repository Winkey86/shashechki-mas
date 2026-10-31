# Контракты входов, CLI, HTTP и артефактов

Версия `1.0`, UTF-8. [Модель данных](../data-model.md) и
[протоколы](protocols.md) определяют предметные значения. Неизвестные поля запрещены;
неподдерживаемая schema_version вызывает явную ошибку без частичного расчёта.

## Сценарий и материализованный пакет

Файл сценария — JSON с обязательными `schema_version`, `scenario_id`, `city`, `drivers`,
`passengers`, `orders`, `channel_profile`, `faults`, `config`. Статическая контрольная
сцена содержит явные массивы; отсутствие заказов/водителей — допустимая сцена, а не ошибка.

| Поле | Структура / проверка |
| --- | --- |
| city | id; nodes[{id,x,y}], edges[{id,from,to,distance_m,travel_ms}]; корректные ссылки, >0 длина/время |
| drivers | [{id,start_node,vehicle_class,cost_per_km,cost_per_min,minimum_profit,markup,decrement,rating_history}]; деньги строками, класс economy/comfort |
| passengers | [{id,budget,max_wait_ms,allowed_tariffs,min_driver_rating,rating_history}]; rating строкой точного десятичного порога |
| orders | [{id,passenger_id,created_at_ms,origin,destination,tariff_id}]; ссылки существуют, нет пересекающихся активных заказов одного пассажира |
| rating_history | [{id,value,cause,commitment_id,source_event_id,origin}]; исходная синтетическая проверенная история имеет origin=fixture и сохраняется отдельно от runtime-событий |
| channel_profile | [{channel,from_ms,to_ms,delay_ms,drop,duplicate_count,duplicate_offset_ms}]; непересекающиеся интервалы для каждого канала (упорядоченная пара ролей, необязательное уточнение по ID), ≥1 мс задержки; отсутствующий канал использует сохранённый default |
| faults | [{id,type,trigger,target,parameters}]; тип F1–F7, валидные параметры типа, trigger=time либо первое подходящее событие |
| config | allocation=central/auction, conflict_policy=first_acceptable/negotiation, rating_policy=off/fixed/dynamic, protection_profile=baseline/protected, limits, weights, deadlines |

Точные параметры воздействия: F1 driver_id и момент/after_confirm; F2 agent_id,
field=position/eta/price и replacement; F3 message selector, mode=duplicate/delay и
count/delay_ms; F4 order/driver selector и mode=conflicting_assignment/unauthorized;
F5 agent_id и mode=keep_negotiating/redelegate/breach; F6 tool=dispatcher/router и
unavailable_from/to_ms; F7 subject_id, forged_value/history и asserted_source.
Условный селектор first_matching сохраняется вместе с resolved_target. Если подходящей
цели нет, not_triggered отражается в результате.

`limits`: horizon_ms (по умолчанию 86400000), max_events (1000000),
max_pending_events (100000). `deadlines`: allocation_window_ms=2000,
consent_window_ms=2000, round_ms=2000, pickup_grace_ms=5000,
max_rounds=3, max_reassignments=2, telemetry_interval_ms=5000.
Параметр не может ослаблять обязательный предел protected (например max_rounds>3).
`weights`: wait_kopecks_per_ms={"numerator":1,"denominator":60}, driver_rating_kopecks=1000;
точная запись дроби использует поля numerator/denominator.

Генератор серии задаёт experiment_id, generator_version, seeds, city, generator,
variants и fixed_config. Генератор детально нормируется в [experiments.md](experiments.md).
Он сначала создаёт InputBundle: scenario + provenance `{seed,generator_version,python_version}`.
Пакет сохраняется до запуска вариантов и получает SHA-256. Повтор использует пакет,
не запускает генерацию заново. Разная config механизма не меняет input_hash.

## CLI

Запуск из корня: `PYTHONPATH=src python3 -m shashechki <command>`.
Все пути CLI локальные; существующий результат не перезаписывается.

| Команда | Аргументы | Результат |
| --- | --- | --- |
| validate | `--scenario PATH` либо `--experiment PATH` (ровно один) | Проверка ссылок, типов/границ; структурированные ошибки |
| run | `--scenario PATH --output-root DIR` | Опыт; config из файла, необязательные `--allocation central/auction`, `--protection baseline/protected` явно входят в config |
| run | `--replay-inputs RESULT_DIR --output-root DIR` | Новое выполнение сохранённых input.json+config.json; проверка хешей/версий |
| series | `--experiment PATH --output-root DIR` | Материализация и последовательные варианты всех пар |
| serve | `--host 127.0.0.1 --port 8765 --output-root DIR` | Локальный UI, каталог сценариев из `scenarios/` |
| export | `--result RESULT_DIR --destination NEW_ZIP` | Архив с манифестом/хешами; источник завершён, целевой файл ещё не существует |
| compare | `--left RESULT_DIR --right RESULT_DIR` | Сравнение canonical_sha256 и модельных метрик, технические поля отдельно |

serve отклоняет внешний host. stdout — JSON с идентификатором, статусом и путём;
stderr — официальные диагностические сообщения без смешивания с JSON.
Коды выхода: 0 — операция выполнена; 2 — неверные аргументы/входы/версия;
3 — ошибка исполнения/сохранения; 4 — различие canonical при compare; 130 — отмена.
Исчерпание горизонта — выполненный расчёт с termination_reason, не ошибка CLI.

## HTTP: общее

Same origin, `/api/v1`; JSON Content-Type; тело ≤2 МиБ. Ответы не используют NaN.
API принимает идентификаторы зарегистрированных сценариев/результатов и разрешённые
настройки, а не произвольные файловые пути. ID/path traversal и неизвестные артефакты
отклоняются. Статика `/` доступна из web; `/fonts/` отображает только разрешённые файлы design/fonts.
Изменяющие запросы проверяют Origin/Host на локальный origin; CORS для внешних сайтов
не включается. Синтетические данные не содержат реальных персональных сведений.

| Метод и путь | Вход | Выход |
| --- | --- | --- |
| GET /scenarios | Без тела | 200 `{scenarios:[{id,title,description,kind,allowed_overrides}]}` |
| POST /jobs | JobRequest | 202 Job при новом задании |
| GET /jobs/{job_id} | — | 200 Job; 404 при неизвестном ID |
| POST /jobs/{job_id}/cancel | `{}` | 200 Job после принятия; 409 если уже succeeded/failed |
| GET /results | — | 200 `{results:[ResultSummary]}` включая incomplete с причиной |
| GET /results/{result_id} | — | 200 manifest+metrics+artifact links; 409 если обязательный результат ещё не завершён |
| GET /results/{result_id}/artifacts/{name} | — | 200 файл только из разрешённого манифеста |

Пути в таблице относительны `/api/v1`. Список результатов не выдаёт содержимое произвольной папки.

### JobRequest

Обязательные `schema_version`, `request_id`, `kind`; request_id соответствует правилу ID.
Для `kind=run`: `scenario_id` и `overrides` из опубликованного allowed_overrides.
Для `kind=series`: `experiment_id`, без произвольного изменения парности.
Для `kind=export`: `result_id`, `archive_name` — только basename `.zip`, без разделителей;
сервер резервирует его внутри export-каталога output_root. Другие сочетания полей — 422.

Повтор request_id и того же канонического тела возвращает существующий Job (200),
не создаёт повторный расчёт. Иное тело при том же request_id — 409 REQUEST_ID_CONFLICT.
Реестр request_id/заданий сохраняется атомарно в `.local/jobs.json`; после перезапуска
неоконченные задания становятся failed/INTERRUPTED, завершённые ссылки остаются.
Идемпотентность действует на этот локальный реестр, не обещает распределённую транзакцию.

Job: `job_id, request_id, kind, state, phase, completed_runs, total_runs, current_result_id,
result_ids, error`. total_runs известен из плана, completed_runs увеличивается только после
сохранения прогона; процент внутри опыта не выдумывается. Состояния — в data-model.
Принятая отмена running устанавливает cancelling под той же блокировкой, что завершение;
после этого succeeded запрещён. Уже завершённый опыт не удаляется. Повтор отмены
cancelling/cancelled — 200 без эффекта. Разрыв fetch сам по себе не отменяет job.
Опрос последовательный, около 500 мс, без перекрывающихся запросов.

### Ошибки

Единая оболочка: `{error:{code,message,field_errors,retryable},request_id}`;
field_errors — массив `{path,code,message}`. Неизвестный request_id до разбора — null.

| HTTP | Коды и условие |
| --- | --- |
| 400 | INVALID_JSON, неверный синтаксис/кодировка |
| 403 | INVALID_ORIGIN/HOST для внешнего изменяющего запроса |
| 404 | NOT_FOUND (сценарий, задание, результат, артефакт) |
| 409 | REQUEST_ID_CONFLICT, TERMINAL_JOB, RESULT_INCOMPLETE, ARTIFACT_EXISTS |
| 413 | BODY_TOO_LARGE |
| 415 | UNSUPPORTED_MEDIA_TYPE |
| 422 | INVALID_INPUT, UNSUPPORTED_SCHEMA, INVALID_OVERRIDE; корректный JSON, неверный смысл |
| 503 | QUEUE_FULL, retryable=true, Retry-After: 1 |
| 500 | INTERNAL_ERROR без внутренних путей/stack trace в UI |

Ошибка worker при экспорте — GET job возвращает 200 с state=failed/error=EXPORT_FAILED.
Ошибка записи результата — SAVE_FAILED; исходный законченный результат не изменяется.
Очередь имеет два ожидающих задания плюс одно выполняемое; используется put_nowait,
не предварительная проверка full(). Клиент проверяет response.ok и сохраняет введённые
настройки при ошибке.

## Форматы результатов

`results/<execution_id>/` одиночного опыта:

| Файл | Содержание |
| --- | --- |
| input.json | Полный материализованный вход и provenance |
| config.json | Полная фактически применённая конфигурация |
| trace.jsonl | Последовательные TraceEvent без потери отклонённых сообщений |
| metrics.json | Показатели с единицами, значениями и причинами null |
| orders.csv / drivers.csv | Исход каждого заказа, доход/расход/простой каждого водителя |
| playback.json | initial snapshot, checkpoints каждые 100 содержательных изменений представления, изменения полей/движения |
| manifest.json | schema/model/generator/Python versions, case_id, execution_id, hashes, complete, termination_reason, technical timing |

Серия содержит input_bundles/, ссылки на неизменяемые исполнения вариантов, pairs.csv,
summary.json и завершающий manifest.json с перечнем всех обязательных файлов.
Манифест архива включает и файлы вложенных опытов; относительные пути не выходят за корень.

Сначала mkdir(exist_ok=false), затем временные файлы внутри нового каталога; после
проверки размеров/хешей завершающий манифест публикуется последним атомарной заменой.
Отсутствие complete=true означает incomplete. Ошибка не удаляет доказательства частичной
записи. Совпадение ID/назначения не вызывает перезапись. ZIP создаётся через отдельный
временный файл и резервирование целевого имени; исходные файлы не изменяются.

Канонический поток: UTF-8/LF, sort_keys, separators=(',',':'), allow_nan=false;
стабильный порядок массивов и столбцов. case_id = SHA-256 от model_version, schema_version,
input_hash и модельной config. Из canonical исключены только execution_id, календарные
метки, пути и измеренное wall-clock время. Они сохранены в technical metadata, а не
удалены из происхождения. Повтор должен совпадать по canonical trace и модельным метрикам.

## Контракт просмотра

Playback содержит schema_version, result_id, initial_snapshot, checkpoints[{seq,change_index,state}],
changes[{seq,time_ms,assignments}], movements[{agent_id,from_ms,to_ms,edge_ids}].
Assignments — типизированные абсолютные значения по разрешённым полям представления,
не произвольные исполняемые выражения/JSON Patch. Изменения применяются по seq.
Курсор 0 означает initial; шаг — следующий seq; возврат — ближайший checkpoint и изменения.
Все панели читают один восстановленный state. Интерполяция движения не порождает решений.
Неподдерживаемая версия блокирует просмотр с объяснением; повреждённая трасса не скрывается.

## Уточнения реализации 31.10.2026

InputBundle допускает order.candidate_ids (ровно два существующих водителя) и driver.unavailable_until_ms для управляемого дефицита. HTTP overrides допускают tariff_id, budget (строка RUB), passenger_history_score (целое 1–5). GET /api/v1/materials возвращает только существующие отчёты и приложения; /reports/lab-01.pdf…lab-04.pdf и /materials/source.zip, /materials/demo.zip отдают фиксированные файлы. GET /api/v1/exports/NAME.zip выдаёт готовый экспорт. Контрольные точки создаются по содержательным изменениям, содержат change_index; исходный raw seq и полная трасса не сокращаются. Метрики final_price и coordination_cost используют строки RUB.
