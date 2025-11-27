from threading import Thread
import time

class CandleThread(Thread):
    def __init__(self):
        Thread.__init__(self)

    def run(self):
        z = 0
        while z < 10:
             time.sleep(2)
             z += 1
             print("z",z)

if __name__ == '__main__':
    print("start")
    c = CandleThread()
    c.start()

