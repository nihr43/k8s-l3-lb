push: image
	docker push images.local:30500/l3lb

image: doctest
	docker build . --tag=images.local:30500/l3lb

doctest: lint
	python3 -m doctest main.py

lint:
	flake8 main.py --ignore=E501
