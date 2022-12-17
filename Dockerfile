from alpine

run apk update &&\
    apk add python3

copy main.py /usr/sbin/l3lb

cmd [ "python3", "/usr/sbin/l3lb" ]
