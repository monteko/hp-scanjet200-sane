CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra
all: libsane-hp200.so.1
libsane-hp200.so.1: hp200.c
	$(CC) $(CFLAGS) -std=c99 -fPIC -shared -o $@ $< -Wl,-soname,libsane-hp200.so.1 -lusb-1.0
clean:
	rm -f libsane-hp200.so.1
.PHONY: all clean
test: tests/backend-test.so
	python3 -m unittest discover -s tests -p 'test_backend.py' -v
tests/backend-test.so: hp200.c
	$(CC) $(CFLAGS) -std=c99 -fPIC -shared -DHP200_TEST '-DHP200_BRIDGE="$(CURDIR)/tests/fixture.py"' -o $@ $<
.PHONY: test
