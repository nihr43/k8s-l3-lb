push: image
	docker push images.local:30500/l3lb

image: lint
	docker build . --tag=images.local:30500/l3lb

doctest:
	python3 -m doctest main.py

lint:
	black main.py
	flake8 main.py --ignore=E501

jenkins:
	docker build --no-cache . --tag=images.local:30500/l3lb
	docker push images.local:30500/l3lb
