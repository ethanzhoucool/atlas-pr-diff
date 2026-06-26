.PHONY: test lint install build clean

test:
	python3 -m unittest discover -s tests -v

lint:
	python3 -m compileall -q atlas_diff

install:
	pipx install --force .

build:
	python3 -m build

clean:
	rm -rf dist build *.egg-info
