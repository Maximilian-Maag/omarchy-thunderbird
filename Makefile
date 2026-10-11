# Canonical entry points. `make test` runs the same suite CI runs
# (.github/workflows/test.yml -> tools/run_tests.sh); `make check` is the fast
# pre-commit subset.
.PHONY: test check lint mutation

test:
	@bash tools/run_tests.sh

check: lint
	@python3 -m unittest discover -s tests -p 'test_unit_*.py' -q
	@python3 -m unittest discover -s tests -p 'test_regression_*.py' -q

lint:
	@python3 tools/policy_check.py

mutation:
	@python3 tools/mutator.py
