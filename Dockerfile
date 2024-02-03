from alpine:3.19

run apk add python3 py3-pip \
            python3-dev gcc musl-dev linux-headers --no-cache

copy requirements.txt requirements.txt
run pip install -r requirements.txt --break-system-packages
copy main.py /usr/sbin/l3lb

cmd [ "python3", "-u", "/usr/sbin/l3lb" ]
