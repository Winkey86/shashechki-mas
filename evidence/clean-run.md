# Чистый локальный запуск

Проверено scripts/check_clean.py в новой временной копии src/web/tests/scenarios/fonts. Git, .local, существующие results и site-packages не переносились. Python запущен с -S; сетевые аккаунты и внешние сервисы не использовались.

Ran 49 tests in 2.140s

OK

Выполнены normal, playback-10, conflict, tariff-switch, F1–F7; дополнительно auction, validate experiment, повтор normal с canonical compare и ZIP-экспорт. Все команды завершились успешно. HTTP-проверки использовали временный loopback-порт. Временная копия удалена. Подробности: clean-run.json.
