# Data Model: «Шашечки»

Нормативная техническая детализация [spec.md](spec.md), схема версии `1.0`.
Обязательные поля не подразумевают глобальную доступность агентам.

## Единицы и идентификаторы

- `time_ms`, `duration_ms`, `distance_m`: неотрицательные целые; время рёбер >0.
- `*_kopecks`: целые, прибыль может быть отрицательной; входная цена неотрицательна.
- Рейтинг/веса: точные дроби `{numerator: int, denominator: positive int}`;
  экранное округление не используется в предметном сравнении.
- Деньги в API/JSON представлены десятичными строками рублей с двумя знаками;
  преобразование в копейки проверяется без float. CSV использует те же строки.
- ID ASCII: `[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}`; уникален в своём пространстве.
  Условия хешируются SHA-256; `case_id` содержит 64 hex-символа.
- Неизвестное значение — `null` плюс `reason`; NaN/Infinity запрещены.

## Сущности и связи

| Сущность | Основные поля | Ограничения и связи |
| --- | --- | --- |
| City | id, nodes, edges, display_bounds | Узлы имеют id,x,y; координаты только для изображения |
| RoadEdge | id, from, to, distance_m, travel_ms | Направленное ребро, положительные длина/время; двусторонняя улица — два ребра |
| Route | edge_ids, distance_m, travel_ms | Суммы соответствуют рёбрам; недостижимый маршрут — отсутствие с причиной |
| Agent | id, role, state, knowledge, policy_id | Три роли; состояние и знания обновляются разрешёнными событиями |
| Driver | agent_id, node/edge_position, vehicle_class, cost_per_km, cost_per_min, minimum_profit, markup, decrement, idle_since, active_commitment_id, history | Класс economy либо comfort; comfort допускает economy; одна активная поездка |
| Passenger | agent_id, budget, max_wait_ms, allowed_tariffs, min_driver_rating, active_order_id, history | Один незавершённый заказ; бюджет/срок положительны, тарифов ≥1 |
| Dispatcher | agent_id, telemetry, pending_orders, reservations, availability | Телеметрия содержит observed_at и delivered_at; нет доступа к скрытому состоянию |
| Order | id, passenger_id, origin, destination, created_at, wait_deadline, version, tariff_id, state, assignment_attempts, commitment_id | Версия начинается с 1 и строго растёт при смене условий/отзыве |
| Tariff | id, base, per_km, per_min, minimum | Только economy/comfort в первой версии, суммы неотрицательны |
| Offer | id, order_id, version, driver_id, tariff_id, price, floor, eta_ms, driver_rating, idle_since, expires_at, round_no, state | Обязывает водителя при актуальных условиях до срока; не назначает поездку |
| Negotiation | order_id, round_no, round_start, offer_deadline, reply_deadline, offers, counteroffers, tariff_proposal | 1–3 раунда, общий wait_deadline не продлевается |
| Commitment | id, order_id, version, driver_id, passenger_id, tariff_id, price, accepted_offer_id, driver_consent, passenger_consent, state, pickup_deadline, confirmed_at | Снимок условий; два согласия на идентичные поля; единственный действующий commit |
| Message | id, sender, recipient, kind, order_id, version, sent_at, deliver_at, correlation_id, payload | Типизированное содержимое; transport/identity отделены от утверждений отправителя |
| ReputationEvent | id, subject_id, commitment_id, value, cause, verified_by, source_event_id | Runtime: value 1 или 5, один итог subject/commitment, проверенное происхождение; входная fixture-история допускает оценки 1–5 |
| Fault | id, type F1–F7, trigger, target, parameters, resolved_target, activated_at | Хранит и условие, и фактически выбранный объект |
| InputBundle | schema_version, generator_version, seed, Python, city, agents, orders, channel_profile, faults | Материализован до механизма; неизменяем и хеширован |
| RunConfig | allocation, conflict_policy, rating_policy, protection_profile, limits, weights, deadlines | Только известные значения/поля; сохраняется полностью |
| RunResult | case_id, execution_id/result_id, input_hash, config, termination_reason, metrics, artifact_manifest | Успешность записи отдельно от исходов поездок |
| SeriesResult | result_id, experiment_id, input_bundle_ids, variants, pairs, aggregation | Только полные пары участвуют в парных агрегатах |
| Job | job_id, request_id, kind, state, phase, completed_runs, total_runs, results, error | Оболочка выполнения, не агент модели |
| TraceEvent | seq, event_id, time_ms, phase, kind, participants, before/after, reason, causal_message_id, fault_id | Последовательная append-only запись; нет технических часов в каноническом событии |
| Playback | initial_snapshot, checkpoints, changes, movements | Одно состояние просмотра на seq, только применение записей |
| Report | lab_number, method, conditions, result_refs, conclusions, limitations, appendix_refs | Четыре файла; каждый численный вывод связан с сохранённым результатом |

## Локальные знания и полномочия

