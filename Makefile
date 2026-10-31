PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
IN ?= tickets.jsonl
OUT ?= pred.jsonl
GOLD ?= private/handout/tickets_valid.jsonl
PRED ?= $(OUT)
REPORT ?= private/evaluation.json
MARKDOWN ?= private/evaluation.md
KIND ?= organizer
PERSIST ?= 0
RPM ?=
HANDOUT ?=

.PHONY: predict evaluate serve import-handout annotation-sample suggest-templates
import-handout:
	PYTHONPATH=backend $(PYTHON) -m app.handout --archive "$(HANDOUT)"

annotation-sample:
	PYTHONPATH=backend $(PYTHON) -m app.prepare sample --input "$(IN)" --output "$(OUT)"

suggest-templates:
	PYTHONPATH=backend $(PYTHON) -m app.prepare templates --input "$(IN)" --output "$(OUT)"

predict:
	PYTHONPATH=backend $(PYTHON) -m app.predict --input "$(IN)" --output "$(OUT)" $(if $(filter 1,$(PERSIST)),--persist,) $(if $(RPM),--rpm "$(RPM)",)

evaluate:
	@mkdir -p "$(dir $(REPORT))" "$(dir $(MARKDOWN))"
	PYTHONPATH=backend $(PYTHON) -m app.evaluate --gold "$(GOLD)" --pred "$(PRED)" --out "$(REPORT)" --markdown "$(MARKDOWN)" --dataset-kind "$(KIND)" $(if $(filter 1,$(PERSIST)),--persist,)

serve:
	PYTHONPATH=backend $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000
