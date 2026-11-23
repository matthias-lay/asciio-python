PREFIX ?= /usr/local
PYTHON ?= /usr/bin/python3
DATADIR = $(PREFIX)/share/asciio-python
BINDIR = $(PREFIX)/bin
COMMANDS = asciio-python asciio tasciio asciio-to-text asciio_to_text text-to-asciio text_to_asciio
MODULES = $(notdir $(wildcard src/asciio/*.py))

.PHONY: check-deps install uninstall

check-deps:
	"$(PYTHON)" -c 'import sys; sys.version_info >= (3, 11) or sys.exit("Python 3.11 or newer is required")'
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:$${PYTHONPATH:-}" "$(PYTHON)" -c 'from asciio import __version__; print("Runtime dependencies available; Asciio Python " + __version__)'

install: check-deps
	@for command in $(COMMANDS); do \
		target="$(DESTDIR)$(BINDIR)/$$command"; \
		if { test -e "$$target" || test -L "$$target"; } && \
			test "$$(readlink "$$target")" != "../share/asciio-python/launcher"; then \
			echo "Refusing to overwrite an unrelated command: $$target" >&2; exit 1; \
		fi; \
	done
	install -d "$(DESTDIR)$(DATADIR)/asciio" "$(DESTDIR)$(BINDIR)"
	install -m 644 src/asciio/*.py "$(DESTDIR)$(DATADIR)/asciio/"
	install -m 644 README.md LICENSE "$(DESTDIR)$(DATADIR)/"
	{ printf '#!%s\n' "$(PYTHON)"; tail -n +2 packaging/launcher; } > "$(DESTDIR)$(DATADIR)/launcher"
	chmod 755 "$(DESTDIR)$(DATADIR)/launcher"
	@for command in $(COMMANDS); do \
		ln -sfn "../share/asciio-python/launcher" "$(DESTDIR)$(BINDIR)/$$command"; \
	done
	@echo "Installed in $(DESTDIR)$(PREFIX); add $(PREFIX)/bin to PATH."

uninstall:
	@for command in $(COMMANDS); do \
		target="$(DESTDIR)$(BINDIR)/$$command"; \
		if test "$$(readlink "$$target")" = "../share/asciio-python/launcher"; then \
			rm "$$target"; \
		fi; \
	done
	@for module in $(MODULES); do \
		rm -f "$(DESTDIR)$(DATADIR)/asciio/$$module"; \
	done
	rm -f "$(DESTDIR)$(DATADIR)/launcher" "$(DESTDIR)$(DATADIR)/README.md" "$(DESTDIR)$(DATADIR)/LICENSE"
	rmdir --ignore-fail-on-non-empty "$(DESTDIR)$(DATADIR)/asciio" "$(DESTDIR)$(DATADIR)"
