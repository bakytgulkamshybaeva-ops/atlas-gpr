# mpp_tools — конвейер MS Project (.mpp) → реальный ГПР

Извлекает из бинарных `.mpp` настоящие задачи, **связи Finish→Start и критический путь**
и генерирует интерактивные HTML-Гантты (`../mpp/<oid>-<spot>.html`), которые движок
встраивает в каждый блок (реестр `MPP{}` в `../index.html`).

## Состав
- `MppExtract.java` — читает `.mpp` через MPXJ → JSON (id, wbs, level, cat, name, summary,
  days, start, finish, pct, crit, pred). Принимает много файлов за один запуск.
- `build_mpp.py` — прогоняет JSON через шаблон (`../mpp/aura-3.html` — исходный рендер
  от заказчика: WBS + связи + критпуть + подсветка по наведению) → HTML на блок;
  вшивает реестр `MPP{}` в `index.html`. Ось берётся из min/max дат задач.

## Зависимости (на этой машине)
- **JDK 21** (нужен `javac`; JRE без компилятора): был скачан в `/tmp/jdk21/...`
  (Adoptium aarch64). JRE для запуска лежит в `~/Documents/Claude/jre_tmp/`.
- **MPXJ** (jar-ы) из pip-пакета: `pip3 install --user mpxj` →
  `~/Library/Python/3.9/.../site-packages/mpxj/lib/*.jar`.
- ⚠️ JVM **нельзя** запускать встроенной в python (jpype) — у python из CommandLineTools
  нет entitlement на JIT → SIGBUS. Только отдельным процессом `java`.

## Запуск (регенерация всех блоков)
```bash
JDK=/tmp/jdk21/jdk-21.0.11+10/Contents/Home          # или любой JDK 21+
CP=$(ls ~/Library/Python/3.9/lib/python/site-packages/mpxj/lib/*.jar | tr '\n' ':')
cd gpr-engine/mpp_tools
"$JDK/bin/javac" -cp "$CP" MppExtract.java
FILES=$(find ~/Documents/Claude/gpr-source -name '*.mpp')
"$JDK/bin/java" -cp "$CP:." MppExtract $FILES > /tmp/all_mpp.json
python3 build_mpp.py                                  # → ../mpp/*.html + реестр в index.html
```

> Источник `.mpp`: `~/Documents/Claude/gpr-source/ГПР по объектам/ГПР MS Project/` (не в репо).
> Готовность из `.mpp` (рабочие дни, % complete) близка к отчёту PDF, но не равна —
> это нормально (см. ../VALIDATION.md). Блоки вне отчёта (Атмо 37-39, Керуен 6,7)
> генерируются, но в реестр не попадают (нет блока в gpr_data.json).
