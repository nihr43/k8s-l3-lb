from alpine

run apk add python3 py3-pip \
            python3-dev gcc musl-dev linux-headers --no-cache

copy main.py /usr/sbin/l3lb
copy requirements.txt requirements.txt

run pip install -r requirements.txt --break-system-packages

cmd [ "python3", "/usr/sbin/l3lb" ]