| Роль | Цель и доступные знания | Решения и средства | Запреты |
| --- | --- | --- | --- |
| Водитель | Выручка/прибыль при собственном пороге; своя позиция, занятость, расходы, принятые запросы, объявленные цены текущих торгов, сообщённый рейтинг пассажира | Маршрут от известной позиции; предложить/понизить/сохранить/отозвать цену; согласиться; выполнять путь; сообщать телеметрию | Назначать себя, изменять чужие предложения, итоговую цену или реестр рейтинга |
| Пассажир | Приемлемая поездка по бюджету/ожиданию; собственные ограничения, доставленные условия и рейтинги водителей | Принять/отклонить, контрцена, предложить допустимый тариф, отменить до обязательства | Подтверждать за водителя, менять рейтинг напрямую, занимать вторую машину |
| Диспетчер | Обслуживание и непротиворечивые назначения; доставленная телеметрия/предложения, версии и согласия | Рассылка, фильтр/оценка, запрос согласия, атомарный commit, отзыв/переназначение | Использовать скрытые бюджеты/пороги водителей, навязывать не принятую цену |
| Наблюдатель | Исследование; истинное состояние/траектории/все события | Измерения, диагностика, проекция | Передавать скрытую истину в политику агента |

Маршрутизатор, транспорт сообщений, часы и проверенный реестр — средства среды,
а не дополнительные автономные роли. Разрешения зависят от роли и состояния, не от текста payload.

## Функции агента

Для каждого i: see_i возвращает только разрешённое публичное наблюдение и доставленный
inbox; next_i обновляет локальное состояние/знания; action_i выбирает намерение и основание.
Только среда/протокол применяет разрешённое последствие. Общая карта и тарифы публичны;
чужие бюджеты, пороги и текущая скрытая позиция доступны только в объёме соответствующих
доставленных сообщений. Наблюдатель не является аргументом action_i.

## Переходы состояний

### Заказ

`created → allocating → awaiting_consent → assigned → pickup → in_trip → completed`.
Контролируемый конфликт: `allocating → provisional_pickup → negotiating → awaiting_consent`.
До посадки возможны `cancelled` (отказ/нет приемлемых условий), `expired` (срок),
`failed` (неустранимое нарушение). Отзыв назначения до посадки:
`assigned|pickup → allocating` с version+1, освобождением резерва и максимум двумя
переназначениями после первого назначения. Старые ответы не восстанавливают обязательство.
После посадки отказ: `in_trip → failed`; позиция пассажира остаётся последней фактической.
`completed/cancelled/expired/failed` терминальны. Незавершённость на горизонте — отметка
результата, не выдуманный переход заказа в отмену.

### Водитель и пассажир

Водитель: `idle → offering → reserved → to_pickup → carrying → idle`;
предварительная сцена: `offering → provisional_to_pickup → negotiating` без резерва заказа.
До commit допустим выход в idle; недоступность даёт offline, после восстановления требуется
новое согласование. Пассажир: `requesting → evaluating|negotiating → waiting → onboard → arrived`;
до посадки возможен отказ/истечение, после — failed. Состояния связаны с Order/Commitment,
поэтому независимое изменение одной панели невозможно.

### Обязательство и предложение

Commitment: `pending → confirmed → boarded → completed`, либо `revoked/failed`.
Offer: `open → selected → committed`, либо `rejected/withdrawn/expired/invalidated`.
Выбор предложения ещё не означает commit. Цена и тариф confirmed неизменяемы;
новые условия создают новую версию и новые согласия.

### Задание оболочки

`queued → running → succeeded|failed`; `queued → cancelled`;
`running → cancelling → cancelled|failed`. Принятая отмена запрещает succeeded.
Терминальное состояние не меняется. F1–F7 — исходы модели, не исключения worker.

## Инварианты

I1: у заказа максимум один confirmed/boarded commitment.
I2: у водителя максимум один confirmed/boarded commitment.
I3: пассажир физически максимум в одной машине и с одним активным заказом.
I4: посадка/завершение только по актуальному commitment; завершение и выручка однократны.
I5: commit требует одинаковых версии, цены и тарифа в двух согласиях, допустимости и срока.
I6: после смены версии старые офферы/согласия не действуют.
I7: история меняется только подтверждёнными событиями с происхождением, без повторного учёта.
I8: время монотонно, маршрут связен, пассажир не телепортируется.
Проверки I1/I2/I5/I6 как защиты могут отличаться в опытах; физические I3/I8 и целостность
I7 действуют всегда. Намерение нарушить и совершившееся нарушение учитываются раздельно.

## Экономика и рейтинг

Тарифы в рублях: economy `(100,18/км,4/мин,min200)`;
comfort `(160,25/км,6/мин,min300)`.
`P_ref=round_half_up(max(min, base+per_km*d_m/1000+per_min*t_ms/60000))`.
`r_eff=(5*4.5+sum(verified))/(5+n)` точно;
`s=min(0.15,0.10*max(0,4.5-r_eff))`, либо 0 при выключенной политике.
`P_start=round_half_up(P_ref*(1+s))`.
`floor=max(tariff.minimum, ceil_to_kopeck(expected_cost+minimum_profit))`;
`P_offer=max(floor,P_start+markup)`. Порог рассчитывается водителем из подачи и поездки,
диспетчер его не читает. Расход: фактические метры/мс движения × индивидуальные ставки;
округление общей суммы расхода один раз в конце опыта. Предварительный подъезд обоих
конкурентов учитывается. Выручка возникает при completed; у незавершённой поездки доплаты нет.
Прибыль = выручка − расходы, может быть отрицательной.

За выполненное обязательство участнику +5; за доказанную относимую неявку/нарушение +1.
Отказ до обязательства и системная отмена не штрафуются; причинность фиксируется в трассе.
В основных сравнениях рейтинги фиксированы; изменение истории исследуется отдельной серией.
Контроль: 5 км/12 мин → economy 238.00, r_eff3.5 →261.80; comfort 357.00.
