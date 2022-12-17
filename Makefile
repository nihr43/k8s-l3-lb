push: image
	docker push images.local:5000/l3lb

image: lint
	docker build . --tag=images.local:5000/l3lb

lint:
	flake8 main.py --ignore=E501
